#pragma once

#include <stdbool.h>
#include <stddef.h>

bool delivery_ack_matches(const char *json, size_t length, const char *event_id);
