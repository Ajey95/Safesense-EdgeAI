#include "forecast.h"

#include <math.h>
#include <stddef.h>

#include "forecast_model_data.h"

static const float sensor_scale[5] = {10.0f, 20.0f, 1000.0f, 100000.0f, 1000.0f};

const char *forecast_model_sha256(void) {
    return SAFESENSE_FORECAST_MODEL_SHA256;
}

bool forecast_predict(const float history[61][5], uint8_t room, float out[6][5]) {
    if (!history || !out || room >= 5) return false;
    float input[70] = {0};
    for (unsigned minute = 0; minute <= 60; minute += 5) {
        for (unsigned channel = 0; channel < 5; ++channel) {
            const float value = history[minute][channel];
            if (!isfinite(value)) return false;
            input[(minute / 5) * 5 + channel] = value / sensor_scale[channel];
        }
    }
    input[65 + room] = 1.0f;
    for (unsigned i = 0; i < 70; ++i) {
        if (forecast_x_scale[i] <= 0 || !isfinite(forecast_x_scale[i])) return false;
        input[i] = (input[i] - forecast_x_mean[i]) / forecast_x_scale[i];
    }
    float hidden1[48], hidden2[24], result[30];
    for (unsigned j = 0; j < 48; ++j) {
        float total = forecast_b0[j];
        for (unsigned i = 0; i < 70; ++i) total += input[i] * forecast_w0[i * 48 + j];
        hidden1[j] = fmaxf(0.0f, total);
    }
    for (unsigned j = 0; j < 24; ++j) {
        float total = forecast_b1[j];
        for (unsigned i = 0; i < 48; ++i) total += hidden1[i] * forecast_w1[i * 24 + j];
        hidden2[j] = fmaxf(0.0f, total);
    }
    for (unsigned j = 0; j < 30; ++j) {
        float total = forecast_b2[j];
        for (unsigned i = 0; i < 24; ++i) total += hidden2[i] * forecast_w2[i * 30 + j];
        result[j] = total * forecast_y_scale[j] + forecast_y_mean[j];
        const unsigned channel = j % 5;
        const float value = history[60][channel] + result[j] * sensor_scale[channel];
        if (!isfinite(value)) return false;
        out[j / 5][channel] = value;
    }
    return true;
}
