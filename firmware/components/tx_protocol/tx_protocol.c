#include "tx_protocol.h"

#include <ctype.h>
#include <math.h>
#include <stdio.h>
#include <string.h>

static bool valid_id(const char *value, size_t max_length) {
    if (!value || !value[0]) return false;
    size_t length = 0;
    while (value[length]) {
        const unsigned char ch = (unsigned char)value[length];
        if (!(isalnum(ch) || ch == '-' || ch == '_' || ch == '.' || ch == ':')) return false;
        if (++length >= max_length) return false;
    }
    return true;
}

int tx_format_json(char *output, size_t capacity, const tx_sample_t *sample) {
    if (!output || !capacity || !sample || !valid_id(sample->event_id, 64) ||
        !valid_id(sample->tx_device_id, 80) ||
        (sample->mq135_valid && (sample->mq135_adc_raw < 0 || sample->mq135_adc_raw > 4095))) return -1;
    if (sample->bme_healthy && (!isfinite(sample->temperature_c) ||
        !isfinite(sample->humidity_pct) || !isfinite(sample->pressure_pa) ||
        sample->temperature_c < -40.0f || sample->temperature_c > 100.0f ||
        sample->humidity_pct < 0.0f || sample->humidity_pct > 100.0f ||
        sample->pressure_pa < 30000.0f || sample->pressure_pa > 110000.0f)) return -1;

    char temperature[24] = "null", humidity[24] = "null", pressure[24] = "null";
    char gas[24] = "null", mq[16] = "null";
    if (sample->bme_healthy) {
        snprintf(temperature, sizeof(temperature), "%.2f", sample->temperature_c);
        snprintf(humidity, sizeof(humidity), "%.2f", sample->humidity_pct);
        snprintf(pressure, sizeof(pressure), "%.2f", sample->pressure_pa);
    }
    const bool gas_valid = sample->bme_healthy && sample->gas_valid && sample->heat_stable &&
        isfinite(sample->gas_resistance_ohm) && sample->gas_resistance_ohm > 0.0f;
    if (gas_valid) snprintf(gas, sizeof(gas), "%.2f", sample->gas_resistance_ohm);
    if (sample->mq135_valid) snprintf(mq, sizeof(mq), "%d", sample->mq135_adc_raw);

    const int length = snprintf(output, capacity,
        "{\"schema_version\":1,\"event_id\":\"%s\",\"tx_device_id\":\"%s\",\"sequence\":%lu,\"observed_at\":null,"
        "\"bme680\":{\"sensor_healthy\":%s,\"temperature_c\":%s,\"humidity_pct\":%s,\"pressure_pa\":%s,\"gas_resistance_ohm\":%s,\"gas_valid\":%s,\"heat_stable\":%s},"
        "\"mq135\":{\"adc_raw\":%s,\"calibrated\":false},\"gas_risk\":\"UNAVAILABLE\"}",
        sample->event_id, sample->tx_device_id, (unsigned long)sample->sequence,
        sample->bme_healthy ? "true" : "false", temperature, humidity, pressure,
        gas, gas_valid ? "true" : "false",
        sample->bme_healthy && sample->heat_stable ? "true" : "false", mq);
    return length >= 0 && (size_t)length < capacity ? length : -1;
}

typedef struct { const char *cursor; const char *end; } json_cursor_t;

static void skip_space(json_cursor_t *json) {
    while (json->cursor < json->end && isspace((unsigned char)*json->cursor)) json->cursor++;
}

static bool consume(json_cursor_t *json, char expected) {
    skip_space(json);
    if (json->cursor >= json->end || *json->cursor != expected) return false;
    json->cursor++;
    return true;
}

static bool parse_string(json_cursor_t *json, char *out, size_t capacity) {
    if (!consume(json, '"') || capacity == 0) return false;
    size_t written = 0;
    while (json->cursor < json->end && *json->cursor != '"') {
        const unsigned char ch = (unsigned char)*json->cursor++;
        if (ch < 0x20 || ch == '\\' || written + 1 >= capacity) return false;
        out[written++] = (char)ch;
    }
    if (json->cursor >= json->end || *json->cursor != '"') return false;
    json->cursor++;
    out[written] = '\0';
    return true;
}

bool tx_ack_matches(const char *json_text, size_t length, const char *event_id) {
    if (!json_text || !valid_id(event_id, 64) || length > 256) return false;
    json_cursor_t json = {.cursor = json_text, .end = json_text + length};
    if (!consume(&json, '{')) return false;
    bool have_event = false, have_status = false;
    char ack_event[64] = {0}, status[16] = {0};
    while (true) {
        skip_space(&json);
        if (json.cursor < json.end && *json.cursor == '}') { json.cursor++; break; }
        char key[16], value[64];
        if (!parse_string(&json, key, sizeof(key)) || !consume(&json, ':') ||
            !parse_string(&json, value, sizeof(value))) return false;
        if (strcmp(key, "event_id") == 0 && !have_event) {
            memcpy(ack_event, value, strlen(value) + 1); have_event = true;
        } else if (strcmp(key, "status") == 0 && !have_status && strlen(value) < sizeof(status)) {
            memcpy(status, value, strlen(value) + 1); have_status = true;
        } else return false;
        skip_space(&json);
        if (json.cursor < json.end && *json.cursor == ',') { json.cursor++; continue; }
        if (json.cursor < json.end && *json.cursor == '}') { json.cursor++; break; }
        return false;
    }
    skip_space(&json);
    return json.cursor == json.end && have_event && have_status &&
        strcmp(ack_event, event_id) == 0 && strcmp(status, "ACCEPTED") == 0;
}
