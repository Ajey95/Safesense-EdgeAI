#include "delivery_mqtt.h"
#include "delivery_ack.h"
#include <stdio.h>
#include <string.h>
#include "esp_event.h"
#include "esp_log.h"
#include "mqtt_client.h"

static const char *TAG = "delivery_mqtt";
static esp_mqtt_client_handle_t client; static delivery_queue_t *pending_queue; static char event_topic[128], ack_topic[128]; static bool connected;
static void flush_one(void) {
    if (!client || !pending_queue || !connected) return;
    delivery_record_t record; if (delivery_queue_peek(pending_queue, &record) != 0) return;
    if (esp_mqtt_client_publish(client, event_topic, record.payload, 0, 1, 0) < 0) ESP_LOGW(TAG, "Publish deferred; event remains in NVS");
}
static void mqtt_event(void *arg, esp_event_base_t base, int32_t id, void *data) {
    (void)arg; (void)base; esp_mqtt_event_handle_t event = data;
    if (id == MQTT_EVENT_CONNECTED) { connected = true; esp_mqtt_client_subscribe(client, ack_topic, 1); flush_one(); return; }
    if (id == MQTT_EVENT_DISCONNECTED || id == MQTT_EVENT_ERROR) { connected = false; return; }
    if (id != MQTT_EVENT_DATA || event->topic_len != (int)strlen(ack_topic) || strncmp(event->topic, ack_topic, event->topic_len) != 0) return;
    if (event->current_data_offset != 0 || event->data_len != event->total_data_len) return;
    delivery_record_t record; if (delivery_queue_peek(pending_queue, &record) != 0) return;
    /* Only an exact, successful application ACK may remove persistent data. */
    if (delivery_ack_matches(event->data, event->data_len, record.event_id)) { (void)delivery_queue_ack_head(pending_queue, record.event_id); flush_one(); }
}
int delivery_mqtt_start(const delivery_mqtt_config_t *config) {
    if (!config || !config->broker_uri || !config->device_id || !config->queue) return -1;
    pending_queue = config->queue; connected = false;
    const int event_length = config->event_topic && config->event_topic[0]
                                 ? snprintf(event_topic, sizeof(event_topic), "%s", config->event_topic)
                                 : snprintf(event_topic, sizeof(event_topic), "safesense/%s/event", config->device_id);
    const int ack_length = config->ack_topic && config->ack_topic[0]
                               ? snprintf(ack_topic, sizeof(ack_topic), "%s", config->ack_topic)
                               : snprintf(ack_topic, sizeof(ack_topic), "safesense/%s/ack", config->device_id);
    if (event_length <= 0 || event_length >= (int)sizeof(event_topic) ||
        ack_length <= 0 || ack_length >= (int)sizeof(ack_topic)) return -1;
    esp_mqtt_client_config_t settings = {.broker.address.uri = config->broker_uri, .broker.verification.certificate = config->server_certificate};
    client = esp_mqtt_client_init(&settings); if (!client) return -1;
    if (esp_mqtt_client_register_event(client, ESP_EVENT_ANY_ID, mqtt_event, NULL) != ESP_OK) return -1;
    return esp_mqtt_client_start(client) == ESP_OK ? 0 : -1;
}
void delivery_mqtt_flush(void) { flush_one(); }
bool delivery_mqtt_is_connected(void) { return connected; }
