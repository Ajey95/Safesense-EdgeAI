#include "bme680_esp_idf.h"
#include "driver/gpio.h"
#include "driver/i2c_master.h"
#include "esp_event.h"
#include "esp_log.h"
#include "esp_netif.h"
#include "esp_timer.h"
#include "esp_wifi.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include "freertos/task.h"
#include "gas_risk.h"
#include "lwip/inet.h"
#include "lwip/sockets.h"
#include "node_protocol.h"
#include "nvs_flash.h"

#include <math.h>
#include <string.h>

#define PROBE_INTERVAL_MS 20u
#define REGISTRATION_TOKEN "SAFESENSE_NODE2_V1"

#ifdef CONFIG_SAFESENSE_SENSOR_LED_ACTIVE_HIGH
#define SENSOR_LED_ACTIVE_HIGH true
#else
#define SENSOR_LED_ACTIVE_HIGH false
#endif

static const char *TAG = "ss_node1";
static SemaphoreHandle_t state_lock;
static node_environment_t latest_environment;
static int64_t latest_sample_us;
static struct sockaddr_in registered_peer;
static bool peer_registered;

static void set_sensor_led(bool on)
{
    gpio_set_level(CONFIG_SAFESENSE_SENSOR_LED_GPIO,
                   on == SENSOR_LED_ACTIVE_HIGH ? 1 : 0);
}

static int start_softap(void)
{
    esp_err_t error = nvs_flash_init();
    if (error != ESP_OK && error != ESP_ERR_INVALID_STATE) {
        return -1;
    }
    error = esp_netif_init();
    if (error != ESP_OK && error != ESP_ERR_INVALID_STATE) {
        return -1;
    }
    error = esp_event_loop_create_default();
    if (error != ESP_OK && error != ESP_ERR_INVALID_STATE) {
        return -1;
    }
    if (esp_netif_create_default_wifi_ap() == NULL) {
        return -1;
    }
    wifi_init_config_t init = WIFI_INIT_CONFIG_DEFAULT();
    if (esp_wifi_init(&init) != ESP_OK) {
        return -1;
    }
    wifi_config_t config = {0};
    strlcpy((char *)config.ap.ssid, CONFIG_SAFESENSE_AP_SSID, sizeof(config.ap.ssid));
    strlcpy((char *)config.ap.password, CONFIG_SAFESENSE_AP_PASSWORD, sizeof(config.ap.password));
    config.ap.ssid_len = strlen(CONFIG_SAFESENSE_AP_SSID);
    config.ap.channel = CONFIG_SAFESENSE_AP_CHANNEL;
    config.ap.max_connection = 4u;
    config.ap.authmode = strlen(CONFIG_SAFESENSE_AP_PASSWORD) >= 8u
                             ? WIFI_AUTH_WPA2_PSK
                             : WIFI_AUTH_OPEN;
    if (esp_wifi_set_mode(WIFI_MODE_AP) != ESP_OK ||
        esp_wifi_set_config(WIFI_IF_AP, &config) != ESP_OK ||
        esp_wifi_start() != ESP_OK || esp_wifi_set_ps(WIFI_PS_NONE) != ESP_OK) {
        return -1;
    }
    ESP_LOGI(TAG, "SoftAP ready: %s channel %d", CONFIG_SAFESENSE_AP_SSID,
             CONFIG_SAFESENSE_AP_CHANNEL);
    return 0;
}

static bme680_status_t start_sensor(bme680_esp_idf_t *sensor)
{
    i2c_master_bus_handle_t bus;
    const i2c_master_bus_config_t bus_config = {
        .i2c_port = I2C_NUM_0,
        .sda_io_num = CONFIG_SAFESENSE_I2C_SDA_GPIO,
        .scl_io_num = CONFIG_SAFESENSE_I2C_SCL_GPIO,
        .clk_source = I2C_CLK_SRC_DEFAULT,
        .glitch_ignore_cnt = 7u,
        .flags.enable_internal_pullup = true,
    };
    if (i2c_new_master_bus(&bus_config, &bus) != ESP_OK) {
        return BME680_ERR_BUS;
    }
    const bool low_available =
        i2c_master_probe(bus, BME680_I2C_ADDRESS_LOW, 100) == ESP_OK;
    const bool high_available =
        i2c_master_probe(bus, BME680_I2C_ADDRESS_HIGH, 100) == ESP_OK;
    const uint8_t address = bme680_select_i2c_address(
        CONFIG_SAFESENSE_BME680_ADDRESS, low_available, high_available);
    if (address == 0u) {
        ESP_LOGE(TAG, "No BME680 response on I2C 0x76 or 0x77 (SDA=%d SCL=%d)",
                 CONFIG_SAFESENSE_I2C_SDA_GPIO, CONFIG_SAFESENSE_I2C_SCL_GPIO);
        i2c_del_master_bus(bus);
        return BME680_ERR_BUS;
    }
    ESP_LOGI(TAG, "BME680 detected at I2C 0x%02X (SDA=%d SCL=%d)", address,
             CONFIG_SAFESENSE_I2C_SDA_GPIO, CONFIG_SAFESENSE_I2C_SCL_GPIO);
    return bme680_esp_idf_init(sensor, bus, address, NULL);
}

static void sensor_task(void *argument)
{
    (void)argument;
    bme680_esp_idf_t sensor;
    gas_baseline_t baseline;
    gas_baseline_reset(&baseline);
    const gas_policy_t policy = {
        .warmup_samples = CONFIG_SAFESENSE_GAS_WARMUP_SAMPLES,
        .baseline_alpha = CONFIG_SAFESENSE_GAS_BASELINE_ALPHA_PERMILLE / 1000.0f,
        .warning_ratio = CONFIG_SAFESENSE_GAS_WARNING_PERCENT / 100.0f,
        .critical_ratio = CONFIG_SAFESENSE_GAS_CRITICAL_PERCENT / 100.0f,
    };
    const bme680_status_t init = start_sensor(&sensor);
    if (init != BME680_OK || !gas_policy_validate(&policy)) {
        ESP_LOGE(TAG, "BME680 unavailable or gas policy invalid: %d", init);
    }
    while (true) {
        bme680_reading_t reading = {0};
        gas_risk_t risk = GAS_RISK_UNAVAILABLE;
        float ratio = 0.0f;
        const bme680_status_t status = init == BME680_OK
                                           ? bme680_esp_idf_read_forced(&sensor, &reading, 500u)
                                           : init;
        if (status == BME680_OK) {
            const gas_sample_t gas = {
                .resistance_ohm = reading.gas_resistance_ohm,
                .gas_valid = reading.gas_valid,
                .heat_stable = reading.heat_stable,
            };
            risk = gas_risk_update(&baseline, &gas, &policy, &ratio);
        }
        node_environment_t update = {
            .flags = status == BME680_OK ? NODE_FLAG_SENSOR_HEALTHY : 0u,
            .temperature_milli_c = (int32_t)lroundf(reading.temperature_c * 1000.0f),
            .humidity_milli_percent = (uint32_t)lroundf(reading.humidity_percent * 1000.0f),
            .pressure_pa = (uint32_t)lroundf(reading.pressure_pa),
            .gas_resistance_ohm = (uint32_t)lroundf(reading.gas_resistance_ohm),
            .gas_baseline_ohm = (uint32_t)lroundf(baseline.baseline_ohm),
            .gas_ratio_q15 = ratio > 0.0f ? (uint16_t)lroundf(fminf(ratio, 1.999f) * 32768.0f) : 0u,
            .gas_risk = risk,
        };
        if (reading.gas_valid) {
            update.flags |= NODE_FLAG_GAS_VALID;
        }
        if (reading.heat_stable) {
            update.flags |= NODE_FLAG_HEAT_STABLE;
        }
        xSemaphoreTake(state_lock, portMAX_DELAY);
        latest_environment = update;
        latest_sample_us = esp_timer_get_time();
        xSemaphoreGive(state_lock);
        set_sensor_led(status == BME680_OK);
        ESP_LOGI(TAG, "BME680 status=%d T=%.2f RH=%.2f P=%.0f gas=%.0f risk=%d warmup=%lu/%u",
                 status, reading.temperature_c, reading.humidity_percent, reading.pressure_pa,
                 reading.gas_resistance_ohm, risk, (unsigned long)baseline.valid_samples,
                 policy.warmup_samples);
        vTaskDelay(pdMS_TO_TICKS(CONFIG_SAFESENSE_SENSOR_INTERVAL_MS));
    }
}

static void registration_task(void *argument)
{
    (void)argument;
    const int socket_fd = socket(AF_INET, SOCK_DGRAM, IPPROTO_IP);
    struct sockaddr_in address = {
        .sin_family = AF_INET,
        .sin_port = htons(CONFIG_SAFESENSE_REGISTRATION_PORT),
        .sin_addr.s_addr = htonl(INADDR_ANY),
    };
    if (socket_fd < 0 || bind(socket_fd, (struct sockaddr *)&address, sizeof(address)) != 0) {
        ESP_LOGE(TAG, "Registration socket failed");
        vTaskDelete(NULL);
    }
    while (true) {
        char token[32] = {0};
        struct sockaddr_in sender;
        socklen_t sender_length = sizeof(sender);
        const int received = recvfrom(socket_fd, token, sizeof(token) - 1u, 0,
                                      (struct sockaddr *)&sender, &sender_length);
        if (received == (int)strlen(REGISTRATION_TOKEN) &&
            memcmp(token, REGISTRATION_TOKEN, strlen(REGISTRATION_TOKEN)) == 0) {
            sender.sin_port = htons(CONFIG_SAFESENSE_PROBE_PORT);
            xSemaphoreTake(state_lock, portMAX_DELAY);
            const bool peer_changed = node_protocol_peer_changed(
                peer_registered, registered_peer.sin_addr.s_addr, sender.sin_addr.s_addr);
            registered_peer = sender;
            peer_registered = true;
            xSemaphoreGive(state_lock);
            if (peer_changed) {
                ESP_LOGI(TAG, "Node 2 registered from %s", inet_ntoa(sender.sin_addr));
            }
        }
    }
}

static void probe_task(void *argument)
{
    (void)argument;
    const int socket_fd = socket(AF_INET, SOCK_DGRAM, IPPROTO_IP);
    uint32_t sequence = 0u;
    while (true) {
        node_environment_t reading;
        struct sockaddr_in peer;
        bool send = false;
        int64_t sample_time;
        xSemaphoreTake(state_lock, portMAX_DELAY);
        reading = latest_environment;
        sample_time = latest_sample_us;
        if (peer_registered) {
            peer = registered_peer;
            send = true;
        }
        xSemaphoreGive(state_lock);
        if (send && socket_fd >= 0) {
            const int64_t now = esp_timer_get_time();
            reading.sequence = sequence++;
            reading.uptime_ms = (uint32_t)(now / 1000);
            reading.sample_age_ms = sample_time > 0 ? (uint32_t)((now - sample_time) / 1000) : UINT32_MAX;
            uint8_t packet[NODE_PROTOCOL_PACKET_SIZE];
            if (node_protocol_encode(&reading, packet, sizeof(packet)) == NODE_PROTOCOL_OK) {
                (void)sendto(socket_fd, packet, sizeof(packet), 0,
                             (struct sockaddr *)&peer, sizeof(peer));
            }
        }
        vTaskDelay(pdMS_TO_TICKS(PROBE_INTERVAL_MS));
    }
}

void app_main(void)
{
    const gpio_config_t led = {
        .pin_bit_mask = 1ULL << CONFIG_SAFESENSE_SENSOR_LED_GPIO,
        .mode = GPIO_MODE_OUTPUT,
    };
    ESP_ERROR_CHECK(gpio_config(&led));
    set_sensor_led(false);
    state_lock = xSemaphoreCreateMutex();
    if (state_lock == NULL || start_softap() != 0) {
        ESP_LOGE(TAG, "Node 1 startup failed");
        return;
    }
    xTaskCreate(sensor_task, "bme680", 6144, NULL, 5, NULL);
    xTaskCreate(registration_task, "register", 4096, NULL, 5, NULL);
    xTaskCreate(probe_task, "probe50hz", 4096, NULL, 5, NULL);
}
