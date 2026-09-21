#include "bme680_driver.h"

#include <math.h>

static uint16_t u16le(const uint8_t *data)
{
    return (uint16_t)data[0] | ((uint16_t)data[1] << 8);
}

static int16_t s16le(const uint8_t *data)
{
    return (int16_t)u16le(data);
}

bme680_status_t bme680_validate_chip_id(uint8_t chip_id)
{
    return chip_id == BME680_CHIP_ID ? BME680_OK : BME680_ERR_NOT_FOUND;
}

bme680_status_t bme680_parse_calibration(const uint8_t *r,
                                         size_t length,
                                         bme680_calibration_t *c)
{
    if (r == NULL || c == NULL || length != BME680_CALIBRATION_LENGTH) {
        return BME680_ERR_ARGUMENT;
    }

    *c = (bme680_calibration_t){
        .t1 = u16le(&r[31]),
        .t2 = s16le(&r[0]),
        .t3 = (int8_t)r[2],
        .p1 = u16le(&r[4]),
        .p2 = s16le(&r[6]),
        .p3 = (int8_t)r[8],
        .p4 = s16le(&r[10]),
        .p5 = s16le(&r[12]),
        .p6 = (int8_t)r[15],
        .p7 = (int8_t)r[14],
        .p8 = s16le(&r[18]),
        .p9 = s16le(&r[20]),
        .p10 = r[22],
        .h1 = (uint16_t)(((uint16_t)r[25] << 4) | (r[24] & 0x0Fu)),
        .h2 = (uint16_t)(((uint16_t)r[23] << 4) | (r[24] >> 4)),
        .h3 = (int8_t)r[26],
        .h4 = (int8_t)r[27],
        .h5 = (int8_t)r[28],
        .h6 = r[29],
        .h7 = (int8_t)r[30],
        .gh1 = (int8_t)r[35],
        .gh2 = s16le(&r[33]),
        .gh3 = (int8_t)r[36],
        .res_heat_val = (int8_t)r[37],
        .res_heat_range = (uint8_t)((r[39] & 0x30u) >> 4),
        .range_sw_err = (int8_t)((int8_t)(r[41] & 0xF0u) / 16),
    };

    if (c->t1 == 0u || c->p1 == 0u) {
        return BME680_ERR_CALIBRATION;
    }
    return BME680_OK;
}

static float compensate_temperature(const bme680_calibration_t *c,
                                    uint32_t adc,
                                    float *t_fine)
{
    const float var1 = (((float)adc / 16384.0f) - ((float)c->t1 / 1024.0f)) * (float)c->t2;
    const float delta = ((float)adc / 131072.0f) - ((float)c->t1 / 8192.0f);
    const float var2 = delta * delta * ((float)c->t3 * 16.0f);
    *t_fine = var1 + var2;
    return *t_fine / 5120.0f;
}

static float compensate_pressure(const bme680_calibration_t *c,
                                 uint32_t adc,
                                 float t_fine)
{
    float var1 = (t_fine / 2.0f) - 64000.0f;
    float var2 = var1 * var1 * ((float)c->p6 / 131072.0f);
    var2 += var1 * (float)c->p5 * 2.0f;
    var2 = (var2 / 4.0f) + ((float)c->p4 * 65536.0f);
    var1 = ((((float)c->p3 * var1 * var1) / 16384.0f) + ((float)c->p2 * var1)) / 524288.0f;
    var1 = (1.0f + (var1 / 32768.0f)) * (float)c->p1;
    if (fabsf(var1) < 0.000001f) {
        return 0.0f;
    }

    float pressure = (1048576.0f - (float)adc - (var2 / 4096.0f)) * 6250.0f / var1;
    var1 = (float)c->p9 * pressure * pressure / 2147483648.0f;
    var2 = pressure * ((float)c->p8 / 32768.0f);
    const float var3 = (pressure / 256.0f) * (pressure / 256.0f) *
                       (pressure / 256.0f) * ((float)c->p10 / 131072.0f);
    return pressure + (var1 + var2 + var3 + ((float)c->p7 * 128.0f)) / 16.0f;
}

static float compensate_humidity(const bme680_calibration_t *c,
                                 uint16_t adc,
                                 float temperature_c)
{
    const float var1 = (float)adc - ((float)c->h1 * 16.0f + ((float)c->h3 / 2.0f) * temperature_c);
    const float var2 = var1 * ((float)c->h2 / 262144.0f) *
                       (1.0f + ((float)c->h4 / 16384.0f) * temperature_c +
                        ((float)c->h5 / 1048576.0f) * temperature_c * temperature_c);
    float humidity = var2 + (((float)c->h6 / 16384.0f) +
                             ((float)c->h7 / 2097152.0f) * temperature_c) * var2 * var2;
    if (humidity < 0.0f) {
        humidity = 0.0f;
    } else if (humidity > 100.0f) {
        humidity = 100.0f;
    }
    return humidity;
}

static float compensate_gas(const bme680_calibration_t *c, uint16_t adc, uint8_t range)
{
    static const float k1[16] = {
        0.0f, 0.0f, 0.0f, 0.0f, 0.0f, -1.0f, 0.0f, -0.8f,
        0.0f, 0.0f, -0.2f, -0.5f, 0.0f, -1.0f, 0.0f, 0.0f,
    };
    static const float k2[16] = {
        0.0f, 0.0f, 0.0f, 0.0f, 0.1f, 0.7f, 0.0f, -0.8f,
        -0.1f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f,
    };
    const float var1 = 1340.0f + 5.0f * (float)c->range_sw_err;
    const float var2 = var1 * (1.0f + k1[range] / 100.0f);
    const float var3 = 1.0f + k2[range] / 100.0f;
    const float scale = (float)(1u << range);
    return 1.0f / (var3 * 0.000000125f * scale * ((((float)adc - 512.0f) / var2) + 1.0f));
}

bme680_status_t bme680_compensate(const bme680_calibration_t *c,
                                  const bme680_raw_sample_t *raw,
                                  bme680_reading_t *reading)
{
    if (c == NULL || raw == NULL || reading == NULL) {
        return BME680_ERR_ARGUMENT;
    }
    if (!raw->new_data || raw->gas_range > 15u || c->p1 == 0u) {
        return BME680_ERR_INVALID_MEASUREMENT;
    }

    float t_fine;
    reading->temperature_c = compensate_temperature(c, raw->temperature_adc, &t_fine);
    reading->pressure_pa = compensate_pressure(c, raw->pressure_adc, t_fine);
    if (reading->pressure_pa <= 0.0f) {
        return BME680_ERR_INVALID_MEASUREMENT;
    }
    reading->humidity_percent = compensate_humidity(c, raw->humidity_adc, reading->temperature_c);
    reading->gas_valid = raw->gas_valid;
    reading->heat_stable = raw->heat_stable;
    reading->gas_resistance_ohm = raw->gas_valid && raw->heat_stable
                                      ? compensate_gas(c, raw->gas_adc, raw->gas_range)
                                      : 0.0f;
    return BME680_OK;
}

uint8_t bme680_heater_resistance(const bme680_calibration_t *c,
                                 uint16_t target_temperature_c,
                                 int8_t ambient_temperature_c)
{
    if (c == NULL) {
        return 0u;
    }
    if (target_temperature_c > 400u) {
        target_temperature_c = 400u;
    }
    const float var1 = (float)c->gh1 / 16.0f + 49.0f;
    const float var2 = ((float)c->gh2 / 32768.0f) * 0.0005f + 0.00235f;
    const float var3 = (float)c->gh3 / 1024.0f;
    const float var4 = var1 * (1.0f + var2 * (float)target_temperature_c);
    const float var5 = var4 + var3 * (float)ambient_temperature_c;
    const float range_correction = 4.0f / (4.0f + (float)c->res_heat_range);
    const float value_correction = 1.0f / (1.0f + (float)c->res_heat_val * 0.002f);
    const float encoded = 3.4f * (var5 * range_correction * value_correction - 25.0f);
    return encoded <= 0.0f ? 0u : (encoded >= 255.0f ? 255u : (uint8_t)encoded);
}

uint8_t bme680_encode_heater_duration(uint16_t duration_ms)
{
    if (duration_ms >= 0xFC0u) {
        return 0xFFu;
    }
    uint8_t factor = 0u;
    while (duration_ms > 0x3Fu) {
        duration_ms /= 4u;
        factor++;
    }
    return (uint8_t)(duration_ms + (uint16_t)factor * 64u);
}
