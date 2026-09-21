#include "bme280_driver.h"

#define REG_CALIB_00 0x88u
#define REG_CALIB_26 0xE1u
#define REG_CHIP_ID 0xD0u
#define REG_RESET 0xE0u
#define REG_CTRL_HUM 0xF2u
#define REG_STATUS 0xF3u
#define REG_CTRL_MEAS 0xF4u
#define REG_CONFIG 0xF5u
#define REG_DATA 0xF7u
#define RESET_COMMAND 0xB6u
#define STATUS_MEASURING 0x08u
#define STATUS_NVM_COPYING 0x01u

static uint16_t u16le(const uint8_t *p) { return (uint16_t)p[0] | ((uint16_t)p[1] << 8); }
static int16_t s16le(const uint8_t *p) { return (int16_t)u16le(p); }
static int16_t sign_extend_12(uint16_t value) { return (value & 0x0800u) ? (int16_t)(value | 0xF000u) : (int16_t)value; }

static bme280_status_t read_registers(bme280_t *device, uint8_t reg, uint8_t *data, size_t length) {
    if (!device || !data || !length || !device->bus.read) return BME280_ERR_ARGUMENT;
    return device->bus.read(device->bus.context, device->address, reg, data, length) == 0 ? BME280_OK : BME280_ERR_BUS;
}

static bme280_status_t write_register(bme280_t *device, uint8_t reg, uint8_t value) {
    if (!device || !device->bus.write) return BME280_ERR_ARGUMENT;
    return device->bus.write(device->bus.context, device->address, reg, &value, 1) == 0 ? BME280_OK : BME280_ERR_BUS;
}

static void delay_ms(bme280_t *device, uint32_t milliseconds) {
    if (device->bus.delay_ms) device->bus.delay_ms(device->bus.context, milliseconds);
}

static bme280_status_t wait_for_clear(bme280_t *device, uint8_t bit, uint32_t timeout_ms) {
    for (uint32_t elapsed = 0; elapsed <= timeout_ms; elapsed += 2) {
        uint8_t status;
        bme280_status_t result = read_registers(device, REG_STATUS, &status, 1);
        if (result != BME280_OK) return result;
        if ((status & bit) == 0) return BME280_OK;
        delay_ms(device, 2);
    }
    return BME280_ERR_TIMEOUT;
}

static bme280_status_t read_calibration(bme280_t *device) {
    uint8_t first[26], second[7];
    bme280_status_t result = read_registers(device, REG_CALIB_00, first, sizeof(first));
    if (result != BME280_OK) return result;
    result = read_registers(device, REG_CALIB_26, second, sizeof(second));
    if (result != BME280_OK) return result;
    bme280_calibration_t *c = &device->calibration;
    c->t1 = u16le(&first[0]); c->t2 = s16le(&first[2]); c->t3 = s16le(&first[4]);
    c->p1 = u16le(&first[6]); c->p2 = s16le(&first[8]); c->p3 = s16le(&first[10]); c->p4 = s16le(&first[12]);
    c->p5 = s16le(&first[14]); c->p6 = s16le(&first[16]); c->p7 = s16le(&first[18]); c->p8 = s16le(&first[20]); c->p9 = s16le(&first[22]);
    c->h1 = first[25]; c->h2 = s16le(&second[0]); c->h3 = second[2];
    c->h4 = sign_extend_12((uint16_t)((second[3] << 4) | (second[4] & 0x0Fu)));
    c->h5 = sign_extend_12((uint16_t)((second[5] << 4) | (second[4] >> 4)));
    c->h6 = (int8_t)second[6];
    return c->t1 == 0 || c->p1 == 0 ? BME280_ERR_CALIBRATION : BME280_OK;
}

bme280_config_t bme280_default_config(void) {
    return (bme280_config_t){BME280_OVERSAMPLING_X2, BME280_OVERSAMPLING_X16, BME280_OVERSAMPLING_X1, BME280_FILTER_X4, BME280_STANDBY_500_MS};
}

bme280_status_t bme280_configure(bme280_t *device, const bme280_config_t *config) {
    if (!device || !config || !device->initialized || config->temperature_oversampling > BME280_OVERSAMPLING_X16 || config->pressure_oversampling > BME280_OVERSAMPLING_X16 || config->humidity_oversampling > BME280_OVERSAMPLING_X16 || config->filter > BME280_FILTER_X16 || config->standby > BME280_STANDBY_20_MS) return BME280_ERR_ARGUMENT;
    bme280_status_t result = bme280_sleep(device);
    if (result != BME280_OK) return result;
    /* ctrl_hum must be written before ctrl_meas for humidity oversampling to latch. */
    result = write_register(device, REG_CTRL_HUM, (uint8_t)config->humidity_oversampling);
    if (result != BME280_OK) return result;
    result = write_register(device, REG_CONFIG, (uint8_t)((config->standby << 5) | (config->filter << 2)));
    if (result != BME280_OK) return result;
    result = write_register(device, REG_CTRL_MEAS, (uint8_t)((config->temperature_oversampling << 5) | (config->pressure_oversampling << 2)));
    if (result == BME280_OK) device->config = *config;
    return result;
}

bme280_status_t bme280_init(bme280_t *device, const bme280_bus_t *bus, uint8_t address, const bme280_config_t *config) {
    if (!device || !bus || !bus->read || !bus->write || (address != BME280_I2C_ADDRESS_LOW && address != BME280_I2C_ADDRESS_HIGH)) return BME280_ERR_ARGUMENT;
    *device = (bme280_t){.bus = *bus, .address = address};
    uint8_t chip_id;
    bme280_status_t result = read_registers(device, REG_CHIP_ID, &chip_id, 1);
    if (result != BME280_OK) return result;
    if (chip_id != BME280_CHIP_ID) return BME280_ERR_NOT_FOUND;
    result = write_register(device, REG_RESET, RESET_COMMAND);
    if (result != BME280_OK) return result;
    delay_ms(device, 2);
    result = wait_for_clear(device, STATUS_NVM_COPYING, 10);
    if (result != BME280_OK) return result;
    result = read_calibration(device);
    if (result != BME280_OK) return result;
    device->initialized = true;
    return bme280_configure(device, config ? config : &(bme280_config_t){BME280_OVERSAMPLING_X2, BME280_OVERSAMPLING_X16, BME280_OVERSAMPLING_X1, BME280_FILTER_X4, BME280_STANDBY_500_MS});
}

bme280_status_t bme280_sleep(bme280_t *device) {
    if (!device || !device->initialized) return BME280_ERR_ARGUMENT;
    uint8_t control = (uint8_t)((device->config.temperature_oversampling << 5) | (device->config.pressure_oversampling << 2));
    return write_register(device, REG_CTRL_MEAS, control);
}

static bme280_status_t read_compensated(bme280_t *device, bme280_reading_t *reading) {
    uint8_t data[8];
    bme280_status_t result = read_registers(device, REG_DATA, data, sizeof(data));
    if (result != BME280_OK) return result;
    const bme280_calibration_t *c = &device->calibration;
    int32_t adc_p = ((int32_t)data[0] << 12) | ((int32_t)data[1] << 4) | (data[2] >> 4);
    int32_t adc_t = ((int32_t)data[3] << 12) | ((int32_t)data[4] << 4) | (data[5] >> 4);
    int32_t adc_h = ((int32_t)data[6] << 8) | data[7];
    double v1 = ((double)adc_t / 16384.0 - (double)c->t1 / 1024.0) * c->t2;
    double v2 = (((double)adc_t / 131072.0 - (double)c->t1 / 8192.0) * ((double)adc_t / 131072.0 - (double)c->t1 / 8192.0)) * c->t3;
    double t_fine = v1 + v2;
    double temperature = t_fine / 5120.0;
    v1 = t_fine / 2.0 - 64000.0;
    v2 = v1 * v1 * c->p6 / 32768.0;
    v2 = v2 + v1 * c->p5 * 2.0;
    v2 = v2 / 4.0 + c->p4 * 65536.0;
    v1 = (c->p3 * v1 * v1 / 524288.0 + c->p2 * v1) / 524288.0;
    v1 = (1.0 + v1 / 32768.0) * c->p1;
    if (v1 == 0.0) return BME280_ERR_INVALID_MEASUREMENT;
    double pressure = 1048576.0 - adc_p;
    pressure = (pressure - v2 / 4096.0) * 6250.0 / v1;
    v1 = c->p9 * pressure * pressure / 2147483648.0;
    v2 = pressure * c->p8 / 32768.0;
    pressure += (v1 + v2 + c->p7) / 16.0;
    double humidity = t_fine - 76800.0;
    humidity = (adc_h - (c->h4 * 64.0 + c->h5 / 16384.0 * humidity)) * (c->h2 / 65536.0 * (1.0 + c->h6 / 67108864.0 * humidity * (1.0 + c->h3 / 67108864.0 * humidity)));
    humidity *= 1.0 - c->h1 * humidity / 524288.0;
    if (humidity < 0.0) humidity = 0.0;
    if (humidity > 100.0) humidity = 100.0;
    reading->temperature_c = (float)temperature;
    reading->pressure_pa = (float)pressure;
    reading->humidity_percent = (float)humidity;
    return BME280_OK;
}

bme280_status_t bme280_read_forced(bme280_t *device, bme280_reading_t *reading, uint32_t timeout_ms) {
    if (!device || !reading || !device->initialized) return BME280_ERR_ARGUMENT;
    uint8_t control = (uint8_t)((device->config.temperature_oversampling << 5) | (device->config.pressure_oversampling << 2) | 0x01u);
    bme280_status_t result = write_register(device, REG_CTRL_MEAS, control);
    if (result != BME280_OK) return result;
    /* The sensor needs up to 1.25 ms before the measuring flag is observable. */
    delay_ms(device, 2);
    result = wait_for_clear(device, STATUS_MEASURING, timeout_ms);
    return result == BME280_OK ? read_compensated(device, reading) : result;
}

bme280_status_t bme280_read_normal(bme280_t *device, bme280_reading_t *reading) {
    if (!device || !reading || !device->initialized) return BME280_ERR_ARGUMENT;
    return read_compensated(device, reading);
}
