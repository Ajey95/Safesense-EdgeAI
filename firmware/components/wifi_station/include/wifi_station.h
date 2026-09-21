#pragma once

#include <stdint.h>

/* Starts a reconnecting station and waits for an IPv4 address. Returns zero
 * when connected, or -1 on invalid configuration, setup failure or timeout. */
int wifi_station_start(const char *ssid, const char *password, uint32_t timeout_ms);
