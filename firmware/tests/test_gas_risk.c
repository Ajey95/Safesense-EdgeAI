#include <assert.h>
#include <math.h>
#include <stdio.h>

#include "gas_risk.h"

static gas_sample_t valid_sample(float resistance_ohm)
{
    return (gas_sample_t){
        .resistance_ohm = resistance_ohm,
        .gas_valid = true,
        .heat_stable = true,
    };
}

static void test_policy_validation(void)
{
    gas_policy_t policy = gas_default_policy();
    assert(gas_policy_validate(&policy));
    policy.warmup_samples = 0u;
    assert(!gas_policy_validate(&policy));
    policy = gas_default_policy();
    policy.baseline_alpha = 0.0f;
    assert(!gas_policy_validate(&policy));
    policy = gas_default_policy();
    policy.critical_ratio = policy.warning_ratio;
    assert(!gas_policy_validate(&policy));
}

static void test_warmup_and_exponential_baseline(void)
{
    const gas_policy_t policy = {
        .warmup_samples = 3u,
        .baseline_alpha = 0.5f,
        .warning_ratio = 0.75f,
        .critical_ratio = 0.50f,
    };
    gas_baseline_t state;
    gas_baseline_reset(&state);
    float ratio = 0.0f;
    gas_sample_t sample = valid_sample(100000.0f);
    assert(gas_risk_update(&state, &sample, &policy, &ratio) == GAS_RISK_UNAVAILABLE);
    assert(state.valid_samples == 1u && fabsf(state.baseline_ohm - 100000.0f) < 0.1f);
    sample = valid_sample(110000.0f);
    assert(gas_risk_update(&state, &sample, &policy, &ratio) == GAS_RISK_UNAVAILABLE);
    assert(fabsf(state.baseline_ohm - 105000.0f) < 0.1f);
    sample = valid_sample(100000.0f);
    assert(gas_risk_update(&state, &sample, &policy, &ratio) == GAS_RISK_NORMAL);
    assert(state.ready && state.valid_samples == 3u);
    assert(fabsf(state.baseline_ohm - 102500.0f) < 0.1f);
    assert(fabsf(ratio - (100000.0f / 102500.0f)) < 0.0001f);
}

static void test_warning_and_critical_do_not_lower_baseline(void)
{
    const gas_policy_t policy = {
        .warmup_samples = 1u,
        .baseline_alpha = 0.25f,
        .warning_ratio = 0.75f,
        .critical_ratio = 0.50f,
    };
    gas_baseline_t state;
    gas_baseline_reset(&state);
    float ratio;
    gas_sample_t sample = valid_sample(100000.0f);
    assert(gas_risk_update(&state, &sample, &policy, &ratio) == GAS_RISK_NORMAL);
    sample = valid_sample(70000.0f);
    assert(gas_risk_update(&state, &sample, &policy, &ratio) == GAS_RISK_WARNING);
    assert(fabsf(ratio - 0.70f) < 0.0001f);
    assert(fabsf(state.baseline_ohm - 100000.0f) < 0.1f);
    sample = valid_sample(45000.0f);
    assert(gas_risk_update(&state, &sample, &policy, &ratio) == GAS_RISK_CRITICAL);
    assert(fabsf(state.baseline_ohm - 100000.0f) < 0.1f);
}

static void test_invalid_samples_never_update_baseline(void)
{
    gas_policy_t policy = gas_default_policy();
    policy.warmup_samples = 1u;
    gas_baseline_t state;
    gas_baseline_reset(&state);
    float ratio;
    gas_sample_t sample = valid_sample(80000.0f);
    assert(gas_risk_update(&state, &sample, &policy, &ratio) == GAS_RISK_NORMAL);
    const float baseline = state.baseline_ohm;
    sample.gas_valid = false;
    assert(gas_risk_update(&state, &sample, &policy, &ratio) == GAS_RISK_UNAVAILABLE);
    assert(state.baseline_ohm == baseline);
    sample.gas_valid = true;
    sample.heat_stable = false;
    assert(gas_risk_update(&state, &sample, &policy, &ratio) == GAS_RISK_UNAVAILABLE);
    assert(state.baseline_ohm == baseline);
    sample.heat_stable = true;
    sample.resistance_ohm = 0.0f;
    assert(gas_risk_update(&state, &sample, &policy, &ratio) == GAS_RISK_UNAVAILABLE);
    assert(state.baseline_ohm == baseline);
}

int main(void)
{
    test_policy_validation();
    test_warmup_and_exponential_baseline();
    test_warning_and_critical_do_not_lower_baseline();
    test_invalid_samples_never_update_baseline();
    puts("gas_risk tests passed");
    return 0;
}
