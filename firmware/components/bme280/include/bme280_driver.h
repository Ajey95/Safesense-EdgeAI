#pragma once

/*
 * SafeSense BME280 driver.
 *
 * This component implements the BME280 register protocol and Bosch datasheet
 * compensation equations. It intentionally does not depend on an external
 * BME280 sensor library. A board supplies only read/write/delay primitives.
 */

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define BME280_I2C_ADDRESS_LOW  0x76u
#define BME280_I2C_ADDRESS_HIGH 0x77u
#define BME280_CHIP_ID          0x60u

typedef enum {
    BME280_OK = 0,
    BME280_ERR_ARGUMENT = -1,
    BME280_ERR_BUS = -2,
    BME280_ERR_NOT_FOUND = -3,
    BME280_ERR_TIMEOUT = -4,
    BME280_ERR_CALIBRATION = -5,
    BME280_ERR_INVALID_MEASUREMENT = -6,
} bme280_status_t;

typedef enum {
    BME280_OVERSAMPLING_SKIPPED = 0,
    BME280_OVERSAMPLING_X1 = 1,
    BME280_OVERSAMPLING_X2 = 2,
    BME280_OVERSAMPLING_X4 = 3,
    BME280_OVERSAMPLING_X8 = 4,
    BME280_OVERSAMPLING_X16 = 5,
} bme280_oversampling_t;

typedef enum {
    BME280_FILTER_OFF = 0,
    BME280_FILTER_X2 = 1,
    BME280_FILTER_X4 = 2,
    BME280_FILTER_X8 = 3,
    BME280_FILTER_X16 = 4,
} bme280_filter_t;

typedef enum {
    BME280_STANDBY_0_5_MS = 0,
    BME280_STANDBY_62_5_MS = 1,
    BME280_STANDBY_125_MS = 2,
    BME280_STANDBY_250_MS = 3,
    BME280_STANDBY_500_MS = 4,
    BME280_STANDBY_1000_MS = 5,
    BME280_STANDBY_10_MS = 6,
    BME280_STANDBY_20_MS = 7,
} bme280_standby_t;

typedef struct {
    /* Return 0 on success; implementation must transfer all requested bytes. */
    int (*read)(void *context, uint8_t address, uint8_t reg, uint8_t *data, size_t length);
    int (*write)(void *context, uint8_t address, uint8_t reg, const uint8_t *data, size_t length);
    void (*delay_ms)(void *context, uint32_t milliseconds);
    void *context;
} bme280_bus_t;

typedef struct {
    bme280_oversampling_t temperature_oversampling;
    bme280_oversampling_t pressure_oversampling;
    bme280_oversampling_t humidity_oversampling;
    bme280_filter_t filter;
    bme280_standby_t standby;
} bme280_config_t;

typedef struct {
    float temperature_c;
    float pressure_pa;
    float humidity_percent;
} bme280_reading_t;

typedef struct {
    uint16_t t1;
    int16_t t2, t3;
    uint16_t p1;
    int16_t p2, p3, p4, p5, p6, p7, p8, p9;
    uint8_t h1, h3;
    int16_t h2, h4, h5;
    int8_t h6;
} bme280_calibration_t;

typedef struct {
    bme280_bus_t bus;
    uint8_t address;
    bme280_calibration_t calibration;
    bme280_config_t config;
    bool initialized;
} bme280_t;

bme280_config_t bme280_default_config(void);
bme280_status_t bme280_init(bme280_t *device, const bme280_bus_t *bus, uint8_t address, const bme280_config_t *config);
bme280_status_t bme280_configure(bme280_t *device, const bme280_config_t *config);
bme280_status_t bme280_read_forced(bme280_t *device, bme280_reading_t *reading, uint32_t timeout_ms);
bme280_status_t bme280_read_normal(bme280_t *device, bme280_reading_t *reading);
bme280_status_t bme280_sleep(bme280_t *device);

#ifdef __cplusplus
}
#endif
