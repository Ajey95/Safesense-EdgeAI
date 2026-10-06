#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "cJSON.h"
#include "csi_capture_esp_idf.h"
#include "csi_pipeline.h"
#include "delivery_queue.h"
#include "esp_event.h"
#include "esp_http_server.h"
#include "esp_log.h"
#include "esp_netif.h"
#include "esp_timer.h"
#include "esp_wifi.h"
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "freertos/task.h"
#include "lwip/inet.h"
#include "lwip/sockets.h"
#include "nvs_flash.h"
#include "rx_protocol.h"

#define CSI_PACKET_PORT 3333

static const char *TAG = "safesense_rx";
static delivery_queue_t pending;
static QueueHandle_t csi_queue;
static csi_pipeline_t csi_pipeline;
static portMUX_TYPE csi_lock = portMUX_INITIALIZER_UNLOCKED;
static uint32_t csi_frames;
static uint32_t csi_recent_frames;
static uint32_t csi_windows;
static int8_t csi_rssi;
static int64_t csi_last_us;
static int64_t csi_period_start_us;

/* WISDOM uses IQ pairs 6:31 and 33:58 from the classic ESP32 LLTF vector.
 * Export only those 50 pairs so serial capture remains bounded at 115200 baud.
 * The invalid first word affects pairs 0 and 1, which are not selected. */
static void emit_wisdom_csi(const csi_packet_t *packet, uint32_t sequence) {
    static const char alphabet[] =
        "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    uint8_t selected[100];
    char encoded[137];
    unsigned count = 0;
    for (unsigned carrier = 6; carrier < 31; ++carrier) {
        selected[count++] = (uint8_t)packet->iq[carrier * 2];
        selected[count++] = (uint8_t)packet->iq[carrier * 2 + 1];
    }
    for (unsigned carrier = 33; carrier < 58; ++carrier) {
        selected[count++] = (uint8_t)packet->iq[carrier * 2];
        selected[count++] = (uint8_t)packet->iq[carrier * 2 + 1];
    }
    unsigned output = 0;
    for (unsigned input = 0; input < sizeof(selected); input += 3) {
        const uint32_t chunk = ((uint32_t)selected[input] << 16) |
                               ((uint32_t)(input + 1 < sizeof(selected) ? selected[input + 1] : 0) << 8) |
                               (input + 2 < sizeof(selected) ? selected[input + 2] : 0);
        encoded[output++] = alphabet[(chunk >> 18) & 63];
        encoded[output++] = alphabet[(chunk >> 12) & 63];
        encoded[output++] = input + 1 < sizeof(selected) ? alphabet[(chunk >> 6) & 63] : '=';
        encoded[output++] = input + 2 < sizeof(selected) ? alphabet[chunk & 63] : '=';
    }
    encoded[output] = '\0';
    csi_capture_stats_t capture;
    csi_capture_get_stats(&capture);
    printf("WISDOM_CSI,1,%lu,%lld,%d,%u,%lu,%s\n", (unsigned long)sequence,
           (long long)packet->received_us, (int)packet->rssi_dbm,
           packet->first_word_invalid ? 1u : 0u,
           (unsigned long)capture.queue_full, encoded);
}

static void receipt_key(uint8_t slot, char key[8]) {
    snprintf(key, 8, "r%02u", slot);
}

static void reply_json(httpd_req_t *request, const char *status, const char *body) {
    httpd_resp_set_status(request, status);
    httpd_resp_set_type(request, "application/json");
    httpd_resp_send(request, body, HTTPD_RESP_USE_STRLEN);
}

static int read_body(httpd_req_t *request, char body[RX_MAX_JSON_BYTES]) {
    if (request->content_len <= 0 || request->content_len >= RX_MAX_JSON_BYTES) return -1;
    int used = 0;
    while (used < request->content_len) {
        const int got = httpd_req_recv(request, body + used, request->content_len - used);
        if (got <= 0) return -1;
        used += got;
    }
    body[used] = '\0';
    return used;
}

static int find_slot(const char *event_id) {
    for (uint8_t offset = 0; offset < pending.count; ++offset) {
        const uint8_t slot = (pending.head + offset) % DELIVERY_QUEUE_CAPACITY;
        char key[8];
        snprintf(key, sizeof(key), "e%02u", slot);
        delivery_record_t record;
        size_t size = sizeof(record);
        if (nvs_get_blob(pending.handle, key, &record, &size) != ESP_OK ||
            size != sizeof(record)) return -1;
        if (strcmp(record.event_id, event_id) == 0) return slot;
    }
    return -1;
}

static esp_err_t receive_tx(httpd_req_t *request) {
    char body[RX_MAX_JSON_BYTES];
    const int size = read_body(request, body);
    rx_event_info_t info;
    if (size < 0 || rx_parse_tx_event(body, (size_t)size, &info) != 0) {
        reply_json(request, "400 Bad Request", "{\"error\":\"invalid V1 TX telemetry\"}");
        return ESP_OK;
    }
    const int existing = delivery_queue_contains(&pending, info.event_id);
    if (existing < 0) {
        reply_json(request, "503 Service Unavailable", "{\"error\":\"RX queue unreadable\"}");
        return ESP_OK;
    }
    if (existing == 0) {
        delivery_record_t record = {0};
        snprintf(record.event_id, sizeof(record.event_id), "%s", info.event_id);
        memcpy(record.payload, body, (size_t)size + 1u);
        if (delivery_queue_enqueue(&pending, &record) != 0) {
            reply_json(request, "503 Service Unavailable", "{\"error\":\"RX queue full or NVS write failed\"}");
            return ESP_OK;
        }
    }
    const int slot = find_slot(info.event_id);
    if (slot < 0) {
        reply_json(request, "503 Service Unavailable", "{\"error\":\"RX queued record unreadable\"}");
        return ESP_OK;
    }
    char key[8];
    receipt_key((uint8_t)slot, key);
    uint32_t received_ms;
    if (existing == 0 || nvs_get_u32(pending.handle, key, &received_ms) != ESP_OK) {
        received_ms = (uint32_t)(esp_timer_get_time() / 1000);
        if (nvs_set_u32(pending.handle, key, received_ms) != ESP_OK ||
            nvs_commit(pending.handle) != ESP_OK) {
            reply_json(request, "503 Service Unavailable", "{\"error\":\"RX receipt write failed\"}");
            return ESP_OK;
        }
    }
    char response[128];
    snprintf(response, sizeof(response), "{\"event_id\":\"%s\",\"status\":\"ACCEPTED\"}", info.event_id);
    ESP_LOGI(TAG, "HTTP TX accepted event=%s from=%s pending=%u", info.event_id,
             info.tx_device_id, delivery_queue_count(&pending));
    reply_json(request, "202 Accepted", response);
    return ESP_OK;
}

static esp_err_t get_pending(httpd_req_t *request) {
    if (delivery_queue_count(&pending) == 0) {
        httpd_resp_set_status(request, "204 No Content");
        httpd_resp_send(request, NULL, 0);
        return ESP_OK;
    }
    delivery_record_t record;
    if (delivery_queue_peek(&pending, &record) != 0) {
        reply_json(request, "503 Service Unavailable", "{\"error\":\"RX queue unreadable\"}");
        return ESP_OK;
    }
    cJSON *root = cJSON_CreateObject();
    cJSON *tx = cJSON_Parse(record.payload);
    cJSON *rx = cJSON_CreateObject();
    if (!root || !tx || !rx) {
        cJSON_Delete(root); cJSON_Delete(tx); cJSON_Delete(rx);
        reply_json(request, "503 Service Unavailable", "{\"error\":\"RX JSON allocation failed\"}");
        return ESP_OK;
    }
    cJSON_AddStringToObject(root, "event_id", record.event_id);
    cJSON_AddItemToObject(root, "tx", tx);
    cJSON_AddItemToObject(root, "rx", rx);
    cJSON_AddStringToObject(rx, "device_id", CONFIG_SAFESENSE_RX_DEVICE_ID);
    cJSON_AddStringToObject(rx, "transport", "HTTP POST");
    cJSON_AddBoolToObject(rx, "queue_persisted", true);
    char key[8]; receipt_key(pending.head, key);
    uint32_t received_ms;
    if (nvs_get_u32(pending.handle, key, &received_ms) == ESP_OK)
        cJSON_AddNumberToObject(rx, "received_uptime_ms", received_ms);
    else cJSON_AddNullToObject(rx, "received_uptime_ms");

    const int64_t now = esp_timer_get_time();
    uint32_t frames, recent, windows;
    int8_t rssi;
    int64_t last, period;
    portENTER_CRITICAL(&csi_lock);
    frames = csi_frames; recent = csi_recent_frames; windows = csi_windows;
    rssi = csi_rssi; last = csi_last_us; period = csi_period_start_us;
    portEXIT_CRITICAL(&csi_lock);
    const int64_t elapsed = now - period;
    const double rate = elapsed > 0 && elapsed <= 5000000 ?
        (double)recent * 1000000.0 / (double)elapsed : 0.0;
    cJSON_AddNumberToObject(rx, "csi_frames", frames);
    cJSON_AddNumberToObject(rx, "csi_windows", windows);
    cJSON_AddNumberToObject(rx, "csi_packet_rate_hz", rate);
    csi_capture_stats_t capture;
    csi_capture_get_stats(&capture);
    cJSON_AddNumberToObject(rx, "csi_raw_callbacks", capture.callbacks);
    cJSON_AddNumberToObject(rx, "csi_unexpected_length", capture.unexpected_length);
    cJSON_AddNumberToObject(rx, "csi_invalid_first_word", capture.first_word_invalid);
    cJSON_AddNumberToObject(rx, "csi_min_measured_subcarriers",
                            capture.first_word_invalid > 0 ? 47 : CSI_DATA_SUBCARRIERS);
    cJSON_AddNumberToObject(rx, "csi_queue_drops", capture.queue_full);
    cJSON_AddNumberToObject(rx, "csi_last_length", capture.last_length);
    if (last > 0) {
        cJSON_AddNumberToObject(rx, "csi_rssi_dbm", rssi);
        cJSON_AddNumberToObject(rx, "seen_age_ms", (now - last) / 1000);
    } else {
        cJSON_AddNullToObject(rx, "csi_rssi_dbm");
        cJSON_AddNullToObject(rx, "seen_age_ms");
    }
    char *encoded = cJSON_PrintUnformatted(root);
    cJSON_Delete(root);
    if (!encoded) {
        reply_json(request, "503 Service Unavailable", "{\"error\":\"RX JSON encoding failed\"}");
        return ESP_OK;
    }
    reply_json(request, "200 OK", encoded);
    cJSON_free(encoded);
    return ESP_OK;
}

static esp_err_t acknowledge_forward(httpd_req_t *request) {
    char body[RX_MAX_JSON_BYTES];
    char event_id[64];
    const int size = read_body(request, body);
    if (size < 0 || rx_parse_forward_ack(body, (size_t)size, event_id) != 0) {
        reply_json(request, "400 Bad Request", "{\"error\":\"invalid forward ACK\"}");
        return ESP_OK;
    }
    const uint8_t slot = pending.head;
    if (delivery_queue_ack_head(&pending, event_id) != 0) {
        reply_json(request, "409 Conflict", "{\"error\":\"event is not RX queue head\"}");
        return ESP_OK;
    }
    char key[8]; receipt_key(slot, key);
    (void)nvs_erase_key(pending.handle, key);
    (void)nvs_commit(pending.handle);
    char response[128];
    snprintf(response, sizeof(response), "{\"event_id\":\"%s\",\"status\":\"ACKED\"}", event_id);
    ESP_LOGI(TAG, "Host forward ACK event=%s pending=%u", event_id, delivery_queue_count(&pending));
    reply_json(request, "200 OK", response);
    return ESP_OK;
}

static void csi_task(void *unused) {
    (void)unused;
    csi_pipeline_init(&csi_pipeline);
    csi_packet_t packet;
    while (true) {
        if (xQueueReceive(csi_queue, &packet, portMAX_DELAY) != pdTRUE) continue;
        bool window_ready = false;
        if (csi_pipeline_push_masked(&csi_pipeline, packet.iq, sizeof(packet.iq),
                                     packet.first_word_invalid, &window_ready) != CSI_OK) continue;
        portENTER_CRITICAL(&csi_lock);
        if (packet.received_us - csi_period_start_us > 5000000) {
            csi_period_start_us = packet.received_us;
            csi_recent_frames = 0;
        }
        csi_frames++;
        const uint32_t sequence = csi_frames;
        csi_recent_frames++;
        if (window_ready) csi_windows++;
        csi_last_us = packet.received_us;
        csi_rssi = packet.rssi_dbm;
        portEXIT_CRITICAL(&csi_lock);
        emit_wisdom_csi(&packet, sequence);
        if (window_ready) ESP_LOGI(TAG, "CSI window ready count=%lu (activity UNKNOWN; no validated model)",
                                   (unsigned long)csi_windows);
    }
}

static void udp_probe_listener(void *unused) {
    (void)unused;
    const int socket_fd = socket(AF_INET, SOCK_DGRAM, IPPROTO_IP);
    if (socket_fd < 0) { ESP_LOGE(TAG, "UDP probe socket creation failed"); vTaskDelete(NULL); return; }
    struct sockaddr_in address = {.sin_family = AF_INET, .sin_port = htons(CSI_PACKET_PORT),
                                  .sin_addr.s_addr = htonl(INADDR_ANY)};
    if (bind(socket_fd, (struct sockaddr *)&address, sizeof(address)) != 0) {
        ESP_LOGE(TAG, "UDP probe bind failed"); close(socket_fd); vTaskDelete(NULL); return;
    }
    uint32_t count = 0;
    uint8_t data[64];
    while (true) {
        if (recv(socket_fd, data, sizeof(data), 0) <= 0) continue;
        if (++count % 500u == 0) {
            csi_capture_stats_t capture;
            csi_capture_get_stats(&capture);
            portENTER_CRITICAL(&csi_lock);
            const uint32_t frames_snapshot = csi_frames;
            portEXIT_CRITICAL(&csi_lock);
            ESP_LOGI(TAG, "RX UDP=%lu CSI cb=%lu len=%u bad_len=%lu first_invalid=%lu queued=%lu dropped=%lu frames=%lu",
                     (unsigned long)count, (unsigned long)capture.callbacks,
                     (unsigned)capture.last_length, (unsigned long)capture.unexpected_length,
                     (unsigned long)capture.first_word_invalid, (unsigned long)capture.queued,
                     (unsigned long)capture.queue_full, (unsigned long)frames_snapshot);
        }
    }
}

static bool start_ap(void) {
    if (strlen(CONFIG_SAFESENSE_RX_AP_SSID) == 0 ||
        strlen(CONFIG_SAFESENSE_RX_AP_SSID) >= sizeof(((wifi_config_t *)0)->ap.ssid) ||
        strlen(CONFIG_SAFESENSE_RX_AP_PASSWORD) < 8 ||
        strlen(CONFIG_SAFESENSE_RX_AP_PASSWORD) > 63) return false;
    if (esp_netif_init() != ESP_OK || esp_event_loop_create_default() != ESP_OK ||
        !esp_netif_create_default_wifi_ap()) return false;
    wifi_init_config_t initial = WIFI_INIT_CONFIG_DEFAULT();
    if (esp_wifi_init(&initial) != ESP_OK) return false;
    wifi_config_t config = {0};
    snprintf((char *)config.ap.ssid, sizeof(config.ap.ssid), "%s", CONFIG_SAFESENSE_RX_AP_SSID);
    snprintf((char *)config.ap.password, sizeof(config.ap.password), "%s", CONFIG_SAFESENSE_RX_AP_PASSWORD);
    config.ap.ssid_len = strlen(CONFIG_SAFESENSE_RX_AP_SSID);
    config.ap.channel = 1;
    config.ap.max_connection = 4;
    config.ap.authmode = WIFI_AUTH_WPA2_PSK;
    if (esp_wifi_set_mode(WIFI_MODE_AP) != ESP_OK ||
        esp_wifi_set_config(WIFI_IF_AP, &config) != ESP_OK ||
        esp_wifi_start() != ESP_OK) return false;
    ESP_LOGI(TAG, "RX AP SSID=%s gateway=192.168.4.1", CONFIG_SAFESENSE_RX_AP_SSID);
    return true;
}

void app_main(void) {
    if (delivery_queue_init_named(&pending, "ssrx") != 0) {
        ESP_LOGE(TAG, "RX NVS queue unavailable; refusing to ACK TX");
        return;
    }
    ESP_LOGI(TAG, "Restored %u pending RX record(s) from NVS", delivery_queue_count(&pending));
    if (!start_ap()) { ESP_LOGE(TAG, "RX AP startup failed"); return; }
    csi_period_start_us = esp_timer_get_time();
    csi_queue = xQueueCreate(32, sizeof(csi_packet_t));
    if (!csi_queue || csi_capture_start(csi_queue) != 0) {
        ESP_LOGW(TAG, "CSI capture unavailable; HTTP/NVS gateway remains active");
    } else xTaskCreate(csi_task, "csi_rx", 6144, NULL, 5, NULL);
    xTaskCreate(udp_probe_listener, "udp_probe_rx", 3072, NULL, 4, NULL);
    httpd_handle_t server = NULL;
    httpd_config_t config = HTTPD_DEFAULT_CONFIG();
    config.max_uri_handlers = 3;
    /* Validation, NVS queue traversal and JSON serialization share this task. */
    config.stack_size = 10240;
    if (httpd_start(&server, &config) != ESP_OK) {
        ESP_LOGE(TAG, "RX HTTP server startup failed"); return;
    }
    const httpd_uri_t receive = {.uri = "/api/v1/tx/environment", .method = HTTP_POST,
                                 .handler = receive_tx};
    const httpd_uri_t poll = {.uri = "/api/v1/pending", .method = HTTP_GET,
                              .handler = get_pending};
    const httpd_uri_t ack = {.uri = "/api/v1/forward-ack", .method = HTTP_POST,
                             .handler = acknowledge_forward};
    if (httpd_register_uri_handler(server, &receive) != ESP_OK ||
        httpd_register_uri_handler(server, &poll) != ESP_OK ||
        httpd_register_uri_handler(server, &ack) != ESP_OK) {
        ESP_LOGE(TAG, "RX HTTP endpoint registration failed");
        httpd_stop(server); return;
    }
    ESP_LOGI(TAG, "RX HTTP endpoints active; telemetry requires matching event ACK");
}
