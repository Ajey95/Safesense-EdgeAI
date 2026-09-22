#pragma once

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define BME680_I2C_ADDRESS_LOW 0x76u
#define BME680_I2C_ADDRESS_HIGH 0x77u
#define BME680_CHIP_ID 0x61u
#define BME680_CALIBRATION_LENGTH 42u

typedef enum {
    BME680_OK = 0,
    BME680_ERR_ARGUMENT = -1,
    BME680_ERR_BUS = -2,
    BME680_ERR_NOT_FOUND = -3,
    BME680_ERR_TIMEOUT = -4,
    BME680_ERR_CALIBRATION = -5,
    BME680_ERR_HEATER = -6,
    BME680_ERR_INVALID_MEASUREMENT = -7,
} bme680_status_t;

typedef struct {
    uint16_t t1;
    int16_t t2;
    int8_t t3;
    uint16_t p1;
    int16_t p2;
    int8_t p3;
    int16_t p4;
    int16_t p5;
    int8_t p6;
    int8_t p7;
    int16_t p8;
    int16_t p9;
    uint8_t p10;
    uint16_t h1;
    uint16_t h2;
    int8_t h3;
    int8_t h4;
    int8_t h5;
    uint8_t h6;
    int8_t h7;
    int8_t gh1;
    int16_t gh2;
    int8_t gh3;
    int8_t res_heat_val;
    uint8_t res_heat_range;
    int8_t range_sw_err;
} bme680_calibration_t;

typedef struct {
    uint32_t temperature_adc;
    uint32_t pressure_adc;
    uint16_t humidity_adc;
    uint16_t gas_adc;
    uint8_t gas_range;
    bool new_data;
    bool gas_valid;
    bool heat_stable;
} bme680_raw_sample_t;

typedef struct {
    float temperature_c;
    float pressure_pa;
    float humidity_percent;
    float gas_resistance_ohm;
    bool gas_valid;
    bool heat_stable;
} bme680_reading_t;

bme680_status_t bme680_validate_chip_id(uint8_t chip_id);
uint8_t bme680_select_i2c_address(uint8_t preferred,
                                  bool low_available,
                                  bool high_available);
bme680_status_t bme680_parse_calibration(const uint8_t *registers,
                                         size_t length,
                                         bme680_calibration_t *calibration);
bme680_status_t bme680_compensate(const bme680_calibration_t *calibration,
                                  const bme680_raw_sample_t *raw,
                                  bme680_reading_t *reading);
uint8_t bme680_heater_resistance(const bme680_calibration_t *calibration,
                                 uint16_t target_temperature_c,
                                 int8_t ambient_temperature_c);
uint8_t bme680_encode_heater_duration(uint16_t duration_ms);

#ifdef __cplusplus
}
#endif
