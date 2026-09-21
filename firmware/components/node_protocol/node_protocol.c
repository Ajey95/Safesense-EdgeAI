#include "node_protocol.h"

#define NODE_MAGIC 0x53414645u
#define NODE_PACKET_TYPE_ENVIRONMENT 1u
#define NODE_ALLOWED_FLAGS (NODE_FLAG_SENSOR_HEALTHY | NODE_FLAG_GAS_VALID | NODE_FLAG_HEAT_STABLE)

static void put_u16(uint8_t *data, uint16_t value)
{
    data[0] = (uint8_t)(value >> 8);
    data[1] = (uint8_t)value;
}

static void put_u32(uint8_t *data, uint32_t value)
{
    data[0] = (uint8_t)(value >> 24);
    data[1] = (uint8_t)(value >> 16);
    data[2] = (uint8_t)(value >> 8);
    data[3] = (uint8_t)value;
}

static uint16_t get_u16(const uint8_t *data)
{
    return (uint16_t)(((uint16_t)data[0] << 8) | data[1]);
}

static uint32_t get_u32(const uint8_t *data)
{
    return ((uint32_t)data[0] << 24) | ((uint32_t)data[1] << 16) |
           ((uint32_t)data[2] << 8) | data[3];
}

uint32_t node_protocol_crc32(const uint8_t *data, size_t length)
{
    if (data == NULL && length != 0u) {
        return 0u;
    }
    uint32_t crc = 0xFFFFFFFFu;
    for (size_t i = 0; i < length; i++) {
        crc ^= data[i];
        for (uint8_t bit = 0u; bit < 8u; bit++) {
            const uint32_t mask = (uint32_t)(-(int32_t)(crc & 1u));
            crc = (crc >> 1) ^ (0xEDB88320u & mask);
        }
    }
    return ~crc;
}

static bool values_are_valid(const node_environment_t *reading)
{
    return reading->humidity_milli_percent <= 100000u &&
           reading->gas_risk >= GAS_RISK_NORMAL &&
           reading->gas_risk <= GAS_RISK_UNAVAILABLE &&
           (reading->flags & (uint16_t)~NODE_ALLOWED_FLAGS) == 0u;
}

node_protocol_status_t node_protocol_encode(const node_environment_t *reading,
                                            uint8_t *packet,
                                            size_t length)
{
    if (reading == NULL || packet == NULL) {
        return NODE_PROTOCOL_ERR_ARGUMENT;
    }
    if (length != NODE_PROTOCOL_PACKET_SIZE) {
        return NODE_PROTOCOL_ERR_LENGTH;
    }
    if (!values_are_valid(reading)) {
        return NODE_PROTOCOL_ERR_VALUE;
    }

    put_u32(&packet[0], NODE_MAGIC);
    packet[4] = NODE_PROTOCOL_VERSION;
    packet[5] = NODE_PACKET_TYPE_ENVIRONMENT;
    put_u16(&packet[6], NODE_PROTOCOL_PACKET_SIZE);
    put_u32(&packet[8], reading->sequence);
    put_u32(&packet[12], reading->uptime_ms);
    put_u32(&packet[16], reading->sample_age_ms);
    put_u16(&packet[20], reading->flags);
    put_u32(&packet[22], (uint32_t)reading->temperature_milli_c);
    put_u32(&packet[26], reading->humidity_milli_percent);
    put_u32(&packet[30], reading->pressure_pa);
    put_u32(&packet[34], reading->gas_resistance_ohm);
    put_u32(&packet[38], reading->gas_baseline_ohm);
    put_u16(&packet[42], reading->gas_ratio_q15);
    packet[44] = (uint8_t)reading->gas_risk;
    packet[45] = 0u;
    put_u32(&packet[46], node_protocol_crc32(packet, 46u));
    return NODE_PROTOCOL_OK;
}

static bool sequence_is_newer(uint32_t sequence, uint32_t previous)
{
    return (int32_t)(sequence - previous) > 0;
}

node_protocol_status_t node_protocol_decode(const uint8_t *packet,
                                            size_t length,
                                            uint32_t maximum_sample_age_ms,
                                            node_sequence_tracker_t *tracker,
                                            node_environment_t *reading)
{
    if (packet == NULL || reading == NULL) {
        return NODE_PROTOCOL_ERR_ARGUMENT;
    }
    if (length != NODE_PROTOCOL_PACKET_SIZE || get_u16(&packet[6]) != NODE_PROTOCOL_PACKET_SIZE) {
        return NODE_PROTOCOL_ERR_LENGTH;
    }
    if (get_u32(&packet[0]) != NODE_MAGIC) {
        return NODE_PROTOCOL_ERR_MAGIC;
    }
    if (packet[4] != NODE_PROTOCOL_VERSION) {
        return NODE_PROTOCOL_ERR_VERSION;
    }
    if (packet[5] != NODE_PACKET_TYPE_ENVIRONMENT) {
        return NODE_PROTOCOL_ERR_TYPE;
    }
    if (get_u32(&packet[46]) != node_protocol_crc32(packet, 46u)) {
        return NODE_PROTOCOL_ERR_CRC;
    }

    node_environment_t decoded = {
        .sequence = get_u32(&packet[8]),
        .uptime_ms = get_u32(&packet[12]),
        .sample_age_ms = get_u32(&packet[16]),
        .flags = get_u16(&packet[20]),
        .temperature_milli_c = (int32_t)get_u32(&packet[22]),
        .humidity_milli_percent = get_u32(&packet[26]),
        .pressure_pa = get_u32(&packet[30]),
        .gas_resistance_ohm = get_u32(&packet[34]),
        .gas_baseline_ohm = get_u32(&packet[38]),
        .gas_ratio_q15 = get_u16(&packet[42]),
        .gas_risk = (gas_risk_t)packet[44],
    };
    if (packet[45] != 0u || !values_are_valid(&decoded)) {
        return NODE_PROTOCOL_ERR_VALUE;
    }
    if (decoded.sample_age_ms > maximum_sample_age_ms) {
        return NODE_PROTOCOL_ERR_STALE;
    }
    if (tracker != NULL && tracker->initialized &&
        !sequence_is_newer(decoded.sequence, tracker->last_sequence)) {
        return NODE_PROTOCOL_ERR_SEQUENCE;
    }

    *reading = decoded;
    if (tracker != NULL) {
        tracker->last_sequence = decoded.sequence;
        tracker->initialized = true;
    }
    return NODE_PROTOCOL_OK;
}
