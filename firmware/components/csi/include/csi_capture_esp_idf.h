#pragma once
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include <stdbool.h>
#include <stdint.h>
#include "csi_pipeline.h"
typedef struct { int8_t iq[CSI_RAW_IQ_BYTES]; int8_t rssi_dbm; bool first_word_invalid; int64_t received_us; } csi_packet_t;
typedef struct {
    uint32_t callbacks;
    uint32_t unexpected_length;
    uint32_t first_word_invalid;
    uint32_t queued;
    uint32_t queue_full;
    uint16_t last_length;
} csi_capture_stats_t;
/* Wi-Fi must already be initialized and receiving packets. The callback only copies/queues. */
int csi_capture_start(QueueHandle_t destination_queue);
void csi_capture_get_stats(csi_capture_stats_t *out);
