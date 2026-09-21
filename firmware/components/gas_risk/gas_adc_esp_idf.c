#include "gas_adc_esp_idf.h"
#include "esp_err.h"
int gas_adc_init(gas_adc_t *sensor, adc_channel_t channel) {
    if (!sensor) return -1;
    adc_oneshot_unit_init_cfg_t unit_config = {.unit_id = ADC_UNIT_1};
    if (adc_oneshot_new_unit(&unit_config, &sensor->unit) != ESP_OK) return -1;
    sensor->channel = channel;
    adc_oneshot_chan_cfg_t channel_config = {.bitwidth = ADC_BITWIDTH_DEFAULT, .atten = ADC_ATTEN_DB_12};
    return adc_oneshot_config_channel(sensor->unit, channel, &channel_config) == ESP_OK ? 0 : -1;
}
gas_sample_t gas_adc_read(gas_adc_t *sensor) {
    int raw = 0;
    if (!sensor || adc_oneshot_read(sensor->unit, sensor->channel, &raw) != ESP_OK) return (gas_sample_t){.healthy = false};
    /* The policy stores the matching calibrated or raw baseline signal. */
    return (gas_sample_t){.signal = raw, .healthy = true};
}
