#include "bme680_esp_idf.h"

#include "esp_err.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#include <string.h>

#define REG_COEFF3 0x00u
#define REG_FIELD0 0x1Du
#define REG_RES_HEAT0 0x5Au
#define REG_GAS_WAIT0 0x64u
#define REG_CTRL_GAS_0 0x70u
#define REG_CTRL_GAS_1 0x71u
#define REG_CTRL_HUM 0x72u
#define REG_CTRL_MEAS 0x74u
#define REG_CONFIG 0x75u
#define REG_COEFF1 0x8Au
#define REG_CHIP_ID 0xD0u
#define REG_SOFT_RESET 0xE0u
#define REG_COEFF2 0xE1u
#define RESET_COMMAND 0xB6u
#define NEW_DATA_MASK 0x80u
#define GAS_VALID_MASK 0x20u
#define HEAT_STABLE_MASK 0x10u
#define GAS_RANGE_MASK 0x0Fu

static bme680_status_t read_registers(bme680_esp_idf_t *device,
                                      uint8_t reg,
                                      uint8_t *data,
                                      size_t length)
{
    if (device == NULL || device->handle == NULL || data == NULL || length == 0u) {
        return BME680_ERR_ARGUMENT;
    }
    return i2c_master_transmit_receive(device->handle, &reg, 1u, data, length, 100) == ESP_OK
               ? BME680_OK
               : BME680_ERR_BUS;
}

static bme680_status_t write_register(bme680_esp_idf_t *device, uint8_t reg, uint8_t value)
{
    const uint8_t packet[2] = {reg, value};
    if (device == NULL || device->handle == NULL) {
        return BME680_ERR_ARGUMENT;
    }
    return i2c_master_transmit(device->handle, packet, sizeof(packet), 100) == ESP_OK
               ? BME680_OK
               : BME680_ERR_BUS;
}

bme680_esp_idf_config_t bme680_esp_idf_default_config(void)
{
    return (bme680_esp_idf_config_t){
        .heater_temperature_c = 320u,
        .heater_duration_ms = 150u,
        .ambient_temperature_c = 25,
        .i2c_frequency_hz = 100000u,
    };
}

static bme680_status_t read_calibration(bme680_esp_idf_t *device)
{
    uint8_t coefficients[BME680_CALIBRATION_LENGTH];
    bme680_status_t status = read_registers(device, REG_COEFF1, coefficients, 23u);
    if (status == BME680_OK) {
        status = read_registers(device, REG_COEFF2, &coefficients[23], 14u);
    }
    if (status == BME680_OK) {
        status = read_registers(device, REG_COEFF3, &coefficients[37], 5u);
    }
    return status == BME680_OK
               ? bme680_parse_calibration(coefficients, sizeof(coefficients), &device->calibration)
               : status;
}

static bme680_status_t configure_sensor(bme680_esp_idf_t *device)
{
    const uint8_t heater = bme680_heater_resistance(&device->calibration,
                                                     device->config.heater_temperature_c,
                                                     device->config.ambient_temperature_c);
    if (heater == 0u) {
        return BME680_ERR_HEATER;
    }
    bme680_status_t status = write_register(device, REG_RES_HEAT0, heater);
    if (status == BME680_OK) {
        status = write_register(device, REG_GAS_WAIT0,
                                bme680_encode_heater_duration(device->config.heater_duration_ms));
    }
    if (status == BME680_OK) {
        status = write_register(device, REG_CTRL_HUM, 0x02u); /* humidity x2 */
    }
    if (status == BME680_OK) {
        status = write_register(device, REG_CONFIG, 0x08u); /* IIR coefficient 3 */
    }
    if (status == BME680_OK) {
        status = write_register(device, REG_CTRL_GAS_0, 0x00u); /* heater enabled */
    }
    if (status == BME680_OK) {
        status = write_register(device, REG_CTRL_GAS_1, 0x10u); /* run gas, profile 0 */
    }
    if (status == BME680_OK) {
        status = write_register(device, REG_CTRL_MEAS, 0x4Cu); /* temp x2, pressure x4, sleep */
    }
    return status;
}

bme680_status_t bme680_esp_idf_init(bme680_esp_idf_t *device,
                                    i2c_master_bus_handle_t bus,
                                    uint8_t address,
                                    const bme680_esp_idf_config_t *configured)
{
    if (device == NULL || bus == NULL ||
        (address != BME680_I2C_ADDRESS_LOW && address != BME680_I2C_ADDRESS_HIGH)) {
        return BME680_ERR_ARGUMENT;
    }
    const bme680_esp_idf_config_t fallback = bme680_esp_idf_default_config();
    const bme680_esp_idf_config_t *config = configured != NULL ? configured : &fallback;
    if (config->heater_temperature_c == 0u || config->heater_duration_ms == 0u ||
        config->i2c_frequency_hz == 0u) {
        return BME680_ERR_ARGUMENT;
    }

    *device = (bme680_esp_idf_t){.config = *config};
    const i2c_device_config_t device_config = {
        .dev_addr_length = I2C_ADDR_BIT_LEN_7,
        .device_address = address,
        .scl_speed_hz = config->i2c_frequency_hz,
    };
    if (i2c_master_bus_add_device(bus, &device_config, &device->handle) != ESP_OK) {
        return BME680_ERR_BUS;
    }

    uint8_t chip_id;
    bme680_status_t status = read_registers(device, REG_CHIP_ID, &chip_id, 1u);
    if (status == BME680_OK) {
        status = bme680_validate_chip_id(chip_id);
    }
    if (status == BME680_OK) {
        status = write_register(device, REG_SOFT_RESET, RESET_COMMAND);
    }
    if (status == BME680_OK) {
        vTaskDelay(pdMS_TO_TICKS(10u));
        status = read_calibration(device);
    }
    if (status == BME680_OK) {
        status = configure_sensor(device);
    }
    if (status != BME680_OK) {
        bme680_esp_idf_deinit(device);
        return status;
    }
    device->initialized = true;
    return BME680_OK;
}

bme680_status_t bme680_esp_idf_read_forced(bme680_esp_idf_t *device,
                                           bme680_reading_t *reading,
                                           uint32_t timeout_ms)
{
    if (device == NULL || reading == NULL || !device->initialized || timeout_ms == 0u) {
        return BME680_ERR_ARGUMENT;
    }
    bme680_status_t status = write_register(device, REG_CTRL_MEAS, 0x4Du);
    if (status != BME680_OK) {
        return status;
    }

    uint8_t field[17];
    for (uint32_t elapsed = 0u; elapsed <= timeout_ms; elapsed += 5u) {
        status = read_registers(device, REG_FIELD0, field, sizeof(field));
        if (status != BME680_OK) {
            return status;
        }
        if ((field[0] & NEW_DATA_MASK) != 0u) {
            const bme680_raw_sample_t raw = {
                .pressure_adc = ((uint32_t)field[2] << 12) |
                                ((uint32_t)field[3] << 4) | (field[4] >> 4),
                .temperature_adc = ((uint32_t)field[5] << 12) |
                                   ((uint32_t)field[6] << 4) | (field[7] >> 4),
                .humidity_adc = (uint16_t)(((uint16_t)field[8] << 8) | field[9]),
                .gas_adc = (uint16_t)(((uint16_t)field[13] << 2) | (field[14] >> 6)),
                .gas_range = field[14] & GAS_RANGE_MASK,
                .new_data = true,
                .gas_valid = (field[14] & GAS_VALID_MASK) != 0u,
                .heat_stable = (field[14] & HEAT_STABLE_MASK) != 0u,
            };
            return bme680_compensate(&device->calibration, &raw, reading);
        }
        vTaskDelay(pdMS_TO_TICKS(5u));
    }
    return BME680_ERR_TIMEOUT;
}

void bme680_esp_idf_deinit(bme680_esp_idf_t *device)
{
    if (device == NULL) {
        return;
    }
    if (device->handle != NULL) {
        i2c_master_bus_rm_device(device->handle);
    }
    memset(device, 0, sizeof(*device));
}
