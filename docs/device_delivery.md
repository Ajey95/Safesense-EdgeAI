# Device Delivery and Environmental Risk

## Delivery path

Telemetry is serialized with a stable `event_id`, committed to the bounded NVS queue, published at MQTT QoS 1, and retained until a valid JSON ACK names that exact ID with status `ACCEPTED` on the device-specific ACK topic. A successful MQTT publish by itself does not remove the event. Substring matches and malformed ACKs are rejected.

`firmware/components/delivery` is designed for low-frequency incidents and state transitions. It must not be used to write raw CSI frames: NVS is suited to bounded key-value state, not high-rate logging.

Topics:

```text
safesense/{device_id}/event
safesense/{device_id}/ack
```

`scripts/mqtt_bridge.py` is the backend-side bridge. Configure the broker via `SAFESENSE_MQTT_BROKER`; do not commit a broker credential or certificate.

`firmware/environmental_node` wires the complete review path: custom BME280 driver → JSON serialization → NVS queue → MQTT. At boot it logs how many records were restored. For the persistence demonstration, stop the broker, wait for `Persisted reading`, reset the board, and show `Restored 1 pending telemetry record(s) from NVS`; reconnect the broker and show the backend ACK draining the record.

## Environmental-risk source

The custom BME280 driver measures temperature, humidity, and pressure. The added `gas_risk` component is a calibrated analog-sensor policy: it evaluates a signal relative to a stored baseline and warning/critical ratios. Until the actual gas/smoke module, board pin, warm-up procedure, and calibration values are chosen and measured, its output is deliberately `UNAVAILABLE`; it does not make fictional safety claims.

## Model boundary

`csi_pipeline` creates deterministic 100 x 48 windows. The model call is intentionally deferred until the trained and quantified INT8 artifact from the separate model-training task exists. Until then the application must publish activity `UNKNOWN`, not a fabricated class.
