#include <assert.h>
#include <stdio.h>

#include "delivery_telemetry.h"

static void test_connectivity_changes_publish_immediately(void)
{
    delivery_telemetry_tracker_t tracker = {0};
    assert(delivery_telemetry_due(&tracker, false, false, 0u, 5000u));
    assert(!delivery_telemetry_due(&tracker, false, false, 100u, 5000u));
    assert(delivery_telemetry_due(&tracker, true, false, 100u, 5000u));
    assert(!delivery_telemetry_due(&tracker, true, false, 5099u, 5000u));
    assert(delivery_telemetry_due(&tracker, true, false, 5100u, 5000u));
    assert(delivery_telemetry_due(&tracker, false, false, 5200u, 5000u));
}

static void test_heartbeats_require_connection_but_state_changes_do_not(void)
{
    delivery_telemetry_tracker_t tracker = {0};
    assert(delivery_telemetry_due(&tracker, false, false, 0u, 5000u));
    assert(!delivery_telemetry_due(&tracker, false, false, 6000u, 5000u));
    assert(delivery_telemetry_due(&tracker, false, true, 6100u, 5000u));
}

int main(void)
{
    test_connectivity_changes_publish_immediately();
    test_heartbeats_require_connection_but_state_changes_do_not();
    puts("delivery_telemetry tests passed");
    return 0;
}
