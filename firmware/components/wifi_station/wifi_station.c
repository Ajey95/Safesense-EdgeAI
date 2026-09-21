#include "wifi_station.h"

#include <string.h>

#include "esp_event.h"
#include "esp_netif.h"
#include "esp_wifi.h"
#include "freertos/FreeRTOS.h"
#include "freertos/event_groups.h"

#define CONNECTED_BIT BIT0

static EventGroupHandle_t connection_events;

static void network_event(void *arg, esp_event_base_t base, int32_t id, void *data) {
    (void)arg; (void)data;
    if (base == WIFI_EVENT && id == WIFI_EVENT_STA_START) esp_wifi_connect();
    if (base == WIFI_EVENT && id == WIFI_EVENT_STA_DISCONNECTED) {
        xEventGroupClearBits(connection_events, CONNECTED_BIT);
        esp_wifi_connect();
    }
    if (base == IP_EVENT && id == IP_EVENT_STA_GOT_IP) xEventGroupSetBits(connection_events, CONNECTED_BIT);
}

int wifi_station_start(const char *ssid, const char *password, uint32_t timeout_ms) {
    if (!ssid || !ssid[0] || !password || !timeout_ms || strlen(ssid) > 32 || strlen(password) > 64) return -1;
    const esp_err_t netif = esp_netif_init();
    if (netif != ESP_OK && netif != ESP_ERR_INVALID_STATE) return -1;
    const esp_err_t event_loop = esp_event_loop_create_default();
    if (event_loop != ESP_OK && event_loop != ESP_ERR_INVALID_STATE) return -1;
    if (!esp_netif_create_default_wifi_sta()) return -1;
    connection_events = xEventGroupCreate();
    if (!connection_events) return -1;
    wifi_init_config_t initial = WIFI_INIT_CONFIG_DEFAULT();
    initial.nvs_enable = false;
    if (esp_wifi_init(&initial) != ESP_OK) return -1;
    if (esp_event_handler_register(WIFI_EVENT, ESP_EVENT_ANY_ID, network_event, NULL) != ESP_OK ||
        esp_event_handler_register(IP_EVENT, IP_EVENT_STA_GOT_IP, network_event, NULL) != ESP_OK) return -1;
    wifi_config_t config = {0};
    strlcpy((char *)config.sta.ssid, ssid, sizeof(config.sta.ssid));
    strlcpy((char *)config.sta.password, password, sizeof(config.sta.password));
    config.sta.threshold.authmode = password[0] ? WIFI_AUTH_WPA2_PSK : WIFI_AUTH_OPEN;
    if (esp_wifi_set_mode(WIFI_MODE_STA) != ESP_OK || esp_wifi_set_config(WIFI_IF_STA, &config) != ESP_OK ||
        esp_wifi_start() != ESP_OK || esp_wifi_set_ps(WIFI_PS_NONE) != ESP_OK) return -1;
    return (xEventGroupWaitBits(connection_events, CONNECTED_BIT, pdFALSE, pdTRUE, pdMS_TO_TICKS(timeout_ms)) & CONNECTED_BIT) ? 0 : -1;
}
