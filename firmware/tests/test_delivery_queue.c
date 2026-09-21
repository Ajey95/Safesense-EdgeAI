#include <assert.h>
#include <stdio.h>
#include <string.h>

#include "delivery_ack.h"
#include "delivery_queue.h"

typedef struct {
    delivery_record_t slots[DELIVERY_QUEUE_CAPACITY];
    bool present[DELIVERY_QUEUE_CAPACITY];
    bool has_meta;
    uint8_t head;
    uint8_t count;
} fake_store_t;

static int load_meta(void *context, uint8_t *head, uint8_t *count)
{
    fake_store_t *store = context;
    if (!store->has_meta) {
        return DELIVERY_STORE_NOT_FOUND;
    }
    *head = store->head;
    *count = store->count;
    return DELIVERY_STORE_OK;
}

static int save_meta(void *context, uint8_t head, uint8_t count)
{
    fake_store_t *store = context;
    store->has_meta = true;
    store->head = head;
    store->count = count;
    return DELIVERY_STORE_OK;
}

static int load_record(void *context, uint8_t slot, delivery_record_t *record)
{
    fake_store_t *store = context;
    if (!store->present[slot]) {
        return DELIVERY_STORE_NOT_FOUND;
    }
    *record = store->slots[slot];
    return DELIVERY_STORE_OK;
}

static int save_record(void *context, uint8_t slot, const delivery_record_t *record)
{
    fake_store_t *store = context;
    store->slots[slot] = *record;
    store->present[slot] = true;
    return DELIVERY_STORE_OK;
}

static int erase_record(void *context, uint8_t slot)
{
    fake_store_t *store = context;
    store->present[slot] = false;
    memset(&store->slots[slot], 0, sizeof(store->slots[slot]));
    return DELIVERY_STORE_OK;
}

static delivery_store_t fake_store_api(fake_store_t *store)
{
    return (delivery_store_t){
        .context = store,
        .load_meta = load_meta,
        .save_meta = save_meta,
        .load_record = load_record,
        .save_record = save_record,
        .erase_record = erase_record,
    };
}

static delivery_record_t record(const char *event_id)
{
    delivery_record_t value = {0};
    snprintf(value.event_id, sizeof(value.event_id), "%s", event_id);
    snprintf(value.payload, sizeof(value.payload), "{\"event_id\":\"%s\"}", event_id);
    return value;
}

static void test_restore_duplicate_and_exact_ack(void)
{
    fake_store_t persisted = {0};
    delivery_store_t store = fake_store_api(&persisted);
    delivery_queue_t first;
    assert(delivery_queue_init(&first, &store) == DELIVERY_OK);
    delivery_record_t event = record("evt-001");
    assert(delivery_queue_enqueue(&first, &event) == DELIVERY_OK);
    assert(delivery_queue_enqueue(&first, &event) == DELIVERY_ERR_DUPLICATE);

    delivery_queue_t restored;
    assert(delivery_queue_init(&restored, &store) == DELIVERY_OK);
    assert(delivery_queue_count(&restored) == 1u);
    delivery_record_t head;
    assert(delivery_queue_peek(&restored, &head) == DELIVERY_OK);
    assert(strcmp(head.event_id, "evt-001") == 0);

    assert(delivery_queue_ack_head(&restored, "evt-wrong") == DELIVERY_ERR_ACK);
    assert(delivery_queue_count(&restored) == 1u);
    assert(!delivery_ack_matches("{bad", 4u, "evt-001"));
    assert(!delivery_ack_matches("{\"event_id\":\"evt-002\",\"status\":\"ACCEPTED\"}",
                                 46u, "evt-001"));
    const char *ack = "{\"status\":\"ACCEPTED\",\"event_id\":\"evt-001\"}";
    assert(delivery_ack_matches(ack, strlen(ack), "evt-001"));
    assert(delivery_queue_ack_head(&restored, "evt-001") == DELIVERY_OK);
    assert(delivery_queue_count(&restored) == 0u);
}

static void test_full_queue_fails_without_overwrite(void)
{
    fake_store_t persisted = {0};
    delivery_store_t store = fake_store_api(&persisted);
    delivery_queue_t queue;
    assert(delivery_queue_init(&queue, &store) == DELIVERY_OK);
    char event_id[DELIVERY_EVENT_ID_MAX];
    for (unsigned int i = 0; i < DELIVERY_QUEUE_CAPACITY; i++) {
        snprintf(event_id, sizeof(event_id), "evt-%02u", i);
        delivery_record_t event = record(event_id);
        assert(delivery_queue_enqueue(&queue, &event) == DELIVERY_OK);
    }
    delivery_record_t overflow = record("evt-overflow");
    assert(delivery_queue_enqueue(&queue, &overflow) == DELIVERY_ERR_FULL);
    assert(delivery_queue_count(&queue) == DELIVERY_QUEUE_CAPACITY);
    delivery_record_t head;
    assert(delivery_queue_peek(&queue, &head) == DELIVERY_OK);
    assert(strcmp(head.event_id, "evt-00") == 0);
}

static void test_invalid_metadata_is_rejected(void)
{
    fake_store_t persisted = {.has_meta = true, .head = DELIVERY_QUEUE_CAPACITY, .count = 1u};
    delivery_store_t store = fake_store_api(&persisted);
    delivery_queue_t queue;
    assert(delivery_queue_init(&queue, &store) == DELIVERY_ERR_STORAGE);
}

int main(void)
{
    test_restore_duplicate_and_exact_ack();
    test_full_queue_fails_without_overwrite();
    test_invalid_metadata_is_rejected();
    puts("delivery_queue tests passed");
    return 0;
}
