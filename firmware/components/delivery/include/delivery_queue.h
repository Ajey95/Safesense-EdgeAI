#pragma once
#include <stdbool.h>
#include <stdint.h>
#include "nvs.h"

#define DELIVERY_QUEUE_CAPACITY 16u
#define DELIVERY_EVENT_ID_MAX 64u
#define DELIVERY_PAYLOAD_MAX 768u
typedef struct { char event_id[DELIVERY_EVENT_ID_MAX]; char payload[DELIVERY_PAYLOAD_MAX]; } delivery_record_t;
typedef struct { nvs_handle_t handle; uint8_t head, count; } delivery_queue_t;
int delivery_queue_init(delivery_queue_t *queue);
int delivery_queue_enqueue(delivery_queue_t *queue, const delivery_record_t *record);
int delivery_queue_peek(delivery_queue_t *queue, delivery_record_t *record);
int delivery_queue_ack_head(delivery_queue_t *queue, const char *event_id);
uint8_t delivery_queue_count(const delivery_queue_t *queue);
