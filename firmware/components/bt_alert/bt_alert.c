#include "bt_alert.h"

#include <stdio.h>
#include <string.h>

#include "esp_bt.h"
#include "esp_bt_main.h"
#include "esp_gap_bt_api.h"
#include "esp_log.h"
#include "esp_spp_api.h"
#include "freertos/FreeRTOS.h"
#include "freertos/event_groups.h"

#define RECEIPT_BIT BIT0
#define READY_BIT BIT1
#define TEST_BIT BIT2
static const char *TAG = "safesense_bt_alert";
static EventGroupHandle_t events;
static uint32_t spp_handle;
static bool writable;
static char expected_id[64];
static char incoming[96];
static size_t incoming_used;

static void gap_callback(esp_bt_gap_cb_event_t event, esp_bt_gap_cb_param_t *param) {
    if (event == ESP_BT_GAP_CFM_REQ_EVT) {
        /* The board has no display or input. Windows must also accept pairing.
         * Legacy fixed-PIN pairing is deliberately not enabled. */
        (void)esp_bt_gap_ssp_confirm_reply(param->cfm_req.bda, true);
    } else if (event == ESP_BT_GAP_PIN_REQ_EVT) {
        (void)esp_bt_gap_pin_reply(param->pin_req.bda, false, 0, NULL);
    }
}

static void spp_callback(esp_spp_cb_event_t event, esp_spp_cb_param_t *param) {
    switch (event) {
    case ESP_SPP_INIT_EVT:
        if (param->init.status == ESP_SPP_SUCCESS)
            (void)esp_spp_start_srv(ESP_SPP_SEC_AUTHENTICATE, ESP_SPP_ROLE_SLAVE, 0, "SafeSenseAlert");
        break;
    case ESP_SPP_START_EVT:
        if (param->start.status == ESP_SPP_SUCCESS) {
            (void)esp_bt_gap_set_device_name("SafeSense-TX-Alert");
            (void)esp_bt_gap_set_scan_mode(ESP_BT_CONNECTABLE, ESP_BT_GENERAL_DISCOVERABLE);
        }
        break;
    case ESP_SPP_SRV_OPEN_EVT:
        if (param->srv_open.status == ESP_SPP_SUCCESS) {
            spp_handle = param->srv_open.handle;
            writable = true;
            xEventGroupSetBits(events, READY_BIT);
            ESP_LOGI(TAG, "Nearby laptop SPP link opened");
        }
        break;
    case ESP_SPP_CLOSE_EVT:
        spp_handle = 0;
        writable = false;
        xEventGroupClearBits(events, READY_BIT);
        ESP_LOGW(TAG, "Nearby laptop SPP link closed");
        break;
    case ESP_SPP_WRITE_EVT:
        writable = param->write.status == ESP_SPP_SUCCESS && !param->write.cong;
        break;
    case ESP_SPP_CONG_EVT:
        writable = !param->cong.cong;
        break;
    case ESP_SPP_DATA_IND_EVT:
        for (unsigned i = 0; i < param->data_ind.len; ++i) {
            const char ch = (char)param->data_ind.data[i];
            if (ch == '\n') {
                incoming[incoming_used] = '\0';
                if (strncmp(incoming, "ACK|", 4) == 0 &&
                    strcmp(incoming + 4, expected_id) == 0 && expected_id[0])
                    xEventGroupSetBits(events, RECEIPT_BIT);
                else if (strcmp(incoming, "TEST") == 0)
                    xEventGroupSetBits(events, TEST_BIT);
                incoming_used = 0;
            } else if (ch >= 32 && ch <= 126 && incoming_used + 1 < sizeof(incoming)) {
                incoming[incoming_used++] = ch;
            } else {
                incoming_used = 0;
            }
        }
        break;
    default:
        break;
    }
}

bool bt_alert_start(void) {
    if (events) return true;
    events = xEventGroupCreate();
    if (!events) return false;
    if (esp_bt_controller_mem_release(ESP_BT_MODE_BLE) != ESP_OK) return false;
    esp_bt_controller_config_t config = BT_CONTROLLER_INIT_CONFIG_DEFAULT();
    if (esp_bt_controller_init(&config) != ESP_OK ||
        esp_bt_controller_enable(ESP_BT_MODE_CLASSIC_BT) != ESP_OK) return false;
    esp_bluedroid_config_t host = BT_BLUEDROID_INIT_CONFIG_DEFAULT();
    if (esp_bluedroid_init_with_cfg(&host) != ESP_OK || esp_bluedroid_enable() != ESP_OK) return false;
    if (esp_bt_gap_register_callback(gap_callback) != ESP_OK) return false;
    esp_bt_sp_param_t parameter = ESP_BT_SP_IOCAP_MODE;
    esp_bt_io_cap_t capability = ESP_BT_IO_CAP_NONE;
    if (esp_bt_gap_set_security_param(parameter, &capability, sizeof(capability)) != ESP_OK) return false;
    if (esp_spp_register_callback(spp_callback) != ESP_OK) return false;
    const esp_spp_cfg_t spp = {.mode = ESP_SPP_MODE_CB, .enable_l2cap_ertm = true, .tx_buffer_size = 0};
    if (esp_spp_enhanced_init(&spp) != ESP_OK) return false;
    ESP_LOGI(TAG, "Bluetooth SPP alert server starting; pair laptop with SafeSense-TX-Alert");
    return true;
}

bool bt_alert_connected(void) {
    return events && (xEventGroupGetBits(events) & READY_BIT) && spp_handle != 0;
}

bool bt_alert_take_test_request(void) {
    return events && (xEventGroupWaitBits(events, TEST_BIT, pdTRUE, pdFALSE, 0)
                      & TEST_BIT) != 0;
}

bool bt_alert_send_sample(const char *event_id, const char *payload, uint32_t receipt_wait_ms) {
    if (!bt_alert_connected() || !writable || !event_id || !payload ||
        strlen(event_id) >= sizeof(expected_id) || strlen(payload) > 768) return false;
    char message[784];
    const int size = snprintf(message, sizeof(message), "DATA|%s\n", payload);
    if (size <= 0 || size >= sizeof(message)) return false;
    snprintf(expected_id, sizeof(expected_id), "%s", event_id);
    xEventGroupClearBits(events, RECEIPT_BIT);
    writable = false;
    if (esp_spp_write(spp_handle, size, (uint8_t *)message) != ESP_OK) {
        expected_id[0] = '\0';
        writable = true;
        return false;
    }
    const bool received = (xEventGroupWaitBits(events, RECEIPT_BIT, pdTRUE, pdFALSE,
                                               pdMS_TO_TICKS(receipt_wait_ms)) & RECEIPT_BIT) != 0;
    expected_id[0] = '\0';
    ESP_LOGI(TAG, "Bluetooth sensor receipt event=%s state=%s", event_id,
             received ? "STORED" : "UNCONFIRMED");
    return received;
}

bool bt_alert_send(const char *event_id, uint8_t room, uint8_t horizon_minutes,
                   uint8_t channel, bool simulated, uint32_t receipt_wait_ms) {
    if (!bt_alert_connected() || !writable || !event_id || strlen(event_id) >= sizeof(expected_id)
        || room >= 5 || channel >= 5 || horizon_minutes > 30) return false;
    for (const char *p = event_id; *p; ++p)
        if (!( (*p >= '0' && *p <= '9') || (*p >= 'A' && *p <= 'Z') ||
               (*p >= 'a' && *p <= 'z') || *p == '-' || *p == '_' )) return false;
    char message[128];
    const int size = snprintf(message, sizeof(message), "ALERT|%s|%u|%u|%u|%c\n",
                              event_id, room, horizon_minutes, channel,
                              simulated ? 'S' : 'R');
    if (size <= 0 || size >= sizeof(message)) return false;
    snprintf(expected_id, sizeof(expected_id), "%s", event_id);
    xEventGroupClearBits(events, RECEIPT_BIT);
    writable = false;
    if (esp_spp_write(spp_handle, size, (uint8_t *)message) != ESP_OK) {
        expected_id[0] = '\0';
        writable = true;
        return false;
    }
    const bool received = (xEventGroupWaitBits(events, RECEIPT_BIT, pdTRUE, pdFALSE,
                                               pdMS_TO_TICKS(receipt_wait_ms)) & RECEIPT_BIT) != 0;
    expected_id[0] = '\0';
    ESP_LOGI(TAG, "Bluetooth laptop receipt event=%s state=%s", event_id,
             received ? "STORED" : "UNCONFIRMED");
    return received;
}
