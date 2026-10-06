#include <assert.h>
#include <stdio.h>
#include <string.h>

#include "tx_protocol.h"

static void test_json_reports_raw_values_without_inventing_risk(void) {
    char json[512];
    const tx_sample_t sample = {
        .event_id = "tx-001", .tx_device_id = "safesense-tx-01", .sequence = 7,
        .bme_healthy = true, .temperature_c = 30.5f,
        .humidity_pct = 67.2f, .pressure_pa = 97380.0f,
        .gas_valid = true, .heat_stable = true, .gas_resistance_ohm = 2637.0f,
        .mq135_valid = true, .mq135_adc_raw = 0,
    };
    assert(tx_format_json(json, sizeof(json), &sample) > 0);
    assert(strcmp(json,
        "{\"schema_version\":1,\"event_id\":\"tx-001\",\"tx_device_id\":\"safesense-tx-01\",\"sequence\":7,\"observed_at\":null,"
        "\"bme680\":{\"sensor_healthy\":true,\"temperature_c\":30.50,\"humidity_pct\":67.20,\"pressure_pa\":97380.00,\"gas_resistance_ohm\":2637.00,\"gas_valid\":true,\"heat_stable\":true},"
        "\"mq135\":{\"adc_raw\":0,\"calibrated\":false},\"gas_risk\":\"UNAVAILABLE\"}") == 0);
}

static void test_invalid_gas_and_missing_sensor_use_null(void) {
    char json[512];
    const tx_sample_t sample = {.event_id="tx-002", .tx_device_id="tx-01", .bme_healthy=true,
        .temperature_c=31.0f, .humidity_pct=50.0f, .pressure_pa=100000.0f};
    assert(tx_format_json(json, sizeof(json), &sample) > 0);
    assert(strstr(json, "\"gas_resistance_ohm\":null,\"gas_valid\":false,\"heat_stable\":false") != NULL);
    assert(strstr(json, "\"adc_raw\":null") != NULL);
    tx_sample_t missing = sample;
    missing.bme_healthy = false;
    assert(tx_format_json(json, sizeof(json), &missing) > 0);
    assert(strstr(json, "\"temperature_c\":null,\"humidity_pct\":null,\"pressure_pa\":null") != NULL);
}

static void test_rejects_malformed_identifiers_and_short_buffer(void) {
    char json[32];
    tx_sample_t sample = {.event_id="tx-003", .tx_device_id="bad\"id"};
    assert(tx_format_json(json, sizeof(json), &sample) < 0);
    sample.tx_device_id = "tx-01";
    assert(tx_format_json(json, sizeof(json), &sample) < 0);
}

static void test_ack_requires_exact_id_and_status(void) {
    const char accepted[] = "{\"event_id\":\"tx-001\",\"status\":\"ACCEPTED\"}";
    const char wrong_id[] = "{\"event_id\":\"tx-001-extra\",\"status\":\"ACCEPTED\"}";
    const char wrong_status[] = "{\"event_id\":\"tx-001\",\"status\":\"REJECTED\"}";
    assert(tx_ack_matches(accepted, strlen(accepted), "tx-001"));
    assert(!tx_ack_matches(wrong_id, strlen(wrong_id), "tx-001"));
    assert(!tx_ack_matches(wrong_status, strlen(wrong_status), "tx-001"));
    assert(!tx_ack_matches("junk", 4, "tx-001"));
    assert(!tx_ack_matches(accepted, strlen(accepted) - 1, "tx-001"));
}

int main(void) {
    test_json_reports_raw_values_without_inventing_risk();
    test_invalid_gas_and_missing_sensor_use_null();
    test_rejects_malformed_identifiers_and_short_buffer();
    test_ack_requires_exact_id_and_status();
    puts("tx_protocol tests passed");
}
