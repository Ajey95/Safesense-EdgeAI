#pragma once

#include <stdbool.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef enum { FUSION_RISK_NORMAL, FUSION_RISK_WARNING, FUSION_RISK_CRITICAL, FUSION_RISK_UNAVAILABLE } fusion_environment_risk_t;
typedef enum { FUSION_ACTIVITY_VACANT, FUSION_ACTIVITY_STATIONARY, FUSION_ACTIVITY_WALKING, FUSION_ACTIVITY_UNKNOWN } fusion_activity_t;
typedef enum { FUSION_STATE_NORMAL, FUSION_STATE_WARNING, FUSION_STATE_INCIDENT, FUSION_STATE_DEGRADED } fusion_state_t;
typedef enum { FUSION_CONTEXT_KNOWN, FUSION_CONTEXT_UNKNOWN } fusion_context_t;

typedef struct {
    fusion_environment_risk_t environmental_risk;
    bool environmental_sensor_healthy;
    bool environmental_reading_fresh;
    bool csi_fresh;
    fusion_activity_t activity;
    float csi_confidence;
} fusion_input_t;

typedef struct {
    float minimum_csi_confidence;
} fusion_policy_t;

typedef struct {
    fusion_state_t state;
    fusion_context_t human_context;
    bool local_alarm;
    bool persist_event;
    bool publish_event;
    const char *reason_code;
} fusion_decision_t;

typedef struct {
    bool has_previous_state;
    fusion_state_t previous_state;
} fusion_tracker_t;

fusion_policy_t fusion_default_policy(void);
fusion_decision_t fusion_evaluate(const fusion_input_t *input, const fusion_policy_t *policy);
/* Call once per decision. State transitions, not repeated samples, request persistence. */
bool fusion_tracker_step(fusion_tracker_t *tracker, const fusion_decision_t *decision);

#ifdef __cplusplus
}
#endif
