#include "delivery_mqtt_state.h"

#include <stddef.h>

void delivery_mqtt_state_init(delivery_mqtt_state_t *state)
{
    if (state == NULL) {
        return;
    }
    state->connected = false;
    state->ack_subscription_ready = false;
    state->awaiting_application_ack = false;
    state->ack_subscription_id = -1;
    state->published_at_ms = 0u;
}

void delivery_mqtt_state_connected(delivery_mqtt_state_t *state, int subscription_id)
{
    if (state == NULL) {
        return;
    }
    state->connected = true;
    state->ack_subscription_ready = false;
    state->awaiting_application_ack = false;
    state->ack_subscription_id = subscription_id;
    state->published_at_ms = 0u;
}

void delivery_mqtt_state_published(delivery_mqtt_state_t *state, uint64_t now_ms)
{
    if (state != NULL && state->connected && state->ack_subscription_ready) {
        state->awaiting_application_ack = true;
        state->published_at_ms = now_ms;
    }
}

void delivery_mqtt_state_acknowledged(delivery_mqtt_state_t *state)
{
    if (state != NULL) {
        state->awaiting_application_ack = false;
        state->published_at_ms = 0u;
    }
}

void delivery_mqtt_state_subscribed(delivery_mqtt_state_t *state, int subscription_id)
{
    if (state == NULL || !state->connected || state->ack_subscription_id < 0) {
        return;
    }
    if (subscription_id == state->ack_subscription_id) {
        state->ack_subscription_ready = true;
    }
}

void delivery_mqtt_state_disconnected(delivery_mqtt_state_t *state)
{
    delivery_mqtt_state_init(state);
}

bool delivery_mqtt_state_can_publish(const delivery_mqtt_state_t *state)
{
    return state != NULL && state->connected && state->ack_subscription_ready &&
        !state->awaiting_application_ack;
}

bool delivery_mqtt_state_retry_due(const delivery_mqtt_state_t *state,
                                   uint64_t now_ms,
                                   uint32_t acknowledgement_timeout_ms)
{
    return state != NULL && state->connected && state->ack_subscription_ready &&
        state->awaiting_application_ack && acknowledgement_timeout_ms > 0u &&
        now_ms - state->published_at_ms >= acknowledgement_timeout_ms;
}
