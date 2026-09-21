#pragma once
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include <stdbool.h>
#include <stdint.h>
#include "csi_pipeline.h"
typedef struct { int8_t iq[CSI_RAW_IQ_BYTES]; int8_t rssi_dbm; bool first_word_invalid; int64_t received_us; } csi_packet_t;
/* Wi-Fi must already be initialized and receiving packets. The callback only copies/queues. */
int csi_capture_start(QueueHandle_t destination_queue);
