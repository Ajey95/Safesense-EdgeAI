#include "gas_risk.h"
gas_policy_t gas_default_policy(void) { return (gas_policy_t){.baseline_signal = 0.0f, .warning_ratio = 1.0f, .critical_ratio = 1.0f}; }
gas_risk_t gas_risk_evaluate(const gas_sample_t *sample, const gas_policy_t *configured) {
    const gas_policy_t fallback = gas_default_policy(); const gas_policy_t *policy = configured ? configured : &fallback;
    if (!sample || !sample->healthy || policy->baseline_signal <= 0 || policy->warning_ratio <= 1 || policy->critical_ratio <= policy->warning_ratio) return GAS_RISK_UNAVAILABLE;
    const float ratio = sample->signal / policy->baseline_signal;
    if (ratio >= policy->critical_ratio) return GAS_RISK_CRITICAL;
    if (ratio >= policy->warning_ratio) return GAS_RISK_WARNING;
    return GAS_RISK_NORMAL;
}
