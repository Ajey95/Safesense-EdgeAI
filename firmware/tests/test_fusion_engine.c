#include <assert.h>
#include <stdio.h>
#include "fusion_engine.h"

static fusion_input_t nominal(void) {
    return (fusion_input_t){.environmental_risk = FUSION_RISK_NORMAL, .environmental_sensor_healthy = true, .environmental_reading_fresh = true, .csi_fresh = true, .activity = FUSION_ACTIVITY_WALKING, .csi_confidence = .92f};
}

int main(void) {
    fusion_input_t input = nominal();
    fusion_decision_t decision = fusion_evaluate(&input, NULL);
    assert(decision.state == FUSION_STATE_NORMAL && decision.human_context == FUSION_CONTEXT_KNOWN);
    input.activity = FUSION_ACTIVITY_UNKNOWN; input.csi_confidence = 0.0f;
    decision = fusion_evaluate(&input, NULL);
    assert(decision.state == FUSION_STATE_DEGRADED && decision.human_context == FUSION_CONTEXT_UNKNOWN && !decision.local_alarm);
    input.environmental_risk = FUSION_RISK_CRITICAL; input.csi_fresh = false;
    decision = fusion_evaluate(&input, NULL);
    assert(decision.state == FUSION_STATE_INCIDENT && decision.local_alarm && decision.persist_event);
    input = nominal(); input.environmental_risk = FUSION_RISK_UNAVAILABLE;
    decision = fusion_evaluate(&input, NULL);
    assert(decision.state == FUSION_STATE_DEGRADED && decision.human_context == FUSION_CONTEXT_UNKNOWN);
    fusion_tracker_t tracker = {0};
    assert(fusion_tracker_step(&tracker, &decision));
    assert(!fusion_tracker_step(&tracker, &decision));
    puts("fusion_engine tests passed");
}
