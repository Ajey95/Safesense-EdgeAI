#pragma once
#include "fusion_engine.h"
#include "csi_pipeline.h"
#ifdef __cplusplus
extern "C" {
#endif
/* Replaced only by the separately trained/quantized TFLite Micro model. */
fusion_activity_t csi_model_infer(const float window[CSI_WINDOW_FRAMES][CSI_DATA_SUBCARRIERS], float *confidence);
#ifdef __cplusplus
}
#endif
