#pragma once

#include "bme280_driver.h"
#include "driver/i2c_master.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    i2c_master_dev_handle_t handle;
} bme280_esp_idf_bus_t;

/* Bind an ESP-IDF I2C device handle to the portable BME280 driver transport. */
void bme280_esp_idf_make_bus(bme280_bus_t *out_bus, bme280_esp_idf_bus_t *idf_bus);

#ifdef __cplusplus
}
#endif
