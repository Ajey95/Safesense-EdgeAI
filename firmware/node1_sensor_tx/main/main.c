#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "bme680_esp_idf.h"
#include "delivery_queue.h"
#include "forecast.h"
#include "bt_alert.h"
#include "esp_err.h"
#include "esp_http_client.h"
#include "esp_log.h"
#include "esp_random.h"
#include "esp_timer.h"
#include "driver/uart.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "gas_adc_esp_idf.h"
#include "lwip/inet.h"
#include "lwip/sockets.h"
#include "nvs_flash.h"
#include "tx_protocol.h"
#include "wifi_station.h"

#define I2C_SDA_GPIO 21
#define I2C_SCL_GPIO 22
#define MQ135_ADC_CHANNEL ADC_CHANNEL_6
#define CSI_PACKET_PORT 3333
#define LAPTOP_DISCOVERY_PORT 3334

static const char *TAG = "safesense_tx";
static delivery_queue_t queue;
static i2c_master_bus_handle_t i2c_bus;
static bme680_esp_idf_t bme;
static bool bme_ready;
static uint32_t sequence;
static float minute_history[FORECAST_HISTORY_MINUTES][FORECAST_CHANNELS];
static unsigned history_count;
static int64_t last_history_us;
static int64_t last_forecast_alert_us;
#if CONFIG_SAFESENSE_TX_DIRECT_LAPTOP_AP
static uint32_t laptop_ipv4;
static portMUX_TYPE laptop_ip_lock = portMUX_INITIALIZER_UNLOCKED;
static bool test_alert_requested;
#endif
static bool forecast_demo_range_crossed(const float prediction[FORECAST_HORIZONS][FORECAST_CHANNELS],
                                        uint8_t room, uint8_t *minutes, uint8_t *channel);
static void make_event_id(char out[DELIVERY_EVENT_ID_MAX]);
static void flush_pending(void);
static bool transport_link_connected(void);
static bool add_alert_metadata(delivery_record_t *record, bool alert,
                               uint8_t room, uint8_t minutes, uint8_t channel,
                               bool simulated);

#if CONFIG_SAFESENSE_TX_SCENARIO_SERIAL_DEMO
static void scenario_serial_loop(void) {
    if (uart_driver_install(UART_NUM_0, 4096, 0, 0, NULL, 0) != ESP_OK) {
        ESP_LOGE(TAG, "Demo UART0 driver unavailable");
        return;
    }
    ESP_LOGW(TAG, "SYNTHETIC SERIAL DEMO MODE: real sensor samples are not used");
    char line[160];
    unsigned used = 0;
    while (true) {
        uint8_t ch;
        if (uart_read_bytes(UART_NUM_0, &ch, 1, pdMS_TO_TICKS(1000)) != 1) continue;
        if (ch == '\r') continue;
        if (ch != '\n' && ch >= 32 && ch <= 126 && used + 1 < sizeof(line)) {
            line[used++] = (char)ch;
            continue;
        }
        if (ch != '\n') { used = 0; continue; }
        line[used] = '\0'; used = 0;
        if (strcmp(line, "RESET") == 0) {
            history_count = 0;
            last_forecast_alert_us = 0;
            printf("DEMO_READY\n");
            continue;
        }
        unsigned room, minute, fault;
        float value[5];
        int consumed = 0;
        if (sscanf(line, "SIM|%u|%u|%f|%f|%f|%f|%f|%u%n", &room, &minute,
                   &value[0], &value[1], &value[2], &value[3], &value[4],
                   &fault, &consumed) != 8 || line[consumed] != '\0' ||
            room >= 5 || minute > 150 || fault > 1 || value[0] < -40 || value[0] > 100 ||
            value[1] < 0 || value[1] > 100 || value[2] < 30000 || value[2] > 110000 ||
            value[3] <= 0 || value[4] < 0 || value[4] > 4095) {
            printf("DEMO_INVALID\n");
            continue;
        }
        if (history_count == FORECAST_HISTORY_MINUTES) {
            memmove(minute_history, minute_history + 1,
                    (FORECAST_HISTORY_MINUTES - 1) * sizeof(minute_history[0]));
            history_count--;
        }
        memcpy(minute_history[history_count++], value, sizeof(value));
        if (history_count < FORECAST_HISTORY_MINUTES) continue;
        float predicted[FORECAST_HORIZONS][FORECAST_CHANNELS];
        uint8_t alert_minutes = 0, alert_channel = 0;
        const bool model_ready = forecast_predict((const float (*)[5])minute_history,
                                                  (uint8_t)room, predicted);
        if (model_ready)
            printf("DEMO_FORECAST|%.3f|%.3f|%.2f|%.2f|%.1f\n",
                   predicted[5][0], predicted[5][1], predicted[5][2],
                   predicted[5][3], predicted[5][4]);
        const bool alert = model_ready &&
            forecast_demo_range_crossed((const float (*)[5])predicted, (uint8_t)room,
                                         &alert_minutes, &alert_channel);
        delivery_record_t record = {0};
        make_event_id(record.event_id);
        const tx_sample_t sample = {.event_id = record.event_id,
            .tx_device_id = "safesense-synthetic-tx", .sequence = sequence++,
            .bme_healthy = true, .temperature_c = value[0], .humidity_pct = value[1],
            .pressure_pa = value[2], .gas_valid = true, .heat_stable = true,
            .gas_resistance_ohm = value[3], .mq135_valid = true,
            .mq135_adc_raw = (int)value[4]};
        if (tx_format_json(record.payload, sizeof(record.payload), &sample) < 0 ||
            !add_alert_metadata(&record, alert, (uint8_t)room, alert_minutes,
                                alert_channel, true)) {
            printf("DEMO_ERROR|FORMAT\n");
            continue;
        }
        const bool persisted = delivery_queue_enqueue(&queue, &record) == 0;
        if (!fault && persisted && transport_link_connected()) flush_pending();
        const int pending = persisted ? delivery_queue_contains(&queue, record.event_id) : -1;
        const bool rx_ack = persisted && pending == 0;
        bool bt_ack = false;
        if (alert && !rx_ack)
            bt_ack = bt_alert_send(record.event_id, (uint8_t)room,
                                   alert_minutes, alert_channel, true, 3000);
        printf("DEMO_RESULT|%s|%u|%u|%u|%u|%u|%u\n", record.event_id,
               alert ? 1u : 0u, rx_ack ? 1u : 0u, bt_ack ? 1u : 0u,
               (unsigned)alert_minutes, (unsigned)alert_channel, persisted ? 1u : 0u);
    }
}
#endif

static bool forecast_demo_range_crossed(const float prediction[FORECAST_HORIZONS][FORECAST_CHANNELS],
                                        uint8_t room, uint8_t *minutes, uint8_t *channel) {
    static const float low[5][3] = {{-19,25,45000},{18,25,45000},{19,25,42000},
                                    {19,20,40000},{17,20,45000}};
    static const float high[5][3] = {{-12,65,200000},{27,65,200000},{29,70,200000},
                                     {34,70,200000},{27,65,200000}};
    static const uint8_t indices[3] = {0,1,3};
    if (room >= 5) return false;
    for (unsigned step = 0; step < FORECAST_HORIZONS; ++step)
        for (unsigned j = 0; j < 3; ++j) {
            const float value = prediction[step][indices[j]];
            if (value < low[room][j] || value > high[room][j]) {
                *minutes = (uint8_t)((step + 1) * 5);
                *channel = indices[j];
                return true;
            }
        }
    return false;
}

static bool update_forecast_history(const bme680_reading_t *reading, const gas_sample_t *mq,
                                    uint8_t *minutes, uint8_t *channel) {
    /* A zero MQ signal on the current board is an electrical gap, not a safe
     * gas reading. Synthetic-trained inference is disabled until all inputs
     * are valid. The model is still unvalidated for physical alert decisions. */
    if (!reading || !mq || !reading->gas_valid || !reading->heat_stable ||
        !mq->healthy || mq->signal <= 0) {
        history_count = 0;
        last_history_us = 0;
        return false;
    }
    const int64_t now = esp_timer_get_time();
    if (last_history_us && now - last_history_us > 90000000) history_count = 0;
    if (last_history_us && now - last_history_us < 60000000) return false;
    last_history_us = now;
    if (history_count == FORECAST_HISTORY_MINUTES) {
        memmove(minute_history, minute_history + 1,
                (FORECAST_HISTORY_MINUTES - 1) * sizeof(minute_history[0]));
        history_count--;
    }
    float *sample = minute_history[history_count++];
    sample[0] = reading->temperature_c;
    sample[1] = reading->humidity_percent;
    sample[2] = reading->pressure_pa;
    sample[3] = reading->gas_resistance_ohm;
    sample[4] = (float)mq->signal;
    if (history_count < FORECAST_HISTORY_MINUTES) {
        ESP_LOGI(TAG, "Forecast history %u/%u valid minute samples", history_count,
                 FORECAST_HISTORY_MINUTES);
        return false;
    }
    float prediction[FORECAST_HORIZONS][FORECAST_CHANNELS];
    if (!forecast_predict((const float (*)[FORECAST_CHANNELS])minute_history,
                          CONFIG_SAFESENSE_FORECAST_ROOM, prediction)) return false;
    ESP_LOGI(TAG, "Synthetic-trained TinyML +30m T=%.1f RH=%.1f P=%.0f gas=%.0f MQ=%.0f model=%s",
             prediction[5][0], prediction[5][1], prediction[5][2], prediction[5][3],
             prediction[5][4], forecast_model_sha256());
    if (last_forecast_alert_us && now - last_forecast_alert_us < 900000000) return false;
    if (!forecast_demo_range_crossed((const float (*)[FORECAST_CHANNELS])prediction,
                                     CONFIG_SAFESENSE_FORECAST_ROOM, minutes, channel)) return false;
    last_forecast_alert_us = now;
    return true;
}

static bool migrate_pre_fix_test_queue(void) {
    /* The pre-calibration-fix TX test records contain false 0 C values.
     * Never forward them to RX after upgrading this board. Only the TX-owned
     * namespace is affected; the first clean boot records the migration. */
    if (nvs_flash_init() != ESP_OK) return false;
    nvs_handle_t handle;
    if (nvs_open("sstx", NVS_READWRITE, &handle) != ESP_OK) return false;
    uint8_t revision = 0;
    esp_err_t status = nvs_get_u8(handle, "cal_rev", &revision);
    if (status == ESP_ERR_NVS_NOT_FOUND || (status == ESP_OK && revision == 0u)) {
        status = nvs_erase_all(handle);
        if (status == ESP_OK) status = nvs_set_u8(handle, "cal_rev", 1u);
        if (status == ESP_OK) status = nvs_commit(handle);
        if (status == ESP_OK) ESP_LOGW(TAG, "Discarded pre-fix TX test queue in namespace sstx");
    } else if (status == ESP_OK && revision == 1u) {
        status = ESP_OK;
    } else {
        status = ESP_FAIL;
    }
    nvs_close(handle);
    return status == ESP_OK;
}

static bool start_sensor(void) {
    if (!i2c_bus) {
        const i2c_master_bus_config_t bus_config = {
            .i2c_port = I2C_NUM_0, .sda_io_num = I2C_SDA_GPIO,
            .scl_io_num = I2C_SCL_GPIO, .clk_source = I2C_CLK_SRC_DEFAULT,
            .glitch_ignore_cnt = 7, .flags.enable_internal_pullup = true,
        };
        if (i2c_new_master_bus(&bus_config, &i2c_bus) != ESP_OK) return false;
    }
    const uint8_t addresses[] = {BME680_I2C_ADDRESS_LOW, BME680_I2C_ADDRESS_HIGH};
    for (size_t index = 0; index < sizeof(addresses); ++index) {
        const uint8_t address = addresses[index];
        const esp_err_t probe = i2c_master_probe(i2c_bus, address, 50);
        if (probe != ESP_OK) {
            ESP_LOGW(TAG, "No I2C ACK at BME680 address 0x%02x: %s", address,
                     esp_err_to_name(probe));
            continue;
        }
        const bme680_status_t status = bme680_esp_idf_init(&bme, i2c_bus, address, NULL);
        if (status == BME680_OK) {
            ESP_LOGI(TAG, "Custom BME680 initialized at 0x%02x on GPIO21/GPIO22", address);
            return true;
        }
        ESP_LOGW(TAG, "Custom BME680 init at 0x%02x failed: %d", address, status);
    }
    return false;
}

static bool add_alert_metadata(delivery_record_t *record, bool alert,
                               uint8_t room, uint8_t minutes, uint8_t channel,
                               bool simulated) {
    const size_t size = strlen(record->payload);
    if (size < 2 || record->payload[size - 1] != '}') return false;
    const size_t available = sizeof(record->payload) - size + 1;
    const int written = alert
        ? snprintf(record->payload + size - 1, available,
                   ",\"simulated\":%s,\"forecast_alert\":{\"room\":%u,\"horizon_minutes\":%u,\"channel\":%u}}",
                   simulated ? "true" : "false", room, minutes, channel)
        : snprintf(record->payload + size - 1, available, ",\"simulated\":%s}",
                   simulated ? "true" : "false");
    return written > 0 && (size_t)written < sizeof(record->payload) - size + 1;
}

static bool transport_link_connected(void) {
#if CONFIG_SAFESENSE_TX_DIRECT_LAPTOP_AP
    return safesense_wifi_ap_client_connected();
#else
    return safesense_wifi_station_connected();
#endif
}

#if CONFIG_SAFESENSE_TX_DIRECT_LAPTOP_AP
static void laptop_discovery_task(void *unused) {
    (void)unused;
    const int fd = socket(AF_INET, SOCK_DGRAM, IPPROTO_IP);
    if (fd < 0) { ESP_LOGE(TAG, "Laptop discovery socket failed"); vTaskDelete(NULL); return; }
    struct sockaddr_in local = {.sin_family = AF_INET,
                                .sin_port = htons(LAPTOP_DISCOVERY_PORT),
                                .sin_addr.s_addr = htonl(INADDR_ANY)};
    if (bind(fd, (struct sockaddr *)&local, sizeof(local)) != 0) {
        ESP_LOGE(TAG, "Laptop discovery bind failed"); close(fd); vTaskDelete(NULL); return;
    }
    while (true) {
        char message[40];
        struct sockaddr_in peer = {0};
        socklen_t peer_length = sizeof(peer);
        const int length = recvfrom(fd, message, sizeof(message), 0,
                                    (struct sockaddr *)&peer, &peer_length);
        if ((ntohl(peer.sin_addr.s_addr) & 0xFFFFFF00u) != 0xC0A80400u) continue;
        if (length == (int)strlen("SAFESENSE_TEST_ALERT_V1") &&
            memcmp(message, "SAFESENSE_TEST_ALERT_V1", (size_t)length) == 0) {
            portENTER_CRITICAL(&laptop_ip_lock);
            test_alert_requested = true;
            portEXIT_CRITICAL(&laptop_ip_lock);
            ESP_LOGW(TAG, "Transport test alert requested by nearby laptop");
            continue;
        }
        if (length != (int)strlen("SAFESENSE_LAPTOP_V1") ||
            memcmp(message, "SAFESENSE_LAPTOP_V1", (size_t)length) != 0) continue;
        portENTER_CRITICAL(&laptop_ip_lock);
        laptop_ipv4 = peer.sin_addr.s_addr;
        portEXIT_CRITICAL(&laptop_ip_lock);
        char host[INET_ADDRSTRLEN];
        if (inet_ntop(AF_INET, &peer.sin_addr, host, sizeof(host)))
            ESP_LOGI(TAG, "Laptop receiver discovered at %s:%d", host,
                     CONFIG_SAFESENSE_TX_LAPTOP_HTTP_PORT);
    }
}
#endif

typedef struct { char body[256]; size_t used; bool overflow; } http_reply_t;

static esp_err_t http_event(esp_http_client_event_t *event) {
    if (event->event_id != HTTP_EVENT_ON_DATA || !event->user_data) return ESP_OK;
    http_reply_t *reply = event->user_data;
    if (event->data_len < 0 || (size_t)event->data_len >= sizeof(reply->body) - reply->used) {
        reply->overflow = true;
        return ESP_OK;
    }
    memcpy(reply->body + reply->used, event->data, (size_t)event->data_len);
    reply->used += (size_t)event->data_len;
    reply->body[reply->used] = '\0';
    return ESP_OK;
}

static bool post_record(const delivery_record_t *record) {
#if CONFIG_SAFESENSE_TX_DIRECT_LAPTOP_AP
    char direct_url[128];
#endif
    const char *endpoint = CONFIG_SAFESENSE_TX_RX_HTTP_URL;
#if CONFIG_SAFESENSE_TX_DIRECT_LAPTOP_AP
    uint32_t ip;
    portENTER_CRITICAL(&laptop_ip_lock);
    ip = laptop_ipv4;
    portEXIT_CRITICAL(&laptop_ip_lock);
    if (!ip || !safesense_wifi_ap_client_connected()) return false;
    struct in_addr address = {.s_addr = ip};
    char host[INET_ADDRSTRLEN];
    if (!inet_ntop(AF_INET, &address, host, sizeof(host))) return false;
    snprintf(direct_url, sizeof(direct_url), "http://%s:%d/api/v1/tx/environment",
             host, CONFIG_SAFESENSE_TX_LAPTOP_HTTP_PORT);
    endpoint = direct_url;
#endif
    if (!endpoint[0]) return false;
    http_reply_t reply = {0};
    const esp_http_client_config_t config = {
        .url = endpoint,
        .timeout_ms = 5000,
        .event_handler = http_event,
        .user_data = &reply,
    };
    esp_http_client_handle_t client = esp_http_client_init(&config);
    if (!client) return false;
    esp_http_client_set_method(client, HTTP_METHOD_POST);
    esp_http_client_set_header(client, "Content-Type", "application/json");
    esp_http_client_set_post_field(client, record->payload, strlen(record->payload));
    const esp_err_t result = esp_http_client_perform(client);
    const int status = result == ESP_OK ? esp_http_client_get_status_code(client) : 0;
    const bool accepted = result == ESP_OK && (status == 200 || status == 202) &&
        !reply.overflow && tx_ack_matches(reply.body, reply.used, record->event_id);
    if (!accepted) ESP_LOGW(TAG, "Wi-Fi HTTP deferred: %s status=%d event=%s", esp_err_to_name(result), status, record->event_id);
    esp_http_client_cleanup(client);
    return accepted;
}

static void flush_pending(void) {
    delivery_record_t record;
    while (delivery_queue_count(&queue) > 0) {
        if (delivery_queue_peek(&queue, &record) != 0) {
            ESP_LOGE(TAG, "TX NVS queue head unreadable; delivery stopped without deleting records");
            break;
        }
        if (!post_record(&record)) break;
        if (delivery_queue_ack_head(&queue, record.event_id) != 0) {
            ESP_LOGE(TAG, "HTTP accepted %s but NVS queue acknowledgement failed", record.event_id);
            break;
        }
        ESP_LOGI(TAG, "Wi-Fi receiver accepted event=%s pending=%u", record.event_id, delivery_queue_count(&queue));
    }
}

static void make_event_id(char out[DELIVERY_EVENT_ID_MAX]) {
    uint32_t nonce[3];
    esp_fill_random(nonce, sizeof(nonce));
    snprintf(out, DELIVERY_EVENT_ID_MAX, "tx-%08lx%08lx%08lx",
             (unsigned long)nonce[0], (unsigned long)nonce[1], (unsigned long)nonce[2]);
}

#if !CONFIG_SAFESENSE_TX_DIRECT_LAPTOP_AP
static void udp_probe_task(void *unused) {
    (void)unused;
    const TickType_t probe_delay_ticks = pdMS_TO_TICKS(CONFIG_SAFESENSE_TX_CSI_PROBE_INTERVAL_MS);
    if (probe_delay_ticks == 0) {
        ESP_LOGE(TAG, "CSI probe interval is shorter than one FreeRTOS tick");
        vTaskDelete(NULL);
        return;
    }
    const int socket_fd = socket(AF_INET, SOCK_DGRAM, IPPROTO_IP);
    if (socket_fd < 0) { ESP_LOGE(TAG, "CSI UDP socket creation failed"); vTaskDelete(NULL); return; }
    struct sockaddr_in target = {.sin_family = AF_INET, .sin_port = htons(CSI_PACKET_PORT)};
    if (inet_pton(AF_INET, CONFIG_SAFESENSE_TX_RX_UDP_IP, &target.sin_addr) != 1) {
        ESP_LOGE(TAG, "Invalid RX UDP IPv4 address");
        close(socket_fd); vTaskDelete(NULL); return;
    }
    uint32_t probe_sequence = 0;
    while (true) {
        (void)sendto(socket_fd, &probe_sequence, sizeof(probe_sequence), 0,
                     (struct sockaddr *)&target, sizeof(target));
        probe_sequence++;
        vTaskDelay(probe_delay_ticks);
    }
}
#endif

void app_main(void) {
    if (!migrate_pre_fix_test_queue()) {
        ESP_LOGE(TAG, "TX queue calibration migration failed; refusing to run");
        return;
    }
    if (delivery_queue_init_named(&queue, "sstx") != 0) {
        ESP_LOGE(TAG, "NVS delivery queue initialization failed; TX will not run without persistence");
        return;
    }
    const int repaired = delivery_queue_repair_missing_head(&queue);
    if (repaired < 0) {
        ESP_LOGE(TAG, "TX NVS queue head unreadable; refusing to discard records");
        return;
    }
    if (repaired > 0)
        ESP_LOGW(TAG, "Recovered TX NVS metadata past %d confirmed missing head slot(s)", repaired);
    ESP_LOGI(TAG, "Restored %u pending TX record(s) from NVS", delivery_queue_count(&queue));
    bme_ready = start_sensor();
    if (!bt_alert_start()) ESP_LOGW(TAG, "Bluetooth alert server unavailable; Wi-Fi queue remains primary");

    gas_adc_t mq135 = {0};
    const bool mq_ready = gas_adc_init(&mq135, MQ135_ADC_CHANNEL) == 0;
    if (!mq_ready) ESP_LOGW(TAG, "MQ-135 raw ADC GPIO34 initialization failed");

    bool wifi_ready = false;
#if CONFIG_SAFESENSE_TX_DIRECT_LAPTOP_AP
    wifi_ready = safesense_wifi_ap_start(CONFIG_SAFESENSE_TX_LAPTOP_AP_SSID,
                                        CONFIG_SAFESENSE_TX_LAPTOP_AP_PASSWORD) == 0;
    if (wifi_ready) {
        ESP_LOGI(TAG, "Direct laptop AP ready SSID=%s gateway=192.168.4.1",
                 CONFIG_SAFESENSE_TX_LAPTOP_AP_SSID);
        if (xTaskCreate(laptop_discovery_task, "laptop_discovery", 4096,
                        NULL, 4, NULL) != pdPASS)
            ESP_LOGE(TAG, "Laptop discovery task failed");
    } else ESP_LOGE(TAG, "Direct laptop AP failed to start");
#else
    if (CONFIG_SAFESENSE_TX_WIFI_SSID[0]) {
        wifi_ready = safesense_wifi_station_start(CONFIG_SAFESENSE_TX_WIFI_SSID,
                                        CONFIG_SAFESENSE_TX_WIFI_PASSWORD, 30000) == 0;
        if (!wifi_ready) ESP_LOGW(TAG, "Wi-Fi not ready; records remain in NVS");
    } else ESP_LOGW(TAG, "Wi-Fi SSID not configured; local sensing and NVS logging only");
#endif
#if !CONFIG_SAFESENSE_TX_DIRECT_LAPTOP_AP
    bool probe_started = false;
    if (wifi_ready && CONFIG_SAFESENSE_TX_RX_UDP_IP[0]) {
        probe_started = xTaskCreate(udp_probe_task, "csi_probe", 4096, NULL, 5, NULL) == pdPASS;
        if (!probe_started) ESP_LOGE(TAG, "CSI UDP probe task could not start");
    }
    if (wifi_ready && CONFIG_SAFESENSE_TX_RX_HTTP_URL[0]) flush_pending();
#endif

#if CONFIG_SAFESENSE_TX_SCENARIO_SERIAL_DEMO
    scenario_serial_loop();
    return;
#endif

    while (true) {
        const bool connected_now = transport_link_connected();
        if (connected_now && !wifi_ready)
            ESP_LOGI(TAG, "Wi-Fi connected after startup wait; resuming RX delivery");
        wifi_ready = connected_now;
#if !CONFIG_SAFESENSE_TX_DIRECT_LAPTOP_AP
        if (wifi_ready && !probe_started && CONFIG_SAFESENSE_TX_RX_UDP_IP[0]) {
            if (xTaskCreate(udp_probe_task, "csi_probe", 4096, NULL, 5, NULL) == pdPASS)
                probe_started = true;
        }
#endif
        if (!bme_ready) bme_ready = start_sensor();
        bme680_reading_t reading = {0};
        const bme680_status_t bme_status = bme_ready
            ? bme680_esp_idf_read_forced(&bme, &reading, 1000) : BME680_ERR_NOT_FOUND;
        if (bme_status != BME680_OK) {
            ESP_LOGW(TAG, "BME680 read unavailable: %d", bme_status);
            bme680_esp_idf_deinit(&bme);
            bme_ready = false;
        } else {
            ESP_LOGI(TAG, "BME680 T=%.2f C RH=%.2f %% P=%.2f Pa gas=%.0f ohm valid=%d stable=%d",
                     reading.temperature_c, reading.humidity_percent, reading.pressure_pa,
                     reading.gas_resistance_ohm, reading.gas_valid, reading.heat_stable);
        }
        const gas_sample_t mq_sample = mq_ready ? gas_adc_read(&mq135) : (gas_sample_t){.healthy=false};
        if (mq_sample.healthy) {
            ESP_LOGI(TAG, "MQ-135 AO GPIO34 raw ADC=%d (uncalibrated)", mq_sample.signal);
            if (mq_sample.signal == 0)
                ESP_LOGW(TAG, "MQ-135 ADC is zero; electrical signal/heater not verified");
        }
        else ESP_LOGW(TAG, "MQ-135 raw ADC unavailable");

        uint8_t alert_minutes = 0, alert_channel = 0;
        bool forecast_alert = bme_status == BME680_OK &&
            update_forecast_history(&reading, &mq_sample, &alert_minutes, &alert_channel);
#if CONFIG_SAFESENSE_TX_DIRECT_LAPTOP_AP
        portENTER_CRITICAL(&laptop_ip_lock);
        const bool udp_transport_test = test_alert_requested;
        test_alert_requested = false;
        portEXIT_CRITICAL(&laptop_ip_lock);
        const bool transport_test = udp_transport_test || bt_alert_take_test_request();
        if (transport_test) {
            forecast_alert = true;
            alert_minutes = 5;
            alert_channel = 0;
        }
#else
        const bool transport_test = false;
#endif
        delivery_record_t record = {0};
        make_event_id(record.event_id);
        const tx_sample_t sample = {
            .event_id = record.event_id, .tx_device_id = CONFIG_SAFESENSE_TX_DEVICE_ID,
            .sequence = sequence++, .bme_healthy = bme_status == BME680_OK,
            .temperature_c = reading.temperature_c, .humidity_pct = reading.humidity_percent,
            .pressure_pa = reading.pressure_pa,
            .gas_valid = bme_status == BME680_OK && reading.gas_valid && reading.heat_stable,
            .heat_stable = bme_status == BME680_OK && reading.heat_stable,
            .gas_resistance_ohm = reading.gas_resistance_ohm,
            .mq135_valid = mq_sample.healthy, .mq135_adc_raw = mq_sample.signal,
        };
        bool queued = false;
        bool event_valid = false;
        if (tx_format_json(record.payload, sizeof(record.payload), &sample) < 0 ||
            !add_alert_metadata(&record, forecast_alert, CONFIG_SAFESENSE_FORECAST_ROOM,
                                alert_minutes, alert_channel, transport_test))
            ESP_LOGE(TAG, "TX JSON could not be formatted; check device ID or sensor values");
        else {
            event_valid = true;
            if (delivery_queue_enqueue(&queue, &record) != 0)
                ESP_LOGE(TAG, "NVS queue full/write failed; pending=%u", delivery_queue_count(&queue));
            else {
                queued = true;
                ESP_LOGI(TAG, "Persisted event=%s pending=%u JSON=%s", record.event_id,
                         delivery_queue_count(&queue), record.payload);
            }
        }
        if (wifi_ready) flush_pending();
        const bool wifi_sample_acked = queued && delivery_queue_contains(&queue, record.event_id) == 0;
        if (event_valid && !wifi_sample_acked && bt_alert_connected()) {
            const bool bt_sample_stored = bt_alert_send_sample(record.event_id, record.payload, 1800);
            ESP_LOGI(TAG, "Bluetooth sensor event=%s laptop_stored=%s", record.event_id,
                     bt_sample_stored ? "YES" : "NO");
        }
        if (forecast_alert) {
            const bool wifi_acked = wifi_sample_acked;
            ESP_LOGW(TAG, "%s alert in %u min channel=%u event=%s NVS_STORED=%s WIFI_ACK=%s",
                     transport_test ? "Transport test" : "DEMO forecast range crossing",
                     alert_minutes, alert_channel, record.event_id,
                     queued ? "YES" : "NO", wifi_acked ? "YES" : "NO");
            if (!wifi_acked) {
                const bool bt_received = bt_alert_send(record.event_id,
                    CONFIG_SAFESENSE_FORECAST_ROOM, alert_minutes, alert_channel,
                    transport_test, 2500);
                ESP_LOGW(TAG, "Nearby laptop BT stored event=%s result=%s",
                         record.event_id, bt_received ? "CONFIRMED" : "UNCONFIRMED");
            }
        }
        vTaskDelay(pdMS_TO_TICKS(CONFIG_SAFESENSE_TX_SAMPLE_INTERVAL_SECONDS * 1000));
    }
}
