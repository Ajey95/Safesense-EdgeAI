#include <assert.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>

#include "bme680_driver.h"

static const uint8_t calibration_registers[BME680_CALIBRATION_LENGTH] = {
    0xED, 0x66, 0x03, 0x00, 0x7D, 0x8E, 0x43, 0xD6, 0x58, 0x00, 0xC3,
    0x28, 0xF3, 0xF4, 0x07, 0x1E, 0x00, 0x00, 0xF8, 0xC6, 0x70, 0x17,
    0x1E, 0x3E, 0x8E, 0x2E, 0x00, 0x2D, 0x14, 0x78, 0x9C, 0x84, 0x65,
    0x3C, 0xF6, 0xE2, 0x04, 0x32, 0x00, 0x10, 0x00, 0xF0,
};

static bme680_calibration_t parse_fixture(void)
{
    bme680_calibration_t calibration;
    assert(bme680_parse_calibration(calibration_registers,
                                    sizeof(calibration_registers),
                                    &calibration) == BME680_OK);
    return calibration;
}

static void test_chip_id_and_addresses(void)
{
    assert(BME680_I2C_ADDRESS_LOW == 0x76u);
    assert(BME680_I2C_ADDRESS_HIGH == 0x77u);
    assert(bme680_validate_chip_id(0x61u) == BME680_OK);
    assert(bme680_validate_chip_id(0x60u) == BME680_ERR_NOT_FOUND);
}

static void test_calibration_parsing(void)
{
    bme680_calibration_t c = parse_fixture();
    assert(c.t1 == 25988u && c.t2 == 26349 && c.t3 == 3);
    assert(c.p1 == 36477u && c.p2 == -10685 && c.p3 == 88);
    assert(c.p4 == 10435 && c.p5 == -2829 && c.p6 == 30 && c.p7 == 7);
    assert(c.p8 == -14600 && c.p9 == 6000 && c.p10 == 30u);
    assert(c.h1 == 750u && c.h2 == 1000u && c.h3 == 0);
    assert(c.h4 == 45 && c.h5 == 20 && c.h6 == 120u && c.h7 == -100);
    assert(c.gh1 == -30 && c.gh2 == -2500 && c.gh3 == 4);
    assert(c.res_heat_val == 50 && c.res_heat_range == 1u && c.range_sw_err == -1);
    assert(bme680_parse_calibration(calibration_registers, 41u, &c) == BME680_ERR_ARGUMENT);
}

static void test_compensation_reference_vector(void)
{
    bme680_calibration_t c = parse_fixture();
    const bme680_raw_sample_t raw = {
        .temperature_adc = 519888u,
        .pressure_adc = 415148u,
        .humidity_adc = 20000u,
        .gas_adc = 650u,
        .gas_range = 9u,
        .new_data = true,
        .gas_valid = true,
        .heat_stable = true,
    };
    bme680_reading_t reading;
    assert(bme680_compensate(&c, &raw, &reading) == BME680_OK);
    assert(fabsf(reading.temperature_c - 32.6979f) < 0.001f);
    assert(fabsf(reading.pressure_pa - 81504.63f) < 0.2f);
    assert(fabsf(reading.humidity_percent - 40.4983f) < 0.01f);
    assert(fabsf(reading.gas_resistance_ohm - 14161.15f) < 1.0f);
    assert(reading.gas_valid && reading.heat_stable);
}

static void test_heater_and_duration_encoding(void)
{
    bme680_calibration_t c = parse_fixture();
    assert(bme680_heater_resistance(&c, 320u, 25) == 117u);
    assert(bme680_heater_resistance(&c, 500u, 25) ==
           bme680_heater_resistance(&c, 400u, 25));
    assert(bme680_encode_heater_duration(0u) == 0u);
    assert(bme680_encode_heater_duration(63u) == 63u);
    assert(bme680_encode_heater_duration(64u) == 80u);
    assert(bme680_encode_heater_duration(4032u) == 0xFFu);
}

static void test_measurement_validation(void)
{
    bme680_calibration_t c = parse_fixture();
    bme680_raw_sample_t raw = {
        .temperature_adc = 519888u,
        .pressure_adc = 415148u,
        .humidity_adc = 20000u,
        .gas_adc = 650u,
        .gas_range = 9u,
        .new_data = false,
        .gas_valid = true,
        .heat_stable = true,
    };
    bme680_reading_t reading;
    assert(bme680_compensate(&c, &raw, &reading) == BME680_ERR_INVALID_MEASUREMENT);
    raw.new_data = true;
    raw.gas_valid = false;
    assert(bme680_compensate(&c, &raw, &reading) == BME680_OK);
    assert(!reading.gas_valid && reading.gas_resistance_ohm == 0.0f);
    raw.gas_valid = true;
    raw.heat_stable = false;
    assert(bme680_compensate(&c, &raw, &reading) == BME680_OK);
    assert(!reading.heat_stable && reading.gas_resistance_ohm == 0.0f);
    raw.heat_stable = true;
    raw.gas_range = 16u;
    assert(bme680_compensate(&c, &raw, &reading) == BME680_ERR_INVALID_MEASUREMENT);
}

int main(void)
{
    test_chip_id_and_addresses();
    test_calibration_parsing();
    test_compensation_reference_vector();
    test_heater_and_duration_encoding();
    test_measurement_validation();
    puts("bme680_driver tests passed");
    return 0;
}
