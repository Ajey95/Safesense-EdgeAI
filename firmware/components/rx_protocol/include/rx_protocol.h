#pragma once

#include <stddef.h>

#define RX_MAX_JSON_BYTES 768u

typedef struct {
    char event_id[64];
    char tx_device_id[80];
} rx_event_info_t;

/* Validates the exact V1 sensor contract before RX durably ACKs TX. */
int rx_parse_tx_event(const char *json, size_t length, rx_event_info_t *out);

/* Accept only an unambiguous durable-forward ACK for the current queue head. */
int rx_parse_forward_ack(const char *json, size_t length, char event_id[64]);
