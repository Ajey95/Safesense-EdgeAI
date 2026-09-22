#pragma once

#include <stdbool.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    bool connected;
    bool ack_subscription_ready;
    bool awaiting_application_ack;
    int ack_subscription_id;
    uint64_t published_at_ms;
} delivery_mqtt_state_t;

void delivery_mqtt_state_init(delivery_mqtt_state_t *state);
void delivery_mqtt_state_connected(delivery_mqtt_state_t *state, int subscription_id);
void delivery_mqtt_state_subscribed(delivery_mqtt_state_t *state, int subscription_id);
void delivery_mqtt_state_published(delivery_mqtt_state_t *state, uint64_t now_ms);
void delivery_mqtt_state_acknowledged(delivery_mqtt_state_t *state);
void delivery_mqtt_state_disconnected(delivery_mqtt_state_t *state);
bool delivery_mqtt_state_can_publish(const delivery_mqtt_state_t *state);
bool delivery_mqtt_state_retry_due(const delivery_mqtt_state_t *state,
                                   uint64_t now_ms,
                                   uint32_t acknowledgement_timeout_ms);

#ifdef __cplusplus
}
#endif
