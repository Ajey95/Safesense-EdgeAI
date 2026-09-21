#include "gas_risk.h"

#include <stddef.h>

gas_policy_t gas_default_policy(void)
{
    return (gas_policy_t){
        .warmup_samples = 30u,
        .baseline_alpha = 0.02f,
        .warning_ratio = 0.75f,
        .critical_ratio = 0.50f,
    };
}

bool gas_policy_validate(const gas_policy_t *policy)
{
    return policy != NULL && policy->warmup_samples > 0u &&
           policy->baseline_alpha > 0.0f && policy->baseline_alpha <= 1.0f &&
           policy->warning_ratio > 0.0f && policy->warning_ratio < 1.0f &&
           policy->critical_ratio > 0.0f &&
           policy->critical_ratio < policy->warning_ratio;
}

void gas_baseline_reset(gas_baseline_t *state)
{
    if (state != NULL) {
        *state = (gas_baseline_t){0};
    }
}

gas_risk_t gas_risk_update(gas_baseline_t *state,
                           const gas_sample_t *sample,
                           const gas_policy_t *configured,
                           float *ratio_out)
{
    const gas_policy_t fallback = gas_default_policy();
    const gas_policy_t *policy = configured != NULL ? configured : &fallback;
    if (ratio_out != NULL) {
        *ratio_out = 0.0f;
    }
    if (state == NULL || sample == NULL || !gas_policy_validate(policy) ||
        !sample->gas_valid || !sample->heat_stable || sample->resistance_ohm <= 0.0f) {
        return GAS_RISK_UNAVAILABLE;
    }

    const bool was_ready = state->ready;
    if (state->valid_samples == 0u || state->baseline_ohm <= 0.0f) {
        state->baseline_ohm = sample->resistance_ohm;
    } else if (!state->ready) {
        state->baseline_ohm += policy->baseline_alpha *
                               (sample->resistance_ohm - state->baseline_ohm);
    }
    if (state->valid_samples < UINT32_MAX) {
        state->valid_samples++;
    }
    state->ready = state->valid_samples >= policy->warmup_samples;
    if (!state->ready) {
        return GAS_RISK_UNAVAILABLE;
    }

    float ratio = sample->resistance_ohm / state->baseline_ohm;
    if (ratio_out != NULL) {
        *ratio_out = ratio;
    }
    if (ratio <= policy->critical_ratio) {
        return GAS_RISK_CRITICAL;
    }
    if (ratio <= policy->warning_ratio) {
        return GAS_RISK_WARNING;
    }

    if (was_ready) {
        state->baseline_ohm += policy->baseline_alpha *
                               (sample->resistance_ohm - state->baseline_ohm);
    }
    return GAS_RISK_NORMAL;
}
