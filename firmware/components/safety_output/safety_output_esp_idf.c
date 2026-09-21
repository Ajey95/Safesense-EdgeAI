#include "safety_output_esp_idf.h"

#define BUZZER_LEDC_MODE LEDC_LOW_SPEED_MODE
#define BUZZER_LEDC_TIMER LEDC_TIMER_0
#define BUZZER_LEDC_CHANNEL LEDC_CHANNEL_0
#define BUZZER_DUTY_ON 512u

static int active_level(bool on, bool active_high)
{
    return on == active_high ? 1 : 0;
}

static bool pin_is_valid(gpio_num_t pin)
{
    return pin >= GPIO_NUM_0 && pin < GPIO_NUM_MAX;
}

esp_err_t safety_output_esp_idf_init(safety_output_esp_idf_t *output,
                                     const safety_output_esp_idf_config_t *config)
{
    if (output == NULL || config == NULL || !pin_is_valid(config->green_pin) ||
        !pin_is_valid(config->yellow_pin) || !pin_is_valid(config->red_pin) ||
        !pin_is_valid(config->buzzer_pin) || config->buzzer_mode > SAFETY_BUZZER_PASSIVE) {
        return ESP_ERR_INVALID_ARG;
    }

    *output = (safety_output_esp_idf_t){.config = *config};
    const gpio_config_t leds = {
        .pin_bit_mask = (1ULL << config->green_pin) |
                        (1ULL << config->yellow_pin) |
                        (1ULL << config->red_pin),
        .mode = GPIO_MODE_OUTPUT,
        .pull_up_en = GPIO_PULLUP_DISABLE,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .intr_type = GPIO_INTR_DISABLE,
    };
    esp_err_t error = gpio_config(&leds);
    if (error != ESP_OK) {
        return error;
    }

    if (config->buzzer_mode == SAFETY_BUZZER_ACTIVE) {
        const gpio_config_t buzzer = {
            .pin_bit_mask = 1ULL << config->buzzer_pin,
            .mode = GPIO_MODE_OUTPUT,
            .pull_up_en = GPIO_PULLUP_DISABLE,
            .pull_down_en = GPIO_PULLDOWN_DISABLE,
            .intr_type = GPIO_INTR_DISABLE,
        };
        error = gpio_config(&buzzer);
    } else {
        const ledc_timer_config_t timer = {
            .speed_mode = BUZZER_LEDC_MODE,
            .duty_resolution = LEDC_TIMER_10_BIT,
            .timer_num = BUZZER_LEDC_TIMER,
            .freq_hz = 2000,
            .clk_cfg = LEDC_AUTO_CLK,
        };
        error = ledc_timer_config(&timer);
        if (error == ESP_OK) {
            const ledc_channel_config_t channel = {
                .gpio_num = config->buzzer_pin,
                .speed_mode = BUZZER_LEDC_MODE,
                .channel = BUZZER_LEDC_CHANNEL,
                .intr_type = LEDC_INTR_DISABLE,
                .timer_sel = BUZZER_LEDC_TIMER,
                .duty = 0u,
                .hpoint = 0u,
            };
            error = ledc_channel_config(&channel);
        }
    }
    if (error != ESP_OK) {
        return error;
    }
    output->initialized = true;
    return safety_output_esp_idf_all_off(output);
}

static esp_err_t set_buzzer(const safety_output_esp_idf_t *output,
                            const safety_output_pattern_t *pattern)
{
    if (output->config.buzzer_mode == SAFETY_BUZZER_ACTIVE) {
        return gpio_set_level(output->config.buzzer_pin,
                              active_level(pattern->buzzer_on,
                                           output->config.buzzer_active_high));
    }
    esp_err_t error = ESP_OK;
    if (pattern->buzzer_on) {
        error = ledc_set_freq(BUZZER_LEDC_MODE, BUZZER_LEDC_TIMER,
                              pattern->buzzer_frequency_hz);
    }
    if (error == ESP_OK) {
        error = ledc_set_duty(BUZZER_LEDC_MODE, BUZZER_LEDC_CHANNEL,
                              pattern->buzzer_on ? BUZZER_DUTY_ON : 0u);
    }
    if (error == ESP_OK) {
        error = ledc_update_duty(BUZZER_LEDC_MODE, BUZZER_LEDC_CHANNEL);
    }
    return error;
}

static esp_err_t apply_pattern(safety_output_esp_idf_t *output,
                               const safety_output_pattern_t *pattern)
{
    esp_err_t error = gpio_set_level(output->config.green_pin,
                                     active_level(pattern->green_led,
                                                  output->config.leds_active_high));
    if (error == ESP_OK) {
        error = gpio_set_level(output->config.yellow_pin,
                               active_level(pattern->yellow_led,
                                            output->config.leds_active_high));
    }
    if (error == ESP_OK) {
        error = gpio_set_level(output->config.red_pin,
                               active_level(pattern->red_led,
                                            output->config.leds_active_high));
    }
    return error == ESP_OK ? set_buzzer(output, pattern) : error;
}

esp_err_t safety_output_esp_idf_apply(safety_output_esp_idf_t *output,
                                      fusion_state_t state,
                                      uint32_t elapsed_ms)
{
    if (output == NULL || !output->initialized) {
        return ESP_ERR_INVALID_STATE;
    }
    const safety_output_pattern_t pattern = safety_output_pattern_for_state(state, elapsed_ms);
    return apply_pattern(output, &pattern);
}

esp_err_t safety_output_esp_idf_all_off(safety_output_esp_idf_t *output)
{
    if (output == NULL || !output->initialized) {
        return ESP_ERR_INVALID_STATE;
    }
    const safety_output_pattern_t off = {0};
    return apply_pattern(output, &off);
}
