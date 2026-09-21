# SafeSense BME280 Driver

This is the project's custom environmental-sensor driver. It reads BME280 registers through caller-supplied I2C primitives, loads factory trimming values, and applies the Bosch datasheet compensation equations. It does not include or call Adafruit, Bosch, Arduino, or another BME280 driver.

## ESP32 integration

Create an ESP-IDF I2C device handle at `0x76` or `0x77`, then bind it to the driver with `bme280_esp_idf_make_bus()`. The hardware application's I2C initialization owns the SDA/SCL pins, pull-ups, and controller configuration; this component owns the BME280 protocol.

Use forced mode in the sensor task, not an ISR:

```c
bme280_reading_t reading;
bme280_status_t status = bme280_read_forced(&bme, &reading, 50);
```

The 50 ms limit is adequate for the supplied default oversampling configuration. Treat `BME280_ERR_TIMEOUT`, `BME280_ERR_BUS`, and `BME280_ERR_INVALID_MEASUREMENT` as unhealthy sensor states; never silently reuse an old reading as a new reading.

`firmware/environmental_node` creates an I2C controller/device, initializes this driver, persists each JSON reading in NVS, and delivers it through MQTT. Its SDA/SCL pins (`21` and `22`) are explicit board defaults and must be checked against the actual ESP32 wiring before flashing. Wi-Fi, broker URI, device ID, and sample interval are configured through `idf.py menuconfig`; credentials are not stored in source.

## Acceptance test when hardware arrives

1. Scan the expected I2C address (`0x76` or `0x77`) and confirm chip ID `0x60`.
2. Log calibration-read and initialization status.
3. Read temperature, pressure, and humidity for at least ten forced measurements.
4. Compare temperature and humidity against a reference instrument; record the reference, placement, and time.
5. Unplug the sensor and verify the application marks sensor health degraded rather than sending fabricated values.

The Bosch BME280 datasheet is the register and compensation authority: https://www.bosch-sensortec.com/media/boschsensortec/downloads/datasheets/bst-bme280-ds002.pdf
