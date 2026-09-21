#include "csi_model.h"
fusion_activity_t csi_model_infer(const float window[CSI_WINDOW_FRAMES][CSI_DATA_SUBCARRIERS], float *confidence) {
    (void)window; if (confidence) *confidence = 0.0f;
    return FUSION_ACTIVITY_UNKNOWN; /* Fail closed until the INT8 artifact is available. */
}
