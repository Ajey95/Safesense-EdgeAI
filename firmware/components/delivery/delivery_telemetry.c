#include "delivery_telemetry.h"

#include <stddef.h>

bool delivery_telemetry_due(delivery_telemetry_tracker_t *tracker,
                            bool connected,
                            bool safety_state_changed,
                            uint64_t now_ms,
                            uint32_t heartbeat_interval_ms)
{
    if (tracker == NULL || heartbeat_interval_ms == 0u) {
        return false;
    }
    const bool first_snapshot = !tracker->initialized;
    const bool connectivity_changed = tracker->initialized &&
        tracker->previous_connected != connected;
    const bool heartbeat_due = tracker->initialized && connected &&
        now_ms - tracker->last_published_ms >= heartbeat_interval_ms;
    const bool publish = first_snapshot || safety_state_changed ||
        connectivity_changed || heartbeat_due;

    tracker->initialized = true;
    tracker->previous_connected = connected;
    if (publish) {
        tracker->last_published_ms = now_ms;
    }
    return publish;
}
