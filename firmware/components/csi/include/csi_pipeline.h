#pragma once
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define CSI_RAW_IQ_BYTES 128u
#define CSI_DATA_SUBCARRIERS 48u
#define CSI_WINDOW_FRAMES 100u
#define CSI_WINDOW_STRIDE 20u

typedef enum { CSI_OK = 0, CSI_ERR_ARGUMENT = -1, CSI_ERR_INVALID_FRAME = -2 } csi_status_t;
typedef struct { float frames[CSI_WINDOW_FRAMES][CSI_DATA_SUBCARRIERS]; uint16_t count, write_index, since_window; } csi_pipeline_t;

void csi_pipeline_init(csi_pipeline_t *pipeline);
/* ESP32 raw order is imaginary, real; invalid first words are rejected without shifting features. */
csi_status_t csi_pipeline_push(csi_pipeline_t *pipeline, const int8_t *iq, size_t length, bool first_word_invalid, bool *window_ready);
/* Copies frames chronologically so model input is always [100][48]. */
csi_status_t csi_pipeline_copy_window(const csi_pipeline_t *pipeline, float output[CSI_WINDOW_FRAMES][CSI_DATA_SUBCARRIERS]);
