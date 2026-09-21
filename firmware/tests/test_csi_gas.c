#include <assert.h>
#include <stdio.h>
#include "csi_pipeline.h"
#include "gas_risk.h"
int main(void) {
    csi_pipeline_t pipeline; csi_pipeline_init(&pipeline); int8_t raw[CSI_RAW_IQ_BYTES] = {0}; bool ready;
    for (uint16_t i = 0; i < CSI_WINDOW_FRAMES; i++) { raw[0] = (int8_t)i; assert(csi_pipeline_push(&pipeline, raw, sizeof(raw), false, &ready) == CSI_OK); }
    assert(ready); float window[CSI_WINDOW_FRAMES][CSI_DATA_SUBCARRIERS]; assert(csi_pipeline_copy_window(&pipeline, window) == CSI_OK);
    assert(csi_pipeline_push(&pipeline, raw, sizeof(raw), true, &ready) == CSI_ERR_INVALID_FRAME);
    gas_policy_t policy = {.baseline_signal = 1000, .warning_ratio = 1.2f, .critical_ratio = 1.5f};
    assert(gas_risk_evaluate(&(gas_sample_t){.signal = 1100, .healthy = true}, &policy) == GAS_RISK_NORMAL);
    assert(gas_risk_evaluate(&(gas_sample_t){.signal = 1300, .healthy = true}, &policy) == GAS_RISK_WARNING);
    assert(gas_risk_evaluate(&(gas_sample_t){.signal = 1600, .healthy = true}, &policy) == GAS_RISK_CRITICAL);
    puts("csi and gas tests passed");
}
