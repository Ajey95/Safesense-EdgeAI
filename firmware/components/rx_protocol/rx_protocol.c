#include "rx_protocol.h"

#include <ctype.h>
#include <math.h>
#include <stdio.h>
#include <string.h>

#include "cJSON.h"

static const cJSON *field(const cJSON *object, const char *name) {
    return cJSON_GetObjectItemCaseSensitive(object, name);
}

static int valid_id(const cJSON *item, size_t capacity) {
    if (!cJSON_IsString(item) || !item->valuestring) return 0;
    const char *value = item->valuestring;
    const size_t length = strlen(value);
    if (length == 0 || length >= capacity) return 0;
    for (size_t i = 0; i < length; ++i) {
        const unsigned char ch = (unsigned char)value[i];
        if (!(isalnum(ch) || ch == '-' || ch == '_' || ch == '.' || ch == ':')) return 0;
    }
    return 1;
}

static int numeric(const cJSON *item, double minimum, double maximum) {
    return cJSON_IsNumber(item) && isfinite(item->valuedouble) &&
           item->valuedouble >= minimum && item->valuedouble <= maximum;
}

static int numeric_or_null(const cJSON *item, double minimum, double maximum) {
    return cJSON_IsNull(item) || numeric(item, minimum, maximum);
}

static int unique_object_keys(const cJSON *object) {
    if (!cJSON_IsObject(object)) return 0;
    for (const cJSON *a = object->child; a; a = a->next) {
        if (!a->string) return 0;
        for (const cJSON *b = a->next; b; b = b->next)
            if (b->string && strcmp(a->string, b->string) == 0) return 0;
        if (cJSON_IsObject(a) && !unique_object_keys(a)) return 0;
    }
    return 1;
}

static int valid_bme(const cJSON *bme) {
    if (!cJSON_IsObject(bme)) return 0;
    const cJSON *healthy = field(bme, "sensor_healthy");
    const cJSON *temperature = field(bme, "temperature_c");
    const cJSON *humidity = field(bme, "humidity_pct");
    const cJSON *pressure = field(bme, "pressure_pa");
    const cJSON *gas = field(bme, "gas_resistance_ohm");
    const cJSON *gas_valid = field(bme, "gas_valid");
    const cJSON *stable = field(bme, "heat_stable");
    const int legacy_no_stability = stable == NULL;
    if (!cJSON_IsBool(healthy) || !cJSON_IsBool(gas_valid) ||
        (!legacy_no_stability && !cJSON_IsBool(stable))) return 0;
    if (cJSON_IsTrue(healthy)) {
        if (!numeric(temperature, -40, 100) || !numeric(humidity, 0, 100) ||
            !numeric(pressure, 30000, 110000)) return 0;
    } else if (!cJSON_IsNull(temperature) || !cJSON_IsNull(humidity) ||
               !cJSON_IsNull(pressure)) return 0;
    if (cJSON_IsTrue(gas_valid)) {
        if (!cJSON_IsTrue(healthy) || (!legacy_no_stability && !cJSON_IsTrue(stable)) ||
            !numeric(gas, 0.001, 1000000000)) return 0;
    } else if (!cJSON_IsNull(gas)) return 0;
    return 1;
}

int rx_parse_tx_event(const char *json, size_t length, rx_event_info_t *out) {
    if (!json || !out || length == 0 || length >= RX_MAX_JSON_BYTES) return -1;
    memset(out, 0, sizeof(*out));
    const char *end = NULL;
    cJSON *root = cJSON_ParseWithLengthOpts(json, length + 1u, &end, 1);
    if (!root) return -1;
    const cJSON *schema = field(root, "schema_version");
    const cJSON *event_id = field(root, "event_id");
    const cJSON *device_id = field(root, "tx_device_id");
    const cJSON *sequence = field(root, "sequence");
    const cJSON *mq = field(root, "mq135");
    const cJSON *risk = field(root, "gas_risk");
    const cJSON *adc = field(mq, "adc_raw");
    const cJSON *calibrated = field(mq, "calibrated");
    const int valid = end == json + length && unique_object_keys(root) &&
        numeric(schema, 1, 1) && valid_id(event_id, sizeof(out->event_id)) &&
        valid_id(device_id, sizeof(out->tx_device_id)) &&
        numeric(sequence, 0, 4294967295.0) && floor(sequence->valuedouble) == sequence->valuedouble &&
        cJSON_IsNull(field(root, "observed_at")) &&
        valid_bme(field(root, "bme680")) && cJSON_IsObject(mq) &&
        numeric_or_null(adc, 0, 4095) &&
        (cJSON_IsNull(adc) || floor(adc->valuedouble) == adc->valuedouble) &&
        cJSON_IsFalse(calibrated) && cJSON_IsString(risk) &&
        strcmp(risk->valuestring, "UNAVAILABLE") == 0;
    if (valid) {
        snprintf(out->event_id, sizeof(out->event_id), "%s", event_id->valuestring);
        snprintf(out->tx_device_id, sizeof(out->tx_device_id), "%s", device_id->valuestring);
    }
    cJSON_Delete(root);
    return valid ? 0 : -1;
}

int rx_parse_forward_ack(const char *json, size_t length, char event_id_out[64]) {
    if (!json || !event_id_out || length == 0 || length >= RX_MAX_JSON_BYTES) return -1;
    event_id_out[0] = '\0';
    const char *end = NULL;
    cJSON *root = cJSON_ParseWithLengthOpts(json, length + 1u, &end, 1);
    if (!root) return -1;
    const cJSON *event_id = field(root, "event_id");
    const int valid = end == json + length && unique_object_keys(root) &&
        cJSON_GetArraySize(root) == 1 && valid_id(event_id, 64);
    if (valid) snprintf(event_id_out, 64, "%s", event_id->valuestring);
    cJSON_Delete(root);
    return valid ? 0 : -1;
}
