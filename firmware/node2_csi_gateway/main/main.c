#include "csi_capture_esp_idf.h"
#include "csi_model.h"
#include "csi_pipeline.h"
#include "delivery_mqtt.h"
#include "delivery_nvs.h"
#include "delivery_queue.h"
#include "esp_log.h"
#include "esp_random.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "freertos/semphr.h"
#include "freertos/task.h"
#include "fusion_engine.h"
#include "lwip/inet.h"
#include "lwip/sockets.h"
#include "node_protocol.h"
#include "safety_output_esp_idf.h"
#include "wifi_station.h"

#include <stdio.h>
#include <string.h>

#define REGISTRATION_TOKEN "SAFESENSE_NODE2_V1"

#ifdef CONFIG_SAFESENSE_LEDS_ACTIVE_HIGH
#define LEDS_ACTIVE_HIGH true
#else
#define LEDS_ACTIVE_HIGH false
#endif

#ifdef CONFIG_SAFESENSE_BUZZER_ACTIVE_HIGH
#define BUZZER_ACTIVE_HIGH true
#else
#define BUZZER_ACTIVE_HIGH false
#endif

typedef struct {
    node_environment_t environment;
    int64_t environment_received_us;
    fusion_activity_t activity;
    float confidence;
    int8_t rssi_dbm;
    float packet_rate_hz;
    int64_t csi_received_us;
    bool window_ready;
} gateway_state_t;

static const char *TAG = "ss_node2";
static SemaphoreHandle_t state_lock;
static gateway_state_t gateway_state;
static node_sequence_tracker_t sequence_tracker;
static QueueHandle_t csi_queue;
static csi_pipeline_t csi_pipeline;
static float csi_window[CSI_WINDOW_FRAMES][CSI_DATA_SUBCARRIERS];
static delivery_nvs_t nvs_adapter;
static delivery_queue_t delivery_queue;
static safety_output_esp_idf_t local_output;

static const char *risk_name(gas_risk_t risk)
{
    switch (risk) {
    case GAS_RISK_NORMAL: return "NORMAL";
    case GAS_RISK_WARNING: return "WARNING";
    case GAS_RISK_CRITICAL: return "CRITICAL";
    default: return "UNAVAILABLE";
    }
}

static const char *activity_name(fusion_activity_t activity)
{
    switch (activity) {
    case FUSION_ACTIVITY_VACANT: return "VACANT";
    case FUSION_ACTIVITY_STATIONARY: return "STATIONARY";
    case FUSION_ACTIVITY_WALKING: return "WALKING";
    default: return "UNKNOWN";
    }
}

static const char *state_name(fusion_state_t state)
{
    switch (state) {
    case FUSION_STATE_NORMAL: return "NORMAL";
    case FUSION_STATE_WARNING: return "WARNING";
    case FUSION_STATE_INCIDENT: return "INCIDENT";
    default: return "DEGRADED";
    }
}

static fusion_environment_risk_t fusion_risk(gas_risk_t risk)
{
    switch (risk) {
    case GAS_RISK_NORMAL: return FUSION_RISK_NORMAL;
    case GAS_RISK_WARNING: return FUSION_RISK_WARNING;
    case GAS_RISK_CRITICAL: return FUSION_RISK_CRITICAL;
    default: return FUSION_RISK_UNAVAILABLE;
    }
}

static void node_receive_task(void *argument)
{
    (void)argument;
    const int socket_fd = socket(AF_INET, SOCK_DGRAM, IPPROTO_IP);
    struct timeval timeout = {.tv_sec = 1, .tv_usec = 0};
    struct sockaddr_in local = {
        .sin_family = AF_INET,
        .sin_port = htons(CONFIG_SAFESENSE_PROBE_PORT),
        .sin_addr.s_addr = htonl(INADDR_ANY),
    };
    struct sockaddr_in node1 = {
        .sin_family = AF_INET,
        .sin_port = htons(CONFIG_SAFESENSE_REGISTRATION_PORT),
        .sin_addr.s_addr = inet_addr(CONFIG_SAFESENSE_NODE1_IP),
    };
    if (socket_fd < 0 || bind(socket_fd, (struct sockaddr *)&local, sizeof(local)) != 0 ||
        setsockopt(socket_fd, SOL_SOCKET, SO_RCVTIMEO, &timeout, sizeof(timeout)) != 0) {
        ESP_LOGE(TAG, "Node protocol socket failed");
        vTaskDelete(NULL);
    }
    uint8_t packet[NODE_PROTOCOL_PACKET_SIZE];
    while (true) {
        (void)sendto(socket_fd, REGISTRATION_TOKEN, strlen(REGISTRATION_TOKEN), 0,
                     (struct sockaddr *)&node1, sizeof(node1));
        struct sockaddr_in sender;
        socklen_t sender_length = sizeof(sender);
        const int received = recvfrom(socket_fd, packet, sizeof(packet), 0,
                                      (struct sockaddr *)&sender, &sender_length);
        if (received != NODE_PROTOCOL_PACKET_SIZE || sender.sin_addr.s_addr != node1.sin_addr.s_addr) {
            continue;
        }
        node_environment_t decoded;
        const node_protocol_status_t status = node_protocol_decode(
            packet, sizeof(packet), CONFIG_SAFESENSE_SENSOR_MAX_AGE_MS,
            &sequence_tracker, &decoded);
        if (status != NODE_PROTOCOL_OK) {
            ESP_LOGW(TAG, "Rejected Node 1 packet: %d", status);
            continue;
        }
        xSemaphoreTake(state_lock, portMAX_DELAY);
        gateway_state.environment = decoded;
        gateway_state.environment_received_us = esp_timer_get_time();
        xSemaphoreGive(state_lock);
    }
}

static void csi_processing_task(void *argument)
{
    (void)argument;
    csi_pipeline_init(&csi_pipeline);
    csi_packet_t packet;
    uint32_t frames = 0u;
    int64_t rate_started_us = esp_timer_get_time();
    while (true) {
        if (xQueueReceive(csi_queue, &packet, portMAX_DELAY) != pdTRUE) {
            continue;
        }
        frames++;
        bool ready = false;
        const csi_status_t status = csi_pipeline_push(&csi_pipeline, packet.iq,
                                                       sizeof(packet.iq),
                                                       packet.first_word_invalid,
                                                       &ready);
        fusion_activity_t activity = FUSION_ACTIVITY_UNKNOWN;
        float confidence = 0.0f;
        if (status == CSI_OK && ready &&
            csi_pipeline_copy_window(&csi_pipeline, csi_window) == CSI_OK) {
            activity = csi_model_infer(csi_window, &confidence);
        }
        const int64_t now = esp_timer_get_time();
        xSemaphoreTake(state_lock, portMAX_DELAY);
        gateway_state.csi_received_us = packet.received_us;
        gateway_state.rssi_dbm = packet.rssi_dbm;
        if (ready) {
            gateway_state.window_ready = true;
            gateway_state.activity = activity;
            gateway_state.confidence = confidence;
        }
        if (now - rate_started_us >= 1000000) {
            gateway_state.packet_rate_hz = frames * 1000000.0f /
                                           (float)(now - rate_started_us);
            frames = 0u;
            rate_started_us = now;
        }
        xSemaphoreGive(state_lock);
    }
}

static delivery_status_t persist_transition(const gateway_state_t *snapshot,
                                            const fusion_decision_t *decision,
                                            bool environment_fresh,
                                            bool csi_fresh)
{
    delivery_record_t record = {0};
    snprintf(record.event_id, sizeof(record.event_id), "node2-%08lx-%08lx",
             (unsigned long)esp_random(), (unsigned long)snapshot->environment.sequence);
#ifdef CONFIG_SAFESENSE_CSI_TFLM_MODEL
    const char *model_state = "RELEASED_INT8";
#else
    const char *model_state = "DISABLED_RELEASE_GATE";
#endif
    const safety_output_pattern_t output = safety_output_pattern_for_state(decision->state, 0u);
    const float gas_ratio = snapshot->environment.gas_ratio_q15 / 32768.0f;
    const bool sensor_healthy =
        (snapshot->environment.flags & NODE_FLAG_SENSOR_HEALTHY) != 0u;
    const bool gas_available =
        (snapshot->environment.flags & (NODE_FLAG_GAS_VALID | NODE_FLAG_HEAT_STABLE)) ==
            (NODE_FLAG_GAS_VALID | NODE_FLAG_HEAT_STABLE) &&
        snapshot->environment.gas_resistance_ohm > 0u;
    char temperature_json[24] = "null";
    char humidity_json[24] = "null";
    char pressure_json[24] = "null";
    char gas_resistance_json[24] = "null";
    char gas_baseline_json[24] = "null";
    char gas_ratio_json[24] = "null";
    if (sensor_healthy) {
        snprintf(temperature_json, sizeof(temperature_json), "%.3f",
                 snapshot->environment.temperature_milli_c / 1000.0f);
        snprintf(humidity_json, sizeof(humidity_json), "%.3f",
                 snapshot->environment.humidity_milli_percent / 1000.0f);
        snprintf(pressure_json, sizeof(pressure_json), "%lu",
                 (unsigned long)snapshot->environment.pressure_pa);
    }
    if (gas_available) {
        snprintf(gas_resistance_json, sizeof(gas_resistance_json), "%lu",
                 (unsigned long)snapshot->environment.gas_resistance_ohm);
        snprintf(gas_baseline_json, sizeof(gas_baseline_json), "%lu",
                 (unsigned long)snapshot->environment.gas_baseline_ohm);
        snprintf(gas_ratio_json, sizeof(gas_ratio_json), "%.4f", gas_ratio);
    }
    const int length = snprintf(
        record.payload, sizeof(record.payload),
        "{\"event_id\":\"%s\",\"device_id\":\"%s\",\"observed_at\":null,"
        "\"firmware_version\":\"esp32s3-v2\","
        "\"environment\":{\"temperature_c\":%s,\"humidity_pct\":%s,"
        "\"pressure_pa\":%s,\"gas_resistance_ohm\":%s,\"gas_baseline_ohm\":%s,"
        "\"gas_ratio\":%s,\"gas_risk\":\"%s\",\"gas_valid\":%s,"
        "\"heat_stable\":%s,\"sensor_healthy\":%s,\"is_fresh\":%s},"
        "\"csi\":{\"activity\":\"%s\",\"confidence\":%.3f,\"quality\":\"%s\","
        "\"tx_node\":\"ONLINE\",\"rx_node\":\"ONLINE\",\"packet_rate_hz\":%.2f,"
        "\"rssi_dbm\":%d,\"is_fresh\":%s,\"window_ready\":%s,"
        "\"model_release_state\":\"%s\"},"
        "\"system\":{\"mqtt\":\"%s\",\"local_storage\":\"OK\","
        "\"node1_status\":\"ONLINE\",\"node2_status\":\"ONLINE\","
        "\"output_state\":\"%s\",\"green_led\":%s,\"yellow_led\":%s,"
        "\"red_led\":%s,\"buzzer_on\":%s,\"queue_depth\":%u,\"csi_drops\":%lu}}",
        record.event_id, CONFIG_SAFESENSE_DEVICE_ID,
        temperature_json, humidity_json, pressure_json, gas_resistance_json,
        gas_baseline_json, gas_ratio_json,
        risk_name(snapshot->environment.gas_risk),
        (snapshot->environment.flags & NODE_FLAG_GAS_VALID) ? "true" : "false",
        (snapshot->environment.flags & NODE_FLAG_HEAT_STABLE) ? "true" : "false",
        (snapshot->environment.flags & NODE_FLAG_SENSOR_HEALTHY) ? "true" : "false",
        environment_fresh ? "true" : "false",
        activity_name(snapshot->activity), snapshot->confidence,
        snapshot->window_ready ? "GOOD" : "UNAVAILABLE", snapshot->packet_rate_hz,
        snapshot->rssi_dbm, csi_fresh ? "true" : "false",
        snapshot->window_ready ? "true" : "false", model_state,
        delivery_mqtt_is_connected() ? "CONNECTED" : "DISCONNECTED",
        state_name(decision->state), output.green_led ? "true" : "false",
        output.yellow_led ? "true" : "false", output.red_led ? "true" : "false",
        output.buzzer_on ? "true" : "false",
        (unsigned int)(delivery_queue_count(&delivery_queue) + 1u),
        (unsigned long)csi_capture_dropped_packets());
    if (length < 0 || length >= (int)sizeof(record.payload)) {
        return DELIVERY_ERR_ARGUMENT;
    }
    return delivery_queue_enqueue(&delivery_queue, &record);
}

static void fusion_output_task(void *argument)
{
    (void)argument;
    fusion_tracker_t tracker = {0};
    const fusion_policy_t policy = {
        .minimum_csi_confidence = CONFIG_SAFESENSE_CSI_MIN_CONFIDENCE_PERCENT / 100.0f,
    };
    fusion_state_t displayed_state = FUSION_STATE_DEGRADED;
    int64_t state_started_us = esp_timer_get_time();
    while (true) {
        gateway_state_t snapshot;
        xSemaphoreTake(state_lock, portMAX_DELAY);
        snapshot = gateway_state;
        xSemaphoreGive(state_lock);
        const int64_t now = esp_timer_get_time();
        if (snapshot.environment_received_us <= 0) {
            (void)safety_output_esp_idf_apply(&local_output, FUSION_STATE_DEGRADED,
                                              (uint32_t)(now / 1000));
            vTaskDelay(pdMS_TO_TICKS(100u));
            continue;
        }
        const bool environment_fresh = snapshot.environment_received_us > 0 &&
            now - snapshot.environment_received_us <= CONFIG_SAFESENSE_SENSOR_MAX_AGE_MS * 1000LL;
        const bool csi_fresh = snapshot.csi_received_us > 0 &&
            now - snapshot.csi_received_us <= CONFIG_SAFESENSE_CSI_MAX_AGE_MS * 1000LL;
        const fusion_input_t input = {
            .environmental_risk = fusion_risk(snapshot.environment.gas_risk),
            .environmental_sensor_healthy =
                (snapshot.environment.flags & NODE_FLAG_SENSOR_HEALTHY) != 0u,
            .environmental_reading_fresh = environment_fresh,
            .csi_fresh = csi_fresh,
            .activity = snapshot.activity,
            .csi_confidence = snapshot.confidence,
        };
        const fusion_decision_t decision = fusion_evaluate(&input, &policy);
        if (decision.state != displayed_state) {
            displayed_state = decision.state;
            state_started_us = now;
        }
        (void)safety_output_esp_idf_apply(&local_output, displayed_state,
                                          (uint32_t)((now - state_started_us) / 1000));
        if (fusion_tracker_step(&tracker, &decision)) {
            const delivery_status_t queued = persist_transition(&snapshot, &decision,
                                                                 environment_fresh,
                                                                 csi_fresh);
            if (queued == DELIVERY_OK) {
                delivery_mqtt_flush();
            } else {
                ESP_LOGE(TAG, "Transition persistence failed: %d pending=%u",
                         queued, delivery_queue_count(&delivery_queue));
            }
            ESP_LOGI(TAG, "Fusion=%s reason=%s activity=%s confidence=%.2f",
                     state_name(decision.state), decision.reason_code,
                     activity_name(snapshot.activity), snapshot.confidence);
        }
        vTaskDelay(pdMS_TO_TICKS(100u));
    }
}

void app_main(void)
{
    state_lock = xSemaphoreCreateMutex();
    if (state_lock == NULL) {
        ESP_LOGE(TAG, "State mutex allocation failed");
        return;
    }
    delivery_store_t store;
    if (delivery_nvs_open(&nvs_adapter, &store) != DELIVERY_OK ||
        delivery_queue_init(&delivery_queue, &store) != DELIVERY_OK) {
        ESP_LOGE(TAG, "NVS delivery queue restore failed; refusing lossy startup");
        return;
    }
    ESP_LOGI(TAG, "Restored %u persistent event(s)", delivery_queue_count(&delivery_queue));
    if (wifi_station_start(CONFIG_SAFESENSE_WIFI_SSID, CONFIG_SAFESENSE_WIFI_PASSWORD, 30000u) != 0) {
        ESP_LOGE(TAG, "Node 1 SoftAP connection failed");
        return;
    }
    const safety_output_esp_idf_config_t outputs = {
        .green_pin = CONFIG_SAFESENSE_GREEN_LED_GPIO,
        .yellow_pin = CONFIG_SAFESENSE_YELLOW_LED_GPIO,
        .red_pin = CONFIG_SAFESENSE_RED_LED_GPIO,
        .buzzer_pin = CONFIG_SAFESENSE_BUZZER_GPIO,
        .leds_active_high = LEDS_ACTIVE_HIGH,
        .buzzer_active_high = BUZZER_ACTIVE_HIGH,
#ifdef CONFIG_SAFESENSE_BUZZER_PASSIVE
        .buzzer_mode = SAFETY_BUZZER_PASSIVE,
#else
        .buzzer_mode = SAFETY_BUZZER_ACTIVE,
#endif
    };
    if (safety_output_esp_idf_init(&local_output, &outputs) != ESP_OK) {
        ESP_LOGE(TAG, "LED/buzzer initialization failed");
        return;
    }
    csi_queue = xQueueCreate(32u, sizeof(csi_packet_t));
    if (csi_queue == NULL || csi_capture_start(csi_queue) != 0) {
        ESP_LOGE(TAG, "ESP32-S3 CSI capture initialization failed");
        return;
    }
    const delivery_mqtt_config_t mqtt = {
        .broker_uri = CONFIG_SAFESENSE_MQTT_BROKER_URI,
        .device_id = CONFIG_SAFESENSE_DEVICE_ID,
        .event_topic = CONFIG_SAFESENSE_MQTT_EVENT_TOPIC,
        .ack_topic = CONFIG_SAFESENSE_MQTT_ACK_TOPIC,
        .server_certificate = NULL,
        .queue = &delivery_queue,
    };
    if (delivery_mqtt_start(&mqtt) != 0) {
        ESP_LOGW(TAG, "MQTT unavailable; events remain in NVS");
    }
    xTaskCreate(node_receive_task, "node_protocol", 6144, NULL, 6, NULL);
    xTaskCreate(csi_processing_task, "csi_processing", 8192, NULL, 6, NULL);
    xTaskCreate(fusion_output_task, "fusion_output", 8192, NULL, 5, NULL);
}
