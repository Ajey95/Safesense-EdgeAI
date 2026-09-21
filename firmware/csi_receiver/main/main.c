#include "csi_capture_esp_idf.h"
#include "csi_model.h"
#include "csi_pipeline.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "freertos/task.h"
#include "wifi_station.h"

static const char *TAG = "csi_receiver";
static QueueHandle_t csi_queue;
/* These buffers are about 19 KB each, so keep them in BSS rather than the
 * 8 KB FreeRTOS task stack.  Only the CSI processing task accesses them. */
static csi_pipeline_t csi_pipeline;
static float csi_window[CSI_WINDOW_FRAMES][CSI_DATA_SUBCARRIERS];

static void csi_processing_task(void *ignored) {
    (void)ignored; csi_pipeline_init(&csi_pipeline); csi_packet_t packet;
    while (true) {
        if (xQueueReceive(csi_queue, &packet, portMAX_DELAY) != pdTRUE) continue;
        bool ready = false;
        if (csi_pipeline_push(&csi_pipeline, packet.iq, sizeof(packet.iq), packet.first_word_invalid, &ready) != CSI_OK || !ready) continue;
        if (csi_pipeline_copy_window(&csi_pipeline, csi_window) != CSI_OK) continue;
        float confidence; fusion_activity_t activity = csi_model_infer(csi_window, &confidence);
        /* The delivery task serializes this with the BME/gas/fusion result. */
        ESP_LOGI(TAG, "CSI window ready: activity=%d confidence=%.2f rssi=%d", activity, confidence, packet.rssi_dbm);
    }
}

void app_main(void) {
    if (wifi_station_start(CONFIG_SAFESENSE_WIFI_SSID, CONFIG_SAFESENSE_WIFI_PASSWORD, 30000) != 0) {
        ESP_LOGE(TAG, "Wi-Fi connection failed; configure credentials with menuconfig");
        return;
    }
    csi_queue = xQueueCreate(32, sizeof(csi_packet_t));
    if (!csi_queue || csi_capture_start(csi_queue) != 0) { ESP_LOGE(TAG, "CSI startup failed; verify Wi-Fi is initialized and receiving packets"); return; }
    xTaskCreate(csi_processing_task, "csi_processing", 8192, NULL, 5, NULL);
}
