#pragma once

#include <stdbool.h>
#include <stdint.h>

typedef enum {
    GAS_RISK_NORMAL = 0,
    GAS_RISK_WARNING = 1,
    GAS_RISK_CRITICAL = 2,
    GAS_RISK_UNAVAILABLE = 3,
} gas_risk_t;

typedef struct {
    uint16_t warmup_samples;
    float baseline_alpha;
    float warning_ratio;
    float critical_ratio;
} gas_policy_t;

typedef struct {
    float resistance_ohm;
    bool gas_valid;
    bool heat_stable;
} gas_sample_t;

typedef struct {
    float baseline_ohm;
    uint32_t valid_samples;
    bool ready;
} gas_baseline_t;

gas_policy_t gas_default_policy(void);
bool gas_policy_validate(const gas_policy_t *policy);
void gas_baseline_reset(gas_baseline_t *state);
gas_risk_t gas_risk_update(gas_baseline_t *state,
                           const gas_sample_t *sample,
                           const gas_policy_t *policy,
                           float *ratio_out);
