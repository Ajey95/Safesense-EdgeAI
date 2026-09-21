#pragma once

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define DELIVERY_QUEUE_CAPACITY 16u
#define DELIVERY_EVENT_ID_MAX 64u
#define DELIVERY_PAYLOAD_MAX 1536u

typedef enum {
    DELIVERY_OK = 0,
    DELIVERY_ERR_ARGUMENT = -1,
    DELIVERY_ERR_FULL = -2,
    DELIVERY_ERR_EMPTY = -3,
    DELIVERY_ERR_STORAGE = -4,
    DELIVERY_ERR_DUPLICATE = -5,
    DELIVERY_ERR_ACK = -6,
} delivery_status_t;

typedef enum {
    DELIVERY_STORE_OK = 0,
    DELIVERY_STORE_NOT_FOUND = 1,
    DELIVERY_STORE_ERROR = -1,
} delivery_store_status_t;

typedef struct {
    char event_id[DELIVERY_EVENT_ID_MAX];
    char payload[DELIVERY_PAYLOAD_MAX];
} delivery_record_t;

typedef struct {
    void *context;
    int (*load_meta)(void *context, uint8_t *head, uint8_t *count);
    int (*save_meta)(void *context, uint8_t head, uint8_t count);
    int (*load_record)(void *context, uint8_t slot, delivery_record_t *record);
    int (*save_record)(void *context, uint8_t slot, const delivery_record_t *record);
    int (*erase_record)(void *context, uint8_t slot);
} delivery_store_t;

typedef struct {
    delivery_store_t store;
    uint8_t head;
    uint8_t count;
} delivery_queue_t;

delivery_status_t delivery_queue_init(delivery_queue_t *queue, const delivery_store_t *store);
delivery_status_t delivery_queue_enqueue(delivery_queue_t *queue, const delivery_record_t *record);
delivery_status_t delivery_queue_peek(delivery_queue_t *queue, delivery_record_t *record);
delivery_status_t delivery_queue_ack_head(delivery_queue_t *queue, const char *event_id);
uint8_t delivery_queue_count(const delivery_queue_t *queue);
