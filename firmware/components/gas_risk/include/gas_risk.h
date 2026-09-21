#pragma once
#include <stdbool.h>
typedef enum { GAS_RISK_NORMAL, GAS_RISK_WARNING, GAS_RISK_CRITICAL, GAS_RISK_UNAVAILABLE } gas_risk_t;
typedef struct { float baseline_signal, warning_ratio, critical_ratio; } gas_policy_t;
/* Signal unit may be calibrated mV or a sensor-specific corrected ADC value; policy and sample must match. */
typedef struct { int signal; bool healthy; } gas_sample_t;
gas_policy_t gas_default_policy(void);
gas_risk_t gas_risk_evaluate(const gas_sample_t *sample, const gas_policy_t *policy);
