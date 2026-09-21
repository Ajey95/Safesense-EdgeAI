#include <assert.h>
#include <stdio.h>

#include "safety_output.h"

static void assert_mutually_exclusive(const safety_output_pattern_t *pattern)
{
    const unsigned int enabled = (unsigned int)pattern->green_led +
                                 (unsigned int)pattern->yellow_led +
                                 (unsigned int)pattern->red_led;
    assert(enabled <= 1u);
}

static void test_normal_is_green_and_silent(void)
{
    safety_output_pattern_t pattern = safety_output_pattern_for_state(FUSION_STATE_NORMAL, 0u);
    assert(pattern.green_led && !pattern.yellow_led && !pattern.red_led);
    assert(!pattern.buzzer_on && pattern.buzzer_frequency_hz == 0u);
    assert_mutually_exclusive(&pattern);
}

static void test_warning_has_periodic_short_pulse(void)
{
    safety_output_pattern_t start = safety_output_pattern_for_state(FUSION_STATE_WARNING, 0u);
    safety_output_pattern_t quiet = safety_output_pattern_for_state(FUSION_STATE_WARNING, 250u);
    safety_output_pattern_t repeat = safety_output_pattern_for_state(FUSION_STATE_WARNING, 3000u);
    assert(start.yellow_led && start.buzzer_on && start.buzzer_frequency_hz == 1600u);
    assert(quiet.yellow_led && !quiet.buzzer_on);
    assert(repeat.yellow_led && repeat.buzzer_on);
    assert_mutually_exclusive(&start);
}

static void test_incident_uses_urgent_double_pulse(void)
{
    safety_output_pattern_t first = safety_output_pattern_for_state(FUSION_STATE_INCIDENT, 0u);
    safety_output_pattern_t gap = safety_output_pattern_for_state(FUSION_STATE_INCIDENT, 250u);
    safety_output_pattern_t second = safety_output_pattern_for_state(FUSION_STATE_INCIDENT, 400u);
    safety_output_pattern_t rest = safety_output_pattern_for_state(FUSION_STATE_INCIDENT, 700u);
    assert(first.red_led && first.buzzer_on && first.buzzer_frequency_hz == 2200u);
    assert(gap.red_led && !gap.buzzer_on);
    assert(second.red_led && second.buzzer_on);
    assert(rest.red_led && !rest.buzzer_on);
    assert_mutually_exclusive(&first);
}

static void test_degraded_slow_blinks_without_alarm(void)
{
    safety_output_pattern_t on = safety_output_pattern_for_state(FUSION_STATE_DEGRADED, 0u);
    safety_output_pattern_t off = safety_output_pattern_for_state(FUSION_STATE_DEGRADED, 600u);
    safety_output_pattern_t repeat = safety_output_pattern_for_state(FUSION_STATE_DEGRADED, 1000u);
    assert(on.yellow_led && !on.buzzer_on);
    assert(!off.green_led && !off.yellow_led && !off.red_led && !off.buzzer_on);
    assert(repeat.yellow_led && !repeat.buzzer_on);
    assert_mutually_exclusive(&on);
    assert_mutually_exclusive(&off);
}

int main(void)
{
    test_normal_is_green_and_silent();
    test_warning_has_periodic_short_pulse();
    test_incident_uses_urgent_double_pulse();
    test_degraded_slow_blinks_without_alarm();
    puts("safety_output tests passed");
    return 0;
}
