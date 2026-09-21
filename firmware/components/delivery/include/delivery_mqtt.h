#pragma once
#include <stdbool.h>
#include "delivery_queue.h"
typedef struct {
    const char *broker_uri;
    const char *device_id;
    const char *event_topic;
    const char *ack_topic;
    const char *server_certificate;
    delivery_queue_t *queue;
} delivery_mqtt_config_t;
int delivery_mqtt_start(const delivery_mqtt_config_t *config);
void delivery_mqtt_flush(void);
bool delivery_mqtt_is_connected(void);
