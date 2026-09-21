#include "csi_pipeline.h"
#include <math.h>
#include <string.h>

static const int8_t raw_order[64] = {0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23,24,25,26,27,28,29,30,31,-32,-31,-30,-29,-28,-27,-26,-25,-24,-23,-22,-21,-20,-19,-18,-17,-16,-15,-14,-13,-12,-11,-10,-9,-8,-7,-6,-5,-4,-3,-2,-1};
static bool is_data_subcarrier(int8_t index) { return index >= -26 && index <= 26 && index != 0 && index != -21 && index != -7 && index != 7 && index != 21; }

void csi_pipeline_init(csi_pipeline_t *pipeline) { if (pipeline) memset(pipeline, 0, sizeof(*pipeline)); }
csi_status_t csi_pipeline_push(csi_pipeline_t *pipeline, const int8_t *iq, size_t length, bool first_word_invalid, bool *window_ready) {
    if (!pipeline || !iq || !window_ready) return CSI_ERR_ARGUMENT;
    *window_ready = false;
    if (first_word_invalid || length != CSI_RAW_IQ_BYTES) return CSI_ERR_INVALID_FRAME;
    uint8_t output = 0;
    for (uint8_t source = 0; source < 64; source++) {
        if (!is_data_subcarrier(raw_order[source])) continue;
        const float imaginary = iq[source * 2];
        const float real = iq[source * 2 + 1];
        pipeline->frames[pipeline->write_index][output++] = sqrtf(real * real + imaginary * imaginary);
    }
    if (output != CSI_DATA_SUBCARRIERS) return CSI_ERR_INVALID_FRAME;
    pipeline->write_index = (pipeline->write_index + 1) % CSI_WINDOW_FRAMES;
    if (pipeline->count < CSI_WINDOW_FRAMES) pipeline->count++;
    pipeline->since_window++;
    if (pipeline->count == CSI_WINDOW_FRAMES && pipeline->since_window >= CSI_WINDOW_STRIDE) { pipeline->since_window = 0; *window_ready = true; }
    return CSI_OK;
}
csi_status_t csi_pipeline_copy_window(const csi_pipeline_t *pipeline, float output[CSI_WINDOW_FRAMES][CSI_DATA_SUBCARRIERS]) {
    if (!pipeline || !output || pipeline->count != CSI_WINDOW_FRAMES) return CSI_ERR_ARGUMENT;
    for (uint16_t frame = 0; frame < CSI_WINDOW_FRAMES; frame++) memcpy(output[frame], pipeline->frames[(pipeline->write_index + frame) % CSI_WINDOW_FRAMES], sizeof(output[frame]));
    return CSI_OK;
}
