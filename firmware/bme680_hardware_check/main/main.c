#include "bme680.h"
#include "i2cdev.h"

#include "esp_err.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

static const char *TAG = "bme680_check";
static bme680_t sensor;

void app_main(void) {
    ESP_LOGI(TAG, "Checking BME680 at 0x76: SDA=GPIO21, SCL=GPIO22");

    esp_err_t status = i2cdev_init();
    if (status != ESP_OK) {
        ESP_LOGE(TAG, "I2C initialization failed: %s", esp_err_to_name(status));
        return;
    }

    status = bme680_init_desc(&sensor, BME680_I2C_ADDR_0, I2C_NUM_0, GPIO_NUM_21, GPIO_NUM_22);
    if (status != ESP_OK) {
        ESP_LOGE(TAG, "BME680 descriptor failed: %s", esp_err_to_name(status));
        return;
    }

    status = bme680_init_sensor(&sensor);
    if (status != ESP_OK) {
        ESP_LOGE(TAG, "BME680 initialization failed: %s", esp_err_to_name(status));
        return;
    }

    ESP_LOGI(TAG, "BME680 initialized; starting live measurements");
    for (int sample = 1; sample <= 10; ++sample) {
        bme680_values_float_t values;
        status = bme680_measure_float(&sensor, &values);
        if (status == ESP_OK) {
            ESP_LOGI(TAG, "sample=%d temperature=%.2f C humidity=%.2f %% pressure=%.2f hPa gas_resistance=%.0f ohm",
                     sample, values.temperature, values.humidity, values.pressure, values.gas_resistance);
        } else {
            ESP_LOGE(TAG, "sample=%d measurement failed: %s", sample, esp_err_to_name(status));
        }
        vTaskDelay(pdMS_TO_TICKS(2000));
    }
    ESP_LOGI(TAG, "Ten-sample hardware check finished");
}
