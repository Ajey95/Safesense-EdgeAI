#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "node_protocol.h"

static node_environment_t fixture(void)
{
    return (node_environment_t){
        .sequence = 0x01020304u,
        .uptime_ms = 1000u,
        .sample_age_ms = 50u,
        .flags = NODE_FLAG_SENSOR_HEALTHY | NODE_FLAG_GAS_VALID | NODE_FLAG_HEAT_STABLE,
        .temperature_milli_c = 31800,
        .humidity_milli_percent = 64000u,
        .pressure_pa = 100123u,
        .gas_resistance_ohm = 100000u,
        .gas_baseline_ohm = 120000u,
        .gas_ratio_q15 = 19114u,
        .gas_risk = GAS_RISK_WARNING,
    };
}

static void test_exact_network_layout_and_crc(void)
{
    const node_environment_t input = fixture();
    uint8_t packet[NODE_PROTOCOL_PACKET_SIZE];
    assert(node_protocol_encode(&input, packet, sizeof(packet)) == NODE_PROTOCOL_OK);
    const uint8_t expected_prefix[] = {
        0x53, 0x41, 0x46, 0x45, 0x01, 0x01, 0x00, 0x32,
        0x01, 0x02, 0x03, 0x04, 0x00, 0x00, 0x03, 0xE8,
        0x00, 0x00, 0x00, 0x32, 0x00, 0x07, 0x00, 0x00,
        0x7C, 0x38, 0x00, 0x00, 0xFA, 0x00, 0x00, 0x01,
        0x87, 0x1B, 0x00, 0x01, 0x86, 0xA0, 0x00, 0x01,
        0xD4, 0xC0, 0x4A, 0xAA, 0x01, 0x00,
    };
    assert(memcmp(packet, expected_prefix, sizeof(expected_prefix)) == 0);
    assert(packet[46] == 0x90 && packet[47] == 0xD1 &&
           packet[48] == 0xE7 && packet[49] == 0x41);
}

static void test_decode_and_sequence_tracking(void)
{
    const node_environment_t input = fixture();
    uint8_t packet[NODE_PROTOCOL_PACKET_SIZE];
    assert(node_protocol_encode(&input, packet, sizeof(packet)) == NODE_PROTOCOL_OK);
    node_sequence_tracker_t tracker = {0};
    node_environment_t output;
    assert(node_protocol_decode(packet, sizeof(packet), 200u, &tracker, &output) == NODE_PROTOCOL_OK);
    assert(output.sequence == input.sequence);
    assert(output.temperature_milli_c == input.temperature_milli_c);
    assert(output.gas_risk == GAS_RISK_WARNING);
    assert(node_protocol_decode(packet, sizeof(packet), 200u, &tracker, &output) == NODE_PROTOCOL_ERR_SEQUENCE);
    node_environment_t older = input;
    older.sequence--;
    assert(node_protocol_encode(&older, packet, sizeof(packet)) == NODE_PROTOCOL_OK);
    assert(node_protocol_decode(packet, sizeof(packet), 200u, &tracker, &output) == NODE_PROTOCOL_ERR_SEQUENCE);
}

static void test_rejects_corruption_and_invalid_contract(void)
{
    node_environment_t input = fixture();
    uint8_t packet[NODE_PROTOCOL_PACKET_SIZE];
    node_environment_t output;
    assert(node_protocol_encode(&input, packet, sizeof(packet)) == NODE_PROTOCOL_OK);
    packet[30] ^= 0x01u;
    assert(node_protocol_decode(packet, sizeof(packet), 200u, NULL, &output) == NODE_PROTOCOL_ERR_CRC);
    assert(node_protocol_encode(&input, packet, sizeof(packet)) == NODE_PROTOCOL_OK);
    packet[0] = 0u;
    assert(node_protocol_decode(packet, sizeof(packet), 200u, NULL, &output) == NODE_PROTOCOL_ERR_MAGIC);
    assert(node_protocol_encode(&input, packet, sizeof(packet)) == NODE_PROTOCOL_OK);
    packet[4] = 2u;
    assert(node_protocol_decode(packet, sizeof(packet), 200u, NULL, &output) == NODE_PROTOCOL_ERR_VERSION);
    assert(node_protocol_decode(packet, sizeof(packet) - 1u, 200u, NULL, &output) == NODE_PROTOCOL_ERR_LENGTH);
    input.gas_risk = (gas_risk_t)4;
    assert(node_protocol_encode(&input, packet, sizeof(packet)) == NODE_PROTOCOL_ERR_VALUE);
}

static void test_rejects_stale_and_accepts_boundary_values(void)
{
    node_environment_t input = fixture();
    uint8_t packet[NODE_PROTOCOL_PACKET_SIZE];
    node_environment_t output;
    input.sample_age_ms = 201u;
    assert(node_protocol_encode(&input, packet, sizeof(packet)) == NODE_PROTOCOL_OK);
    assert(node_protocol_decode(packet, sizeof(packet), 200u, NULL, &output) == NODE_PROTOCOL_ERR_STALE);
    input.sample_age_ms = 200u;
    input.temperature_milli_c = -40000;
    input.humidity_milli_percent = 100000u;
    input.gas_risk = GAS_RISK_UNAVAILABLE;
    assert(node_protocol_encode(&input, packet, sizeof(packet)) == NODE_PROTOCOL_OK);
    assert(node_protocol_decode(packet, sizeof(packet), 200u, NULL, &output) == NODE_PROTOCOL_OK);
    assert(output.temperature_milli_c == -40000);
    assert(output.humidity_milli_percent == 100000u);
    input.humidity_milli_percent++;
    assert(node_protocol_encode(&input, packet, sizeof(packet)) == NODE_PROTOCOL_ERR_VALUE);
}

int main(void)
{
    test_exact_network_layout_and_crc();
    test_decode_and_sequence_tracking();
    test_rejects_corruption_and_invalid_contract();
    test_rejects_stale_and_accepts_boundary_values();
    puts("node_protocol tests passed");
    return 0;
}
