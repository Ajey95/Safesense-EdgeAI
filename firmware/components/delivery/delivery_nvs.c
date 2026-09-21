#include "delivery_nvs.h"

#include "nvs_flash.h"

#include <stdio.h>

static void slot_key(uint8_t slot, char key[8])
{
    snprintf(key, 8u, "e%02u", slot);
}

static int load_meta(void *context, uint8_t *head, uint8_t *count)
{
    delivery_nvs_t *adapter = context;
    esp_err_t head_result = nvs_get_u8(adapter->handle, "head", head);
    esp_err_t count_result = nvs_get_u8(adapter->handle, "count", count);
    if (head_result == ESP_ERR_NVS_NOT_FOUND && count_result == ESP_ERR_NVS_NOT_FOUND) {
        return DELIVERY_STORE_NOT_FOUND;
    }
    return head_result == ESP_OK && count_result == ESP_OK
               ? DELIVERY_STORE_OK
               : DELIVERY_STORE_ERROR;
}

static int save_meta(void *context, uint8_t head, uint8_t count)
{
    delivery_nvs_t *adapter = context;
    return nvs_set_u8(adapter->handle, "head", head) == ESP_OK &&
                   nvs_set_u8(adapter->handle, "count", count) == ESP_OK &&
                   nvs_commit(adapter->handle) == ESP_OK
               ? DELIVERY_STORE_OK
               : DELIVERY_STORE_ERROR;
}

static int load_record(void *context, uint8_t slot, delivery_record_t *record)
{
    delivery_nvs_t *adapter = context;
    char key[8];
    slot_key(slot, key);
    size_t length = sizeof(*record);
    esp_err_t result = nvs_get_blob(adapter->handle, key, record, &length);
    if (result == ESP_ERR_NVS_NOT_FOUND) {
        return DELIVERY_STORE_NOT_FOUND;
    }
    return result == ESP_OK && length == sizeof(*record)
               ? DELIVERY_STORE_OK
               : DELIVERY_STORE_ERROR;
}

static int save_record(void *context, uint8_t slot, const delivery_record_t *record)
{
    delivery_nvs_t *adapter = context;
    char key[8];
    slot_key(slot, key);
    return nvs_set_blob(adapter->handle, key, record, sizeof(*record)) == ESP_OK &&
                   nvs_commit(adapter->handle) == ESP_OK
               ? DELIVERY_STORE_OK
               : DELIVERY_STORE_ERROR;
}

static int erase_record(void *context, uint8_t slot)
{
    delivery_nvs_t *adapter = context;
    char key[8];
    slot_key(slot, key);
    esp_err_t result = nvs_erase_key(adapter->handle, key);
    if (result != ESP_OK && result != ESP_ERR_NVS_NOT_FOUND) {
        return DELIVERY_STORE_ERROR;
    }
    return nvs_commit(adapter->handle) == ESP_OK ? DELIVERY_STORE_OK : DELIVERY_STORE_ERROR;
}

delivery_status_t delivery_nvs_open(delivery_nvs_t *adapter, delivery_store_t *store)
{
    if (adapter == NULL || store == NULL) {
        return DELIVERY_ERR_ARGUMENT;
    }
    *adapter = (delivery_nvs_t){0};
    esp_err_t result = nvs_flash_init();
    if (result != ESP_OK && result != ESP_ERR_INVALID_STATE) {
        return DELIVERY_ERR_STORAGE;
    }
    if (nvs_open("ssdeliver", NVS_READWRITE, &adapter->handle) != ESP_OK) {
        return DELIVERY_ERR_STORAGE;
    }
    adapter->opened = true;
    *store = (delivery_store_t){
        .context = adapter,
        .load_meta = load_meta,
        .save_meta = save_meta,
        .load_record = load_record,
        .save_record = save_record,
        .erase_record = erase_record,
    };
    return DELIVERY_OK;
}

void delivery_nvs_close(delivery_nvs_t *adapter)
{
    if (adapter != NULL && adapter->opened) {
        nvs_close(adapter->handle);
        adapter->opened = false;
    }
}
