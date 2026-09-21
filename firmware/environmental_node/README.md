# Environmental Review Node

This ESP-IDF application is the rubric demonstration path:

```text
BME280 register driver → JSON → NVS queue → MQTT QoS 1 → application ACK
```

Configure and build:

```powershell
cd firmware\environmental_node
idf.py set-target esp32
idf.py menuconfig
idf.py build
idf.py flash monitor
```

Under **SafeSense environmental node**, set the Wi-Fi SSID/password, local MQTT broker URI, device ID and sampling interval. Do not commit a generated `sdkconfig` containing credentials.

## Persistence demonstration

1. Stop the MQTT broker or disconnect Wi-Fi.
2. Wait for `Persisted reading; pending=1`.
3. Reset or power-cycle the ESP32.
4. Capture `Restored 1 pending telemetry record(s) from NVS`.
5. Restore the broker and run `scripts/mqtt_bridge.py`.
6. Show the exact `ACCEPTED` ACK and the record disappearing only after backend acceptance.

The current payload marks gas risk as `UNAVAILABLE` because BME280 is not a gas sensor. This intentionally produces a `DEGRADED` backend state instead of inventing a normal reading.
