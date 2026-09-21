#include "delivery_queue.h"

#include <string.h>

static bool record_is_valid(const delivery_record_t *record)
{
    return record != NULL && record->event_id[0] != '\0' && record->payload[0] != '\0' &&
           memchr(record->event_id, '\0', sizeof(record->event_id)) != NULL &&
           memchr(record->payload, '\0', sizeof(record->payload)) != NULL;
}

static bool store_is_valid(const delivery_store_t *store)
{
    return store != NULL && store->load_meta != NULL && store->save_meta != NULL &&
           store->load_record != NULL && store->save_record != NULL &&
           store->erase_record != NULL;
}

delivery_status_t delivery_queue_init(delivery_queue_t *queue, const delivery_store_t *store)
{
    if (queue == NULL || !store_is_valid(store)) {
        return DELIVERY_ERR_ARGUMENT;
    }
    *queue = (delivery_queue_t){.store = *store};
    int stored = queue->store.load_meta(queue->store.context, &queue->head, &queue->count);
    if (stored == DELIVERY_STORE_NOT_FOUND) {
        return queue->store.save_meta(queue->store.context, 0u, 0u) == DELIVERY_STORE_OK
                   ? DELIVERY_OK
                   : DELIVERY_ERR_STORAGE;
    }
    if (stored != DELIVERY_STORE_OK || queue->head >= DELIVERY_QUEUE_CAPACITY ||
        queue->count > DELIVERY_QUEUE_CAPACITY) {
        return DELIVERY_ERR_STORAGE;
    }
    for (uint8_t offset = 0u; offset < queue->count; offset++) {
        const uint8_t slot = (uint8_t)((queue->head + offset) % DELIVERY_QUEUE_CAPACITY);
        delivery_record_t record;
        if (queue->store.load_record(queue->store.context, slot, &record) != DELIVERY_STORE_OK ||
            !record_is_valid(&record)) {
            return DELIVERY_ERR_STORAGE;
        }
    }
    return DELIVERY_OK;
}

static delivery_status_t contains_event(const delivery_queue_t *queue,
                                        const char *event_id,
                                        bool *found)
{
    *found = false;
    for (uint8_t offset = 0u; offset < queue->count; offset++) {
        const uint8_t slot = (uint8_t)((queue->head + offset) % DELIVERY_QUEUE_CAPACITY);
        delivery_record_t existing;
        if (queue->store.load_record(queue->store.context, slot, &existing) != DELIVERY_STORE_OK ||
            !record_is_valid(&existing)) {
            return DELIVERY_ERR_STORAGE;
        }
        if (strcmp(existing.event_id, event_id) == 0) {
            *found = true;
            return DELIVERY_OK;
        }
    }
    return DELIVERY_OK;
}

delivery_status_t delivery_queue_enqueue(delivery_queue_t *queue,
                                         const delivery_record_t *record)
{
    if (queue == NULL || !record_is_valid(record)) {
        return DELIVERY_ERR_ARGUMENT;
    }
    if (queue->count == DELIVERY_QUEUE_CAPACITY) {
        return DELIVERY_ERR_FULL;
    }
    bool duplicate;
    delivery_status_t status = contains_event(queue, record->event_id, &duplicate);
    if (status != DELIVERY_OK) {
        return status;
    }
    if (duplicate) {
        return DELIVERY_ERR_DUPLICATE;
    }

    const uint8_t slot = (uint8_t)((queue->head + queue->count) % DELIVERY_QUEUE_CAPACITY);
    if (queue->store.save_record(queue->store.context, slot, record) != DELIVERY_STORE_OK) {
        return DELIVERY_ERR_STORAGE;
    }
    const uint8_t new_count = (uint8_t)(queue->count + 1u);
    if (queue->store.save_meta(queue->store.context, queue->head, new_count) != DELIVERY_STORE_OK) {
        (void)queue->store.erase_record(queue->store.context, slot);
        return DELIVERY_ERR_STORAGE;
    }
    queue->count = new_count;
    return DELIVERY_OK;
}

delivery_status_t delivery_queue_peek(delivery_queue_t *queue, delivery_record_t *record)
{
    if (queue == NULL || record == NULL) {
        return DELIVERY_ERR_ARGUMENT;
    }
    if (queue->count == 0u) {
        return DELIVERY_ERR_EMPTY;
    }
    return queue->store.load_record(queue->store.context, queue->head, record) == DELIVERY_STORE_OK &&
                   record_is_valid(record)
               ? DELIVERY_OK
               : DELIVERY_ERR_STORAGE;
}

delivery_status_t delivery_queue_ack_head(delivery_queue_t *queue, const char *event_id)
{
    delivery_record_t record;
    if (queue == NULL || event_id == NULL || event_id[0] == '\0') {
        return DELIVERY_ERR_ARGUMENT;
    }
    delivery_status_t status = delivery_queue_peek(queue, &record);
    if (status != DELIVERY_OK) {
        return status;
    }
    if (strcmp(record.event_id, event_id) != 0) {
        return DELIVERY_ERR_ACK;
    }
    const uint8_t old_head = queue->head;
    const uint8_t new_head = (uint8_t)((old_head + 1u) % DELIVERY_QUEUE_CAPACITY);
    const uint8_t new_count = (uint8_t)(queue->count - 1u);
    if (queue->store.save_meta(queue->store.context, new_head, new_count) != DELIVERY_STORE_OK) {
        return DELIVERY_ERR_STORAGE;
    }
    queue->head = new_head;
    queue->count = new_count;
    (void)queue->store.erase_record(queue->store.context, old_head);
    return DELIVERY_OK;
}

uint8_t delivery_queue_count(const delivery_queue_t *queue)
{
    return queue != NULL ? queue->count : 0u;
}
