#include "fusion_engine.h"

fusion_policy_t fusion_default_policy(void) {
    return (fusion_policy_t){.minimum_csi_confidence = 0.70f};
}

fusion_decision_t fusion_evaluate(const fusion_input_t *input, const fusion_policy_t *configured_policy) {
    const fusion_policy_t default_policy = fusion_default_policy();
    const fusion_policy_t *policy = configured_policy ? configured_policy : &default_policy;
    if (!input) return (fusion_decision_t){.state = FUSION_STATE_DEGRADED, .human_context = FUSION_CONTEXT_UNKNOWN, .publish_event = true, .reason_code = "INVALID_INPUT"};
    /* Critical environment comes first: CSI can add context, never veto danger. */
    if (input->environmental_risk == FUSION_RISK_CRITICAL) return (fusion_decision_t){.state = FUSION_STATE_INCIDENT, .human_context = (input->csi_fresh && input->activity != FUSION_ACTIVITY_UNKNOWN && input->csi_confidence >= policy->minimum_csi_confidence) ? FUSION_CONTEXT_KNOWN : FUSION_CONTEXT_UNKNOWN, .local_alarm = true, .persist_event = true, .publish_event = true, .reason_code = "ENVIRONMENT_CRITICAL"};
    if (!input->environmental_sensor_healthy || !input->environmental_reading_fresh || input->environmental_risk == FUSION_RISK_UNAVAILABLE) return (fusion_decision_t){.state = FUSION_STATE_DEGRADED, .human_context = FUSION_CONTEXT_UNKNOWN, .publish_event = true, .reason_code = "ENVIRONMENT_UNAVAILABLE"};
    if (input->environmental_risk == FUSION_RISK_WARNING) return (fusion_decision_t){.state = FUSION_STATE_WARNING, .human_context = (input->csi_fresh && input->activity != FUSION_ACTIVITY_UNKNOWN && input->csi_confidence >= policy->minimum_csi_confidence) ? FUSION_CONTEXT_KNOWN : FUSION_CONTEXT_UNKNOWN, .persist_event = true, .publish_event = true, .reason_code = "ENVIRONMENT_WARNING"};
    if (!input->csi_fresh) return (fusion_decision_t){.state = FUSION_STATE_DEGRADED, .human_context = FUSION_CONTEXT_UNKNOWN, .publish_event = true, .reason_code = "CSI_STALE"};
    if (input->activity == FUSION_ACTIVITY_UNKNOWN || input->csi_confidence < policy->minimum_csi_confidence) return (fusion_decision_t){.state = FUSION_STATE_DEGRADED, .human_context = FUSION_CONTEXT_UNKNOWN, .publish_event = true, .reason_code = "CSI_UNCERTAIN"};
    return (fusion_decision_t){.state = FUSION_STATE_NORMAL, .human_context = FUSION_CONTEXT_KNOWN, .publish_event = true, .reason_code = "ALL_SIGNALS_NOMINAL"};
}

bool fusion_tracker_step(fusion_tracker_t *tracker, const fusion_decision_t *decision) {
    if (!tracker || !decision) return false;
    const bool changed = !tracker->has_previous_state || tracker->previous_state != decision->state;
    tracker->has_previous_state = true;
    tracker->previous_state = decision->state;
    return changed;
}
