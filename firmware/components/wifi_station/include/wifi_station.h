#pragma once

#include <stdint.h>

/* Starts a reconnecting station and waits for an IPv4 address. Returns zero
 * when connected, or -1 on invalid configuration, setup failure or timeout. */
int safesense_wifi_station_start(const char *ssid, const char *password, uint32_t timeout_ms);

/* The station can acquire its first IP after start's wait timed out. */
int safesense_wifi_station_connected(void);
