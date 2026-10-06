# TX BME680 hardware check (V1 branch)

Standalone ESP-IDF 6.1 diagnostic for the classic ESP32 TX board. It uses the
`esp-idf-lib/bme680` component at I2C address `0x76`, SDA GPIO21, SCL GPIO22.
It temporarily replaces the normal TX application when flashed.

From the repository root in an ESP-IDF shell:

```text
idf.py -C firmware/bme680_hardware_check build
idf.py -C firmware/bme680_hardware_check -p COM11 flash
idf.py -C firmware/bme680_hardware_check -p COM11 monitor
```

COM11 is the port observed on 2026-09-23, not a permanent board identifier.
Confirm the TX board before flashing. The diagnostic takes ten readings at
roughly two-second intervals and then stops; reset the board to repeat it.

On 2026-09-23, TX (ESP32 MAC ending `1f:ec`) initialized the connected BME680
and returned ten temperature, humidity and pressure samples. Gas resistance was
zero on the first sample, then positive and increasing across the remaining
nine samples, consistent with startup/warm-up. This is a functional check, not
calibration or a gas concentration/air-quality measurement.
