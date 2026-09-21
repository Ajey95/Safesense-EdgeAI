#include <string.h>
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "lwip/inet.h"
#include "lwip/sockets.h"
#include "wifi_station.h"

#define CSI_PACKET_PORT 3333

void app_main(void) {
    if (wifi_station_start(CONFIG_SAFESENSE_WIFI_SSID, CONFIG_SAFESENSE_WIFI_PASSWORD, 30000) != 0) {
        ESP_LOGE("csi_tx", "Wi-Fi connection failed; configure credentials with menuconfig");
        return;
    }
    const int socket_fd = socket(AF_INET, SOCK_DGRAM, IPPROTO_IP);
    if (socket_fd < 0) { ESP_LOGE("csi_tx", "UDP socket creation failed"); return; }
    struct sockaddr_in target = {.sin_family = AF_INET, .sin_port = htons(CSI_PACKET_PORT), .sin_addr.s_addr = inet_addr(CONFIG_SAFESENSE_RECEIVER_IP)};
    uint32_t sequence = 0;
    while (true) {
        /* Wi-Fi must be connected on the fixed review channel before this task starts. */
        (void)sendto(socket_fd, &sequence, sizeof(sequence), 0, (struct sockaddr *)&target, sizeof(target));
        sequence++; vTaskDelay(pdMS_TO_TICKS(20)); /* 50 controlled packets per second. */
    }
}
