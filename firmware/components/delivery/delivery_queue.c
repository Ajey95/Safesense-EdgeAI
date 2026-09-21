#include "delivery_queue.h"
#include <stdio.h>
#include <string.h>
#include "nvs_flash.h"

static void slot_key(uint8_t slot, char key[8]) { snprintf(key, 8, "e%02u", slot); }
static int save_meta(delivery_queue_t *queue) { return nvs_set_u8(queue->handle, "head", queue->head) == ESP_OK && nvs_set_u8(queue->handle, "count", queue->count) == ESP_OK && nvs_commit(queue->handle) == ESP_OK ? 0 : -1; }
int delivery_queue_init(delivery_queue_t *queue) {
    if (!queue) return -1; memset(queue, 0, sizeof(*queue));
    esp_err_t result = nvs_flash_init(); if (result == ESP_ERR_NVS_NO_FREE_PAGES || result == ESP_ERR_NVS_NEW_VERSION_FOUND) { nvs_flash_erase(); result = nvs_flash_init(); }
    if (result != ESP_OK && result != ESP_ERR_INVALID_STATE) return -1;
    if (nvs_open("ssdeliver", NVS_READWRITE, &queue->handle) != ESP_OK) return -1;
    (void)nvs_get_u8(queue->handle, "head", &queue->head); (void)nvs_get_u8(queue->handle, "count", &queue->count);
    if (queue->head >= DELIVERY_QUEUE_CAPACITY || queue->count > DELIVERY_QUEUE_CAPACITY) { queue->head = queue->count = 0; return save_meta(queue); }
    return 0;
}
int delivery_queue_enqueue(delivery_queue_t *queue, const delivery_record_t *record) {
    if (!queue || !record || !record->event_id[0] || !record->payload[0] || queue->count == DELIVERY_QUEUE_CAPACITY) return -1;
    char key[8]; slot_key((queue->head + queue->count) % DELIVERY_QUEUE_CAPACITY, key);
    /* Persist payload before publishing or advancing queue metadata. */
    if (nvs_set_blob(queue->handle, key, record, sizeof(*record)) != ESP_OK || nvs_commit(queue->handle) != ESP_OK) return -1;
    queue->count++; return save_meta(queue);
}
int delivery_queue_peek(delivery_queue_t *queue, delivery_record_t *record) {
    if (!queue || !record || queue->count == 0) return -1; char key[8]; size_t length = sizeof(*record); slot_key(queue->head, key);
    return nvs_get_blob(queue->handle, key, record, &length) == ESP_OK && length == sizeof(*record) ? 0 : -1;
}
int delivery_queue_ack_head(delivery_queue_t *queue, const char *event_id) {
    delivery_record_t record; if (!queue || !event_id || delivery_queue_peek(queue, &record) != 0 || strcmp(record.event_id, event_id) != 0) return -1;
    char key[8]; slot_key(queue->head, key);
    const uint8_t previous_head = queue->head, previous_count = queue->count;
    queue->head = (queue->head + 1) % DELIVERY_QUEUE_CAPACITY; queue->count--;
    /* Commit metadata first. A power loss may leave an unreachable old blob,
     * but can no longer leave the queue pointing at a blob already erased. */
    if (save_meta(queue) != 0) { queue->head = previous_head; queue->count = previous_count; return -1; }
    (void)nvs_erase_key(queue->handle, key);
    (void)nvs_commit(queue->handle);
    return 0;
}
uint8_t delivery_queue_count(const delivery_queue_t *queue) { return queue ? queue->count : 0; }
