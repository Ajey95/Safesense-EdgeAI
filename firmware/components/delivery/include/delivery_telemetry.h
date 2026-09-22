#pragma once

#include <stdbool.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    bool initialized;
    bool previous_connected;
    uint64_t last_published_ms;
} delivery_telemetry_tracker_t;

/*
 * Publish immediately on boot, safety-state changes, and connectivity changes.
 * Periodic heartbeats run only while connected so an outage cannot fill NVS.
 */
bool delivery_telemetry_due(delivery_telemetry_tracker_t *tracker,
                            bool connected,
                            bool safety_state_changed,
                            uint64_t now_ms,
                            uint32_t heartbeat_interval_ms);

#ifdef __cplusplus
}
#endif
