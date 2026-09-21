#include "bme280_esp_idf.h"

#include "esp_err.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

/* Adapter only: all BME280 protocol knowledge remains in bme280_driver.c. */
static int bme280_esp_idf_read(void *context, uint8_t address, uint8_t reg, uint8_t *data, size_t length) {
    (void)address;
    bme280_esp_idf_bus_t *bus = context;
    return i2c_master_transmit_receive(bus->handle, &reg, 1, data, length, 100) == ESP_OK ? 0 : -1;
}

static int bme280_esp_idf_write(void *context, uint8_t address, uint8_t reg, const uint8_t *data, size_t length) {
    (void)address;
    uint8_t packet[1 + 1];
    if (length != 1) return -1;
    packet[0] = reg; packet[1] = data[0];
    bme280_esp_idf_bus_t *bus = context;
    return i2c_master_transmit(bus->handle, packet, sizeof(packet), 100) == ESP_OK ? 0 : -1;
}

static void bme280_esp_idf_delay(void *context, uint32_t milliseconds) {
    (void)context;
    vTaskDelay(pdMS_TO_TICKS(milliseconds));
}

void bme280_esp_idf_make_bus(bme280_bus_t *out_bus, bme280_esp_idf_bus_t *idf_bus) {
    if (!out_bus) return;
    *out_bus = (bme280_bus_t){
        .read = bme280_esp_idf_read,
        .write = bme280_esp_idf_write,
        .delay_ms = bme280_esp_idf_delay,
        .context = idf_bus,
    };
}
