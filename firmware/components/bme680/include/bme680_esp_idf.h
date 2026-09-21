#pragma once

#include "bme680_driver.h"
#include "driver/i2c_master.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    uint16_t heater_temperature_c;
    uint16_t heater_duration_ms;
    int8_t ambient_temperature_c;
    uint32_t i2c_frequency_hz;
} bme680_esp_idf_config_t;

typedef struct {
    i2c_master_dev_handle_t handle;
    bme680_calibration_t calibration;
    bme680_esp_idf_config_t config;
    bool initialized;
} bme680_esp_idf_t;

bme680_esp_idf_config_t bme680_esp_idf_default_config(void);
bme680_status_t bme680_esp_idf_init(bme680_esp_idf_t *device,
                                    i2c_master_bus_handle_t bus,
                                    uint8_t address,
                                    const bme680_esp_idf_config_t *config);
bme680_status_t bme680_esp_idf_read_forced(bme680_esp_idf_t *device,
                                           bme680_reading_t *reading,
                                           uint32_t timeout_ms);
void bme680_esp_idf_deinit(bme680_esp_idf_t *device);

#ifdef __cplusplus
}
#endif
