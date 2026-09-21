#pragma once

#include "fusion_engine.h"

#include <stdbool.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    bool green_led;
    bool yellow_led;
    bool red_led;
    bool buzzer_on;
    uint32_t buzzer_frequency_hz;
} safety_output_pattern_t;

safety_output_pattern_t safety_output_pattern_for_state(fusion_state_t state,
                                                        uint32_t elapsed_ms);

#ifdef __cplusplus
}
#endif
