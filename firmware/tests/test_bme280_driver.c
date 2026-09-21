#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <string.h>
#include "bme280_driver.h"

typedef struct { uint8_t registers[256]; } mock_i2c_t;
static int read_bus(void *ctx, uint8_t address, uint8_t reg, uint8_t *data, size_t len) { (void)address; memcpy(data, &((mock_i2c_t *)ctx)->registers[reg], len); return 0; }
static int write_bus(void *ctx, uint8_t address, uint8_t reg, const uint8_t *data, size_t len) { (void)address; memcpy(&((mock_i2c_t *)ctx)->registers[reg], data, len); return 0; }
static void delay_bus(void *ctx, uint32_t ms) { (void)ctx; (void)ms; }
static void le(uint8_t *dst, int value) { dst[0] = (uint8_t)value; dst[1] = (uint8_t)(value >> 8); }

int main(void) {
    mock_i2c_t mock = {0};
    mock.registers[0xD0] = 0x60;
    /* Bosch datasheet temperature/pressure reference calibration vector. */
    le(&mock.registers[0x88], 27504); le(&mock.registers[0x8A], 26435); le(&mock.registers[0x8C], -1000);
    le(&mock.registers[0x8E], 36477); le(&mock.registers[0x90], -10685); le(&mock.registers[0x92], 3024); le(&mock.registers[0x94], 2855); le(&mock.registers[0x96], 140); le(&mock.registers[0x98], -7); le(&mock.registers[0x9A], 15500); le(&mock.registers[0x9C], -14600); le(&mock.registers[0x9E], 6000);
    mock.registers[0xA1] = 75; le(&mock.registers[0xE1], 362); mock.registers[0xE3] = 0; mock.registers[0xE4] = 0x14; mock.registers[0xE5] = 0x2E; mock.registers[0xE6] = 0x03; mock.registers[0xE7] = 30;
    int32_t p = 415148, t = 519888, h = 32257;
    mock.registers[0xF7] = p >> 12; mock.registers[0xF8] = p >> 4; mock.registers[0xF9] = (p & 15) << 4;
    mock.registers[0xFA] = t >> 12; mock.registers[0xFB] = t >> 4; mock.registers[0xFC] = (t & 15) << 4; mock.registers[0xFD] = h >> 8; mock.registers[0xFE] = h;
    bme280_bus_t bus = {read_bus, write_bus, delay_bus, &mock}; bme280_t bme;
    assert(bme280_init(&bme, &bus, BME280_I2C_ADDRESS_LOW, NULL) == BME280_OK);
    bme280_reading_t reading; assert(bme280_read_forced(&bme, &reading, 20) == BME280_OK);
    assert(fabsf(reading.temperature_c - 25.08f) < 0.05f); assert(fabsf(reading.pressure_pa - 100653.25f) < 1.0f);
    assert(reading.humidity_percent >= 0.0f && reading.humidity_percent <= 100.0f);
    mock.registers[0xD0] = 0x58; assert(bme280_init(&bme, &bus, BME280_I2C_ADDRESS_LOW, NULL) == BME280_ERR_NOT_FOUND);
    puts("bme280_driver tests passed");
}
