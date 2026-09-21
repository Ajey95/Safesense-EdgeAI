#include "delivery_ack.h"

#include "delivery_queue.h"

#include <ctype.h>
#include <string.h>

typedef struct {
    const char *cursor;
    const char *end;
} json_cursor_t;

static void skip_space(json_cursor_t *json)
{
    while (json->cursor < json->end && isspace((unsigned char)*json->cursor)) {
        json->cursor++;
    }
}

static bool consume(json_cursor_t *json, char expected)
{
    skip_space(json);
    if (json->cursor >= json->end || *json->cursor != expected) {
        return false;
    }
    json->cursor++;
    return true;
}

static bool parse_string(json_cursor_t *json, char *out, size_t capacity)
{
    if (!consume(json, '"') || capacity == 0u) {
        return false;
    }
    size_t written = 0u;
    while (json->cursor < json->end && *json->cursor != '"') {
        const unsigned char ch = (unsigned char)*json->cursor++;
        if (ch < 0x20u || ch == '\\' || written + 1u >= capacity) {
            return false;
        }
        out[written++] = (char)ch;
    }
    if (json->cursor >= json->end || *json->cursor != '"') {
        return false;
    }
    json->cursor++;
    out[written] = '\0';
    return true;
}

bool delivery_ack_matches(const char *json_text, size_t length, const char *event_id)
{
    if (json_text == NULL || event_id == NULL || event_id[0] == '\0') {
        return false;
    }
    json_cursor_t json = {.cursor = json_text, .end = json_text + length};
    if (!consume(&json, '{')) {
        return false;
    }
    bool have_event = false;
    bool have_status = false;
    char ack_event[DELIVERY_EVENT_ID_MAX] = {0};
    char status[16] = {0};
    while (true) {
        skip_space(&json);
        if (json.cursor < json.end && *json.cursor == '}') {
            json.cursor++;
            break;
        }
        char key[16];
        char value[DELIVERY_EVENT_ID_MAX];
        if (!parse_string(&json, key, sizeof(key)) || !consume(&json, ':') ||
            !parse_string(&json, value, sizeof(value))) {
            return false;
        }
        if (strcmp(key, "event_id") == 0 && !have_event) {
            memcpy(ack_event, value, strlen(value) + 1u);
            have_event = true;
        } else if (strcmp(key, "status") == 0 && !have_status && strlen(value) < sizeof(status)) {
            memcpy(status, value, strlen(value) + 1u);
            have_status = true;
        } else {
            return false;
        }
        skip_space(&json);
        if (json.cursor < json.end && *json.cursor == ',') {
            json.cursor++;
            continue;
        }
        if (json.cursor < json.end && *json.cursor == '}') {
            json.cursor++;
            break;
        }
        return false;
    }
    skip_space(&json);
    return json.cursor == json.end && have_event && have_status &&
           strcmp(ack_event, event_id) == 0 && strcmp(status, "ACCEPTED") == 0;
}
