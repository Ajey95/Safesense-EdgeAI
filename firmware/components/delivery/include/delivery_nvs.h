#pragma once

#include "delivery_queue.h"
#include "nvs.h"

typedef struct {
    nvs_handle_t handle;
    bool opened;
} delivery_nvs_t;

delivery_status_t delivery_nvs_open(delivery_nvs_t *adapter, delivery_store_t *store);
void delivery_nvs_close(delivery_nvs_t *adapter);
