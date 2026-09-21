#pragma once

#include "gas_risk.h"

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define NODE_PROTOCOL_PACKET_SIZE 50u
#define NODE_PROTOCOL_VERSION 1u

#define NODE_FLAG_SENSOR_HEALTHY 0x0001u
#define NODE_FLAG_GAS_VALID 0x0002u
#define NODE_FLAG_HEAT_STABLE 0x0004u

typedef enum {
    NODE_PROTOCOL_OK = 0,
    NODE_PROTOCOL_ERR_ARGUMENT = -1,
    NODE_PROTOCOL_ERR_LENGTH = -2,
    NODE_PROTOCOL_ERR_MAGIC = -3,
    NODE_PROTOCOL_ERR_VERSION = -4,
    NODE_PROTOCOL_ERR_TYPE = -5,
    NODE_PROTOCOL_ERR_VALUE = -6,
    NODE_PROTOCOL_ERR_CRC = -7,
    NODE_PROTOCOL_ERR_SEQUENCE = -8,
    NODE_PROTOCOL_ERR_STALE = -9,
} node_protocol_status_t;

typedef struct {
    uint32_t sequence;
    uint32_t uptime_ms;
    uint32_t sample_age_ms;
    uint16_t flags;
    int32_t temperature_milli_c;
    uint32_t humidity_milli_percent;
    uint32_t pressure_pa;
    uint32_t gas_resistance_ohm;
    uint32_t gas_baseline_ohm;
    uint16_t gas_ratio_q15;
    gas_risk_t gas_risk;
} node_environment_t;

typedef struct {
    uint32_t last_sequence;
    bool initialized;
} node_sequence_tracker_t;

node_protocol_status_t node_protocol_encode(const node_environment_t *reading,
                                            uint8_t *packet,
                                            size_t length);
node_protocol_status_t node_protocol_decode(const uint8_t *packet,
                                            size_t length,
                                            uint32_t maximum_sample_age_ms,
                                            node_sequence_tracker_t *tracker,
                                            node_environment_t *reading);
uint32_t node_protocol_crc32(const uint8_t *data, size_t length);

#ifdef __cplusplus
}
#endif
