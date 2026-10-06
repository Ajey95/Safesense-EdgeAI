#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "delivery_queue.h"

static char opened_namespace[32];
static esp_err_t flash_result = ESP_OK;
static bool erase_called;
static int commit_calls, fail_on_commit;
static delivery_record_t slots[DELIVERY_QUEUE_CAPACITY];
static bool occupied[DELIVERY_QUEUE_CAPACITY];
static int slot_number(const char *key) { int slot = -1; return sscanf(key, "e%d", &slot) == 1 ? slot : -1; }
esp_err_t nvs_flash_init(void) { return flash_result; }
esp_err_t nvs_flash_erase(void) { erase_called = true; return ESP_OK; }
esp_err_t nvs_open(const char *name, int mode, nvs_handle_t *handle) {
    (void)mode; *handle = 1;
    snprintf(opened_namespace, sizeof(opened_namespace), "%s", name);
    return ESP_OK;
}
esp_err_t nvs_get_u8(nvs_handle_t h, const char *k, uint8_t *v) { (void)h; (void)k; (void)v; return -1; }
esp_err_t nvs_set_u8(nvs_handle_t h, const char *k, uint8_t v) { (void)h; (void)k; (void)v; return ESP_OK; }
esp_err_t nvs_set_blob(nvs_handle_t h, const char *k, const void *v, size_t n) {
    (void)h; int slot = slot_number(k);
    if (slot < 0 || slot >= (int)DELIVERY_QUEUE_CAPACITY || n != sizeof(delivery_record_t)) return -1;
    memcpy(&slots[slot], v, n); occupied[slot] = true; return ESP_OK;
}
esp_err_t nvs_get_blob(nvs_handle_t h, const char *k, void *v, size_t *n) {
    (void)h; int slot = slot_number(k);
    if (slot < 0 || slot >= (int)DELIVERY_QUEUE_CAPACITY || !occupied[slot]) return ESP_ERR_NVS_NOT_FOUND;
    if (*n < sizeof(delivery_record_t)) return -1;
    memcpy(v, &slots[slot], sizeof(delivery_record_t)); *n = sizeof(delivery_record_t); return ESP_OK;
}
esp_err_t nvs_erase_key(nvs_handle_t h, const char *k) {
    (void)h; int slot = slot_number(k);
    if (slot < 0 || slot >= (int)DELIVERY_QUEUE_CAPACITY) return -1;
    occupied[slot] = false; return ESP_OK;
}
esp_err_t nvs_commit(nvs_handle_t h) {
    (void)h;
    commit_calls++;
    return commit_calls == fail_on_commit ? -1 : ESP_OK;
}

int main(void) {
    delivery_queue_t queue;
    assert(delivery_queue_init_named(&queue, "sstx") == 0);
    assert(strcmp(opened_namespace, "sstx") == 0);
    const delivery_record_t record = {.event_id="tx-0123456789abcdef", .payload="{\"event_id\":\"tx-0123456789abcdef\"}"};
    assert(delivery_queue_enqueue(&queue, &record) == 0);
    assert(delivery_queue_contains(&queue, record.event_id) == 1);
    assert(delivery_queue_contains(&queue, "tx-other") == 0);
    assert(delivery_queue_count(&queue) == 1);
    slots[1] = record; occupied[1] = true;
    occupied[0] = false;
    queue.head = 0; queue.count = 2;
    assert(delivery_queue_repair_missing_head(&queue) == 1);
    assert(queue.head == 1 && queue.count == 1);
    assert(delivery_queue_peek(&queue, &(delivery_record_t){0}) == 0);
    const delivery_record_t another = {.event_id="tx-second", .payload="{\"event_id\":\"tx-second\"}"};
    fail_on_commit = commit_calls + 2; /* Blob commit succeeds; queue metadata does not. */
    assert(delivery_queue_enqueue(&queue, &another) != 0);
    assert(delivery_queue_count(&queue) == 1);
    fail_on_commit = 0;
    assert(delivery_queue_ack_head(&queue, "tx-other") != 0);
    assert(delivery_queue_count(&queue) == 1);
    assert(delivery_queue_init_named(&queue, "") == -1);
    flash_result = ESP_ERR_NVS_NO_FREE_PAGES;
    erase_called = false;
    assert(delivery_queue_init_named(&queue, "sstx") == -1);
    assert(!erase_called);
    puts("tx_queue_namespace tests passed");
}
