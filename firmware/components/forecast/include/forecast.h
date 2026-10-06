#pragma once

#include <stdbool.h>
#include <stdint.h>

#define FORECAST_HISTORY_MINUTES 61
#define FORECAST_CHANNELS 5
#define FORECAST_HORIZONS 6

/* History is oldest to newest, one sample per simulated/real minute.
 * Room: 0 cold storage, 1 laboratory, 2 classroom, 3 bakery, 4 server room.
 * Output horizons: +5, +10, +15, +20, +25, +30 minutes. */
bool forecast_predict(const float history[FORECAST_HISTORY_MINUTES][FORECAST_CHANNELS],
                      uint8_t room, float out[FORECAST_HORIZONS][FORECAST_CHANNELS]);
const char *forecast_model_sha256(void);
