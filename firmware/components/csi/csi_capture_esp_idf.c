#include "csi_capture_esp_idf.h"
#include <string.h>
#include "esp_timer.h"
#include "esp_wifi.h"

static QueueHandle_t queue_handle;
static csi_capture_stats_t stats;
static void csi_callback(void *context, wifi_csi_info_t *info) {
    (void)context;
    if (!queue_handle || !info) return;
    __atomic_fetch_add(&stats.callbacks, 1u, __ATOMIC_RELAXED);
    __atomic_store_n(&stats.last_length, info->len, __ATOMIC_RELAXED);
    if (info->first_word_invalid)
        __atomic_fetch_add(&stats.first_word_invalid, 1u, __ATOMIC_RELAXED);
    if (info->len != CSI_RAW_IQ_BYTES || !info->buf) {
        __atomic_fetch_add(&stats.unexpected_length, 1u, __ATOMIC_RELAXED);
        return;
    }
    csi_packet_t packet = {.rssi_dbm = info->rx_ctrl.rssi, .first_word_invalid = info->first_word_invalid, .received_us = esp_timer_get_time()};
    memcpy(packet.iq, info->buf, CSI_RAW_IQ_BYTES);
    if (xQueueSend(queue_handle, &packet, 0) == pdTRUE)
        __atomic_fetch_add(&stats.queued, 1u, __ATOMIC_RELAXED);
    else __atomic_fetch_add(&stats.queue_full, 1u, __ATOMIC_RELAXED);
    /* Never block the Wi-Fi task. */
}
void csi_capture_get_stats(csi_capture_stats_t *out) {
    if (!out) return;
    out->callbacks = __atomic_load_n(&stats.callbacks, __ATOMIC_RELAXED);
    out->unexpected_length = __atomic_load_n(&stats.unexpected_length, __ATOMIC_RELAXED);
    out->first_word_invalid = __atomic_load_n(&stats.first_word_invalid, __ATOMIC_RELAXED);
    out->queued = __atomic_load_n(&stats.queued, __ATOMIC_RELAXED);
    out->queue_full = __atomic_load_n(&stats.queue_full, __ATOMIC_RELAXED);
    out->last_length = __atomic_load_n(&stats.last_length, __ATOMIC_RELAXED);
}
int csi_capture_start(QueueHandle_t destination_queue) {
    if (!destination_queue) return -1;
    queue_handle = destination_queue;
    wifi_csi_config_t config = {.lltf_en = true, .htltf_en = false, .stbc_htltf2_en = false, .ltf_merge_en = true, .channel_filter_en = false, .manu_scale = false, .shift = 0};
    if (esp_wifi_set_csi_config(&config) != ESP_OK) return -1;
    if (esp_wifi_set_csi_rx_cb(csi_callback, NULL) != ESP_OK) return -1;
    return esp_wifi_set_csi(true) == ESP_OK ? 0 : -1;
}
