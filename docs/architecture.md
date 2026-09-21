# SafeSense two-node architecture

This is the implemented software topology for the available parts: one BME680, two ESP32-S3 boards, resistors, LEDs, and a buzzer.

![SafeSense architecture](architecture.svg)

## Node 1 — BME680 sensor and CSI stimulus

Node 1 hosts the custom BME680 I2C driver and creates the `SafeSense-V2` SoftAP. After Node 2 registers, Node 1 samples temperature, humidity, pressure, and gas resistance; updates a relative clean-air baseline; classifies environmental risk; and sends a fixed 50-byte big-endian UDP snapshot with protocol version, sequence, flags, monotonic sample age, and CRC32. The 50 Hz traffic also supplies controlled CSI stimulus.

The sensor LED means the current BME680 reading passed its validity checks. Warm-up, invalid heater/gas flags, I2C failure, and stale measurements remain explicitly unavailable or degraded.

## Node 2 — CSI, fusion, outputs, persistence, and MQTT

Node 2 joins the SoftAP, registers with Node 1, validates the packet contract, and enables ESP32-S3 CSI reception. The Wi-Fi callback only copies a fixed-size packet into a FreeRTOS queue. Lower-priority processing rejects invalid frames, converts interleaved I/Q to amplitude, retains 48 data carriers, and assembles 100-frame windows.

The default model adapter returns `UNKNOWN`: only a model with a passing release manifest may replace it. Deterministic fusion still handles sensor risk and health. Critical environmental risk produces `INCIDENT` regardless of CSI; warning produces `WARNING`; stale/unhealthy evidence produces `DEGRADED`; only healthy non-risk evidence produces `NORMAL`.

Node 2 maps the fused state to green/yellow/red LEDs and the buzzer. Each transition is written to a bounded NVS queue before MQTT QoS 1 publication. The record remains until the laptop returns an exact JSON ACK containing the same `event_id` and status `ACCEPTED`.

## Laptop review station

The laptop joins the Node 1 SoftAP and runs the MQTT broker, bridge, FastAPI service, SQLite database, and Streamlit dashboard. The API validates and timestamps telemetry, deduplicates `event_id`, stores the event durably, performs an independent server-side fusion check, exposes incidents, and returns the application ACK.

## Data path

```text
BME680 -I2C-> Node 1 ESP32-S3 -UDP probes + environment-> Node 2 ESP32-S3
                                                         |
                                         CSI window + deterministic fusion
                                         LEDs/buzzer + NVS queue
                                                         | MQTT QoS 1
                                                         v
                                             Laptop broker -> FastAPI -> SQLite
                                                         | exact ACK
                                                         +----------> Node 2
                                             Streamlit reads the local API
```

## Failure boundaries

- Sensor invalid/stale: `DEGRADED`; never silently normal.
- CSI stale, low confidence, or model disabled: human context `UNKNOWN` and overall `DEGRADED`, unless environmental risk is warning/critical.
- Critical environment plus missing CSI: still `INCIDENT`.
- Broker offline: records remain in the 16-slot NVS queue and retry later.
- Queue full or corrupt metadata: visible failure; software does not silently erase evidence.
- Laptop offline: local LEDs/buzzer and fusion continue, while telemetry queues.

Host-verification is complete. Target ESP32-S3 compilation and every electrical/radio behavior still require physical acceptance.
