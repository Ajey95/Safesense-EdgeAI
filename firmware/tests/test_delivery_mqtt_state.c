#include <assert.h>
#include <stdio.h>

#include "delivery_mqtt_state.h"

static void test_publish_waits_for_matching_ack_subscription(void)
{
    delivery_mqtt_state_t state;
    delivery_mqtt_state_init(&state);
    assert(!delivery_mqtt_state_can_publish(&state));

    delivery_mqtt_state_connected(&state, 41);
    assert(!delivery_mqtt_state_can_publish(&state));

    delivery_mqtt_state_subscribed(&state, 40);
    assert(!delivery_mqtt_state_can_publish(&state));

    delivery_mqtt_state_subscribed(&state, 41);
    assert(delivery_mqtt_state_can_publish(&state));

    delivery_mqtt_state_published(&state, 1000u);
    assert(!delivery_mqtt_state_can_publish(&state));
    assert(!delivery_mqtt_state_retry_due(&state, 5999u, 5000u));
    assert(delivery_mqtt_state_retry_due(&state, 6000u, 5000u));

    delivery_mqtt_state_acknowledged(&state);
    assert(delivery_mqtt_state_can_publish(&state));
    assert(state.published_at_ms == 0u);

    delivery_mqtt_state_published(&state, 7000u);
    delivery_mqtt_state_connected(&state, 42);
    assert(state.published_at_ms == 0u);
}

static void test_disconnect_and_failed_subscription_block_publish(void)
{
    delivery_mqtt_state_t state;
    delivery_mqtt_state_init(&state);
    delivery_mqtt_state_connected(&state, 7);
    delivery_mqtt_state_subscribed(&state, 7);
    assert(delivery_mqtt_state_can_publish(&state));

    delivery_mqtt_state_disconnected(&state);
    assert(!delivery_mqtt_state_can_publish(&state));

    delivery_mqtt_state_connected(&state, -1);
    delivery_mqtt_state_subscribed(&state, -1);
    assert(!delivery_mqtt_state_can_publish(&state));
}

int main(void)
{
    test_publish_waits_for_matching_ack_subscription();
    test_disconnect_and_failed_subscription_block_publish();
    puts("delivery_mqtt_state tests passed");
    return 0;
}
