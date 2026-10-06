#include <assert.h>
#include <stdio.h>
#include <string.h>

#include "rx_protocol.h"

static const char valid[] =
    "{\"schema_version\":1,\"event_id\":\"tx-0123456789abcdef\",\"tx_device_id\":\"safesense-tx-01\","
    "\"sequence\":7,\"observed_at\":null,"
    "\"bme680\":{\"sensor_healthy\":true,\"temperature_c\":29.80,\"humidity_pct\":72.00,"
    "\"pressure_pa\":97368.00,\"gas_resistance_ohm\":29142.00,\"gas_valid\":true,\"heat_stable\":true},"
    "\"mq135\":{\"adc_raw\":0,\"calibrated\":false},\"gas_risk\":\"UNAVAILABLE\"}";

static void test_accepts_the_actual_tx_wire_shape(void) {
    rx_event_info_t event;
    assert(rx_parse_tx_event(valid, strlen(valid), &event) == 0);
    assert(strcmp(event.event_id, "tx-0123456789abcdef") == 0);
    assert(strcmp(event.tx_device_id, "safesense-tx-01") == 0);
}

static void test_accepts_prior_v1_records_without_claiming_heater_stability(void) {
    const char legacy[] =
        "{\"schema_version\":1,\"event_id\":\"tx-legacy\",\"tx_device_id\":\"safesense-tx-01\","
        "\"sequence\":0,\"observed_at\":null,"
        "\"bme680\":{\"sensor_healthy\":true,\"temperature_c\":29.70,\"humidity_pct\":71.96,"
        "\"pressure_pa\":97353.77,\"gas_resistance_ohm\":null,\"gas_valid\":false},"
        "\"mq135\":{\"adc_raw\":0,\"calibrated\":false},\"gas_risk\":\"UNAVAILABLE\"}";
    rx_event_info_t event;
    assert(rx_parse_tx_event(legacy, strlen(legacy), &event) == 0);
}

static void test_rejects_malformed_and_misleading_ids(void) {
    rx_event_info_t event;
    char trailing[sizeof(valid) + 8];
    snprintf(trailing, sizeof(trailing), "%s junk", valid);
    assert(rx_parse_tx_event(trailing, strlen(trailing), &event) != 0);
    assert(rx_parse_tx_event("{}", 2, &event) != 0);
    assert(rx_parse_tx_event(valid, 769, &event) != 0);
    const char duplicate[] =
        "{\"schema_version\":1,\"event_id\":\"tx-first\",\"event_id\":\"tx-second\"}";
    assert(rx_parse_tx_event(duplicate, strlen(duplicate), &event) != 0);
}

static void test_rejects_wrong_schema_and_fabricated_gas_risk(void) {
    rx_event_info_t event;
    char changed[sizeof(valid)];
    memcpy(changed, valid, sizeof(valid));
    char *schema = strstr(changed, "\"schema_version\":1");
    assert(schema != NULL);
    schema[strlen("\"schema_version\":")] = '2';
    assert(rx_parse_tx_event(changed, strlen(changed), &event) != 0);
    memcpy(changed, valid, sizeof(valid));
    char *risk = strstr(changed, "UNAVAILABLE");
    assert(risk != NULL);
    memcpy(risk, "NORMAL     ", 11);
    assert(rx_parse_tx_event(changed, strlen(changed), &event) != 0);
}

static void test_forward_ack_requires_one_safe_event_id(void) {
    char event_id[64];
    const char good[] = "{\"event_id\":\"tx-0123456789abcdef\"}";
    assert(rx_parse_forward_ack(good, strlen(good), event_id) == 0);
    assert(strcmp(event_id, "tx-0123456789abcdef") == 0);
    const char duplicate[] = "{\"event_id\":\"tx-first\",\"event_id\":\"tx-second\"}";
    assert(rx_parse_forward_ack(duplicate, strlen(duplicate), event_id) != 0);
    assert(rx_parse_forward_ack("{\"event_id\":7}", 14, event_id) != 0);
}

int main(void) {
    test_accepts_the_actual_tx_wire_shape();
    test_accepts_prior_v1_records_without_claiming_heater_stability();
    test_rejects_malformed_and_misleading_ids();
    test_rejects_wrong_schema_and_fabricated_gas_risk();
    test_forward_ack_requires_one_safe_event_id();
    puts("rx_protocol tests passed");
    return 0;
}
