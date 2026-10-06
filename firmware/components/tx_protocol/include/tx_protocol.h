#pragma once

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

typedef struct {
    const char *event_id;
    const char *tx_device_id;
    uint32_t sequence;
    bool bme_healthy;
    float temperature_c;
    float humidity_pct;
    float pressure_pa;
    bool gas_valid;
    bool heat_stable;
    float gas_resistance_ohm;
    bool mq135_valid;
    int mq135_adc_raw;
} tx_sample_t;

int tx_format_json(char *output, size_t capacity, const tx_sample_t *sample);
bool tx_ack_matches(const char *json, size_t length, const char *event_id);
