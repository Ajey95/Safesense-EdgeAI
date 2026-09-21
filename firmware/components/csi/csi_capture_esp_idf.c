#include "csi_capture_esp_idf.h"
#include <string.h>
#include "esp_timer.h"
#include "esp_wifi.h"

static QueueHandle_t queue_handle;
static volatile uint32_t dropped_packets;
static void csi_callback(void *context, wifi_csi_info_t *info) {
    (void)context;
    if (!queue_handle || !info || info->len != CSI_RAW_IQ_BYTES || !info->buf) return;
    csi_packet_t packet = {.rssi_dbm = info->rx_ctrl.rssi, .first_word_invalid = info->first_word_invalid, .received_us = esp_timer_get_time()};
    memcpy(packet.iq, info->buf, CSI_RAW_IQ_BYTES);
    if (xQueueSend(queue_handle, &packet, 0) != pdTRUE) {
        dropped_packets++; /* Observable overload; never block the Wi-Fi task. */
    }
}
int csi_capture_start(QueueHandle_t destination_queue) {
    if (!destination_queue) return -1;
    queue_handle = destination_queue; dropped_packets = 0u;
    wifi_csi_config_t config = {.lltf_en = true, .htltf_en = false, .stbc_htltf_en = false, .ltf_merge_en = true, .channel_filter_en = false, .manu_scale = false, .shift = 0};
    if (esp_wifi_set_csi_config(&config) != ESP_OK) return -1;
    if (esp_wifi_set_csi_rx_cb(csi_callback, NULL) != ESP_OK) return -1;
    return esp_wifi_set_csi(true) == ESP_OK ? 0 : -1;
}
uint32_t csi_capture_dropped_packets(void) { return dropped_packets; }
