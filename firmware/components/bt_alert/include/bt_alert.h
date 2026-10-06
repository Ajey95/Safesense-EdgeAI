#pragma once

#include <stdbool.h>
#include <stdint.h>

/* Classic ESP32 Bluetooth SPP server for a paired nearby laptop COM port.
 * A receipt means that laptop software stored this event, not that speech
 * played or that a remote emergency service received it. */
bool bt_alert_start(void);
bool bt_alert_connected(void);
bool bt_alert_send(const char *event_id, uint8_t room, uint8_t horizon_minutes,
                   uint8_t channel, bool simulated, uint32_t receipt_wait_ms);
