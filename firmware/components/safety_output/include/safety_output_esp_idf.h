#pragma once

#include "safety_output.h"
#include "driver/gpio.h"
#include "driver/ledc.h"
#include "esp_err.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef enum {
    SAFETY_BUZZER_ACTIVE = 0,
    SAFETY_BUZZER_PASSIVE = 1,
} safety_buzzer_mode_t;

typedef struct {
    gpio_num_t green_pin;
    gpio_num_t yellow_pin;
    gpio_num_t red_pin;
    gpio_num_t buzzer_pin;
    bool leds_active_high;
    bool buzzer_active_high;
    safety_buzzer_mode_t buzzer_mode;
} safety_output_esp_idf_config_t;

typedef struct {
    safety_output_esp_idf_config_t config;
    bool initialized;
} safety_output_esp_idf_t;

esp_err_t safety_output_esp_idf_init(safety_output_esp_idf_t *output,
                                     const safety_output_esp_idf_config_t *config);
esp_err_t safety_output_esp_idf_apply(safety_output_esp_idf_t *output,
                                      fusion_state_t state,
                                      uint32_t elapsed_ms);
esp_err_t safety_output_esp_idf_all_off(safety_output_esp_idf_t *output);

#ifdef __cplusplus
}
#endif
