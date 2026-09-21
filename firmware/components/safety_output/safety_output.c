#include "safety_output.h"

safety_output_pattern_t safety_output_pattern_for_state(fusion_state_t state,
                                                        uint32_t elapsed_ms)
{
    safety_output_pattern_t pattern = {0};
    switch (state) {
    case FUSION_STATE_NORMAL:
        pattern.green_led = true;
        break;
    case FUSION_STATE_WARNING:
        pattern.yellow_led = true;
        pattern.buzzer_on = (elapsed_ms % 3000u) < 200u;
        pattern.buzzer_frequency_hz = pattern.buzzer_on ? 1600u : 0u;
        break;
    case FUSION_STATE_INCIDENT: {
        const uint32_t phase = elapsed_ms % 1000u;
        pattern.red_led = true;
        pattern.buzzer_on = phase < 200u || (phase >= 350u && phase < 550u);
        pattern.buzzer_frequency_hz = pattern.buzzer_on ? 2200u : 0u;
        break;
    }
    case FUSION_STATE_DEGRADED:
    default:
        pattern.yellow_led = (elapsed_ms % 1000u) < 500u;
        break;
    }
    return pattern;
}
