# SafeSense BME280 Driver

This is the project's custom environmental-sensor driver. It reads BME280 registers through caller-supplied I2C primitives, loads factory trimming values, and applies the Bosch datasheet compensation equations. It also accepts BMP280-compatible chip ID `0x58` for temperature and pressure only. It does not include or call Adafruit, Bosch, Arduino, or another sensor driver.

## ESP32 integration

Create an ESP-IDF I2C device handle at `0x76` or `0x77`, then bind it to the driver with `bme280_esp_idf_make_bus()`. The hardware application's I2C initialization owns the SDA/SCL pins, pull-ups, and controller configuration; this component owns the BME280 protocol.

Use forced mode in the sensor task, not an ISR:

```c
bme280_reading_t reading;
bme280_status_t status = bme280_read_forced(&bme, &reading, 50);
```

The 50 ms limit is adequate for the supplied default oversampling configuration. Treat `BME280_ERR_TIMEOUT`, `BME280_ERR_BUS`, and `BME280_ERR_INVALID_MEASUREMENT` as unhealthy sensor states; never silently reuse an old reading as a new reading.

Check `reading.humidity_available` before using humidity. A BMP280-compatible device has no humidity channel; its `humidity_percent` field is a placeholder and must not be published as a measurement. The V1 environmental app logs its temperature/pressure locally but does not enqueue a telemetry record because the current backend schema requires humidity.

`firmware/environmental_node` creates an I2C controller/device, initializes this driver, persists each JSON reading in NVS, and delivers it through MQTT. Its SDA/SCL pins (`21` and `22`) are explicit board defaults and must be checked against the actual ESP32 wiring before flashing. Wi-Fi, broker URI, device ID, and sample interval are configured through `idf.py menuconfig`; credentials are not stored in source.

## Acceptance test when hardware arrives

1. Scan the expected I2C address (`0x76` or `0x77`) and confirm chip ID `0x60` for BME280 or `0x58` for BMP280-compatible hardware.
2. Log calibration-read and initialization status.
3. Read temperature and pressure for at least ten forced measurements; read humidity only when chip ID is `0x60`.
4. Compare temperature and humidity against a reference instrument; record the reference, placement, and time.
5. Unplug the sensor and verify the application marks sensor health degraded rather than sending fabricated values.

The Bosch BME280 datasheet is the register and compensation authority: https://www.bosch-sensortec.com/media/boschsensortec/downloads/datasheets/bst-bme280-ds002.pdf
