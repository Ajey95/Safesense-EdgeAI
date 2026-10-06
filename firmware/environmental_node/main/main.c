#include <stdio.h>
#include <string.h>

#include "bme280_driver.h"
#include "bme280_esp_idf.h"
#include "delivery_mqtt.h"
#include "delivery_queue.h"
#include "driver/i2c_master.h"
#include "esp_err.h"
#include "esp_event.h"
#include "esp_log.h"
#include "esp_netif.h"
#include "esp_random.h"
#include "esp_system.h"
#include "esp_wifi.h"
#include "freertos/FreeRTOS.h"
#include "freertos/event_groups.h"
#include "freertos/task.h"
#include "gas_adc_esp_idf.h"

#define I2C_SDA_GPIO 21
#define I2C_SCL_GPIO 22
#define WIFI_CONNECTED_BIT BIT0

static const char *TAG = "safesense_env";
static EventGroupHandle_t wifi_events;
static delivery_queue_t delivery_queue;

static void log_gas_adc(gas_adc_t *gas) {
    const gas_sample_t sample = gas_adc_read(gas);
    if (sample.healthy) ESP_LOGI(TAG, "MQ-135 AO GPIO34 raw ADC=%d (uncalibrated)", sample.signal);
    else ESP_LOGW(TAG, "MQ-135 AO GPIO34 ADC read failed");
}

static void wifi_event(void *arg, esp_event_base_t base, int32_t id, void *data) {
    (void)arg; (void)data;
    if (base == WIFI_EVENT && id == WIFI_EVENT_STA_START) esp_wifi_connect();
    if (base == WIFI_EVENT && id == WIFI_EVENT_STA_DISCONNECTED) {
        xEventGroupClearBits(wifi_events, WIFI_CONNECTED_BIT);
        esp_wifi_connect();
    }
    if (base == IP_EVENT && id == IP_EVENT_STA_GOT_IP) xEventGroupSetBits(wifi_events, WIFI_CONNECTED_BIT);
}

static int wifi_start(void) {
    if (esp_netif_init() != ESP_OK || esp_event_loop_create_default() != ESP_OK) return -1;
    if (!esp_netif_create_default_wifi_sta()) return -1;
    wifi_events = xEventGroupCreate();
    if (!wifi_events) return -1;
    wifi_init_config_t initial = WIFI_INIT_CONFIG_DEFAULT();
    if (esp_wifi_init(&initial) != ESP_OK) return -1;
    if (esp_event_handler_register(WIFI_EVENT, ESP_EVENT_ANY_ID, wifi_event, NULL) != ESP_OK ||
        esp_event_handler_register(IP_EVENT, IP_EVENT_STA_GOT_IP, wifi_event, NULL) != ESP_OK) return -1;
    wifi_config_t config = {0};
    strlcpy((char *)config.sta.ssid, CONFIG_SAFESENSE_WIFI_SSID, sizeof(config.sta.ssid));
    strlcpy((char *)config.sta.password, CONFIG_SAFESENSE_WIFI_PASSWORD, sizeof(config.sta.password));
    config.sta.threshold.authmode = strlen(CONFIG_SAFESENSE_WIFI_PASSWORD) ? WIFI_AUTH_WPA2_PSK : WIFI_AUTH_OPEN;
    if (esp_wifi_set_mode(WIFI_MODE_STA) != ESP_OK || esp_wifi_set_config(WIFI_IF_STA, &config) != ESP_OK) return -1;
    return esp_wifi_start() == ESP_OK ? 0 : -1;
}

static int sensor_start(bme280_t *bme) {
    i2c_master_bus_handle_t i2c_bus;
    const i2c_master_bus_config_t bus_config = {
        .i2c_port = I2C_NUM_0, .sda_io_num = I2C_SDA_GPIO, .scl_io_num = I2C_SCL_GPIO,
        .clk_source = I2C_CLK_SRC_DEFAULT, .glitch_ignore_cnt = 7, .flags.enable_internal_pullup = true,
    };
    if (i2c_new_master_bus(&bus_config, &i2c_bus) != ESP_OK) return -1;
    static bme280_esp_idf_bus_t transport;
    const uint8_t addresses[] = {BME280_I2C_ADDRESS_LOW, BME280_I2C_ADDRESS_HIGH};
    for (size_t i = 0; i < sizeof(addresses); ++i) {
        const uint8_t address = addresses[i];
        const esp_err_t probe = i2c_master_probe(i2c_bus, address, 100);
        ESP_LOGI(TAG, "I2C probe 0x%02x on SDA=%d SCL=%d: %s", address, I2C_SDA_GPIO,
                 I2C_SCL_GPIO, esp_err_to_name(probe));
        if (probe != ESP_OK) continue;
        const i2c_device_config_t sensor_config = {
            .dev_addr_length = I2C_ADDR_BIT_LEN_7, .device_address = address, .scl_speed_hz = 100000,
        };
        i2c_master_dev_handle_t sensor;
        if (i2c_master_bus_add_device(i2c_bus, &sensor_config, &sensor) != ESP_OK) continue;
        const uint8_t chip_id_reg = 0xD0;
        uint8_t chip_id = 0;
        const esp_err_t id_result = i2c_master_transmit_receive(sensor, &chip_id_reg, 1, &chip_id, 1, 100);
        if (id_result == ESP_OK) ESP_LOGI(TAG, "I2C 0x%02x chip ID: 0x%02x (BME280 expects 0x60)", address, chip_id);
        else ESP_LOGW(TAG, "I2C 0x%02x chip ID read: %s", address, esp_err_to_name(id_result));
        transport.handle = sensor;
        bme280_bus_t bus;
        bme280_esp_idf_make_bus(&bus, &transport);
        const bme280_status_t status = bme280_init(bme, &bus, address, NULL);
        if (status == BME280_OK) {
            ESP_LOGI(TAG, "%s ready at 0x%02x", bme->humidity_available ? "BME280" : "BMP280-compatible", address);
            return 0;
        }
        ESP_LOGW(TAG, "BME280 init at 0x%02x failed: %d", address, status);
    }
    return -1;
}

static int queue_reading(const bme280_reading_t *reading, uint32_t sequence) {
    if (!reading || !reading->humidity_available) return -1;
    delivery_record_t record = {0};
    snprintf(record.event_id, sizeof(record.event_id), "env-%08lx-%08lx", (unsigned long)esp_random(), (unsigned long)sequence);
    const int length = snprintf(record.payload, sizeof(record.payload),
        "{\"event_id\":\"%s\",\"device_id\":\"%s\",\"observed_at\":null,\"firmware_version\":\"esp32-review-0.2\","
        "\"environment\":{\"temperature_c\":%.2f,\"humidity_pct\":%.2f,\"pressure_pa\":%.2f,\"gas_risk\":\"UNAVAILABLE\",\"sensor_healthy\":true},"
        "\"csi\":{\"activity\":\"UNKNOWN\",\"confidence\":0,\"quality\":\"UNAVAILABLE\",\"tx_node\":\"UNKNOWN\",\"rx_node\":\"UNKNOWN\",\"packet_rate_hz\":0,\"rssi_dbm\":-127,\"is_fresh\":false},"
        "\"system\":{\"mqtt\":\"%s\",\"local_storage\":\"OK\",\"esp32_status\":\"ONLINE\"}}",
        record.event_id, CONFIG_SAFESENSE_DEVICE_ID, reading->temperature_c, reading->humidity_percent, reading->pressure_pa,
        delivery_mqtt_is_connected() ? "CONNECTED" : "DISCONNECTED");
    if (length < 0 || length >= (int)sizeof(record.payload)) return -1;
    return delivery_queue_enqueue(&delivery_queue, &record);
}

void app_main(void) {
    if (delivery_queue_init(&delivery_queue) != 0) {
        ESP_LOGE(TAG, "NVS delivery queue initialization failed");
        return;
    }
    ESP_LOGI(TAG, "Restored %u pending telemetry record(s) from NVS", delivery_queue_count(&delivery_queue));

    gas_adc_t gas;
    const bool gas_ready = gas_adc_init(&gas, ADC_CHANNEL_6) == 0;
    if (!gas_ready) ESP_LOGW(TAG, "MQ-135 AO GPIO34 ADC initialization failed");

    bme280_t bme;
    if (sensor_start(&bme) != 0) {
        ESP_LOGE(TAG, "BME280 initialization failed");
        if (gas_ready) {
            for (int i = 0; i < 10; ++i) {
                log_gas_adc(&gas);
                vTaskDelay(pdMS_TO_TICKS(1000));
            }
        }
        return;
    }
    if (bme.humidity_available) {
        if (wifi_start() != 0) ESP_LOGW(TAG, "Wi-Fi startup failed; readings will remain in NVS");
        const delivery_mqtt_config_t mqtt = {
            .broker_uri = CONFIG_SAFESENSE_MQTT_BROKER_URI,
            .device_id = CONFIG_SAFESENSE_DEVICE_ID,
            .server_certificate = NULL,
            .queue = &delivery_queue,
        };
        if (delivery_mqtt_start(&mqtt) != 0) ESP_LOGW(TAG, "MQTT startup failed; readings will remain in NVS");
    } else {
        ESP_LOGW(TAG, "Humidity unavailable; BMP280-compatible readings will not be queued for the BME280 telemetry schema");
    }

    uint32_t sequence = 0;
    while (true) {
        if (gas_ready) log_gas_adc(&gas);
        bme280_reading_t reading;
        const bme280_status_t status = bme280_read_forced(&bme, &reading, 50);
        if (status == BME280_OK) {
            if (!reading.humidity_available) {
                ESP_LOGI(TAG, "BMP280-compatible reading: T=%.2fC P=%.2fPa RH=UNAVAILABLE", reading.temperature_c, reading.pressure_pa);
            } else if (queue_reading(&reading, sequence++) == 0) {
                ESP_LOGI(TAG, "Persisted reading; pending=%u T=%.2fC RH=%.2f%% P=%.2fPa", delivery_queue_count(&delivery_queue), reading.temperature_c, reading.humidity_percent, reading.pressure_pa);
                delivery_mqtt_flush();
            } else {
                ESP_LOGW(TAG, "Persistent queue full or write failed; pending=%u", delivery_queue_count(&delivery_queue));
            }
        } else {
            ESP_LOGW(TAG, "BME280 read failed: %d", status);
        }
        vTaskDelay(pdMS_TO_TICKS(CONFIG_SAFESENSE_SAMPLE_INTERVAL_SECONDS * 1000));
    }
}
