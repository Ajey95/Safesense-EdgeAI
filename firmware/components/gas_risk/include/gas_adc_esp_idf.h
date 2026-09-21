#pragma once
#include "esp_adc/adc_oneshot.h"
#include "gas_risk.h"
typedef struct { adc_oneshot_unit_handle_t unit; adc_channel_t channel; } gas_adc_t;
int gas_adc_init(gas_adc_t *sensor, adc_channel_t channel);
gas_sample_t gas_adc_read(gas_adc_t *sensor);
