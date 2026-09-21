# SafeSense

Software foundation for the SafeSense indoor safety prototype.

The current rubric-by-rubric status, physical evidence checklist and Q&A guide are in [docs/review_readiness.md](docs/review_readiness.md).

It accepts a device telemetry envelope, validates and stores it, derives a deterministic safety state, records incidents, and streams updates to a live dashboard. A simulator is included until the ESP32 nodes are available.

## Run locally

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
uvicorn safesense.main:app --reload
```

In a second terminal, with the virtual environment active, start the Streamlit dashboard:

```powershell
streamlit run dashboard\app.py
```

Open the URL printed by Streamlit (normally `http://localhost:8501`). In a third terminal:

```powershell
python scripts\simulate_device.py
```

For the CSI preprocessing/dashboard replay, use:

```powershell
$env:PYTHONPATH = "src"
python scripts\replay_csi.py
```

The replay generates deterministic ESP32-shaped 20 MHz LLTF frames, rejects invalid first words, retains the documented 48 usable data subcarriers, and forms 100-frame sliding windows. It is for software integration only, not evidence of real-world activity-recognition accuracy.

## ESP32 software components

- `firmware/components/csi`: non-blocking ESP-IDF CSI callback, 48-subcarrier amplitude processing, and 100 x 48 window construction.
- `firmware/components/delivery`: persistent NVS incident queue and MQTT QoS 1 delivery that removes an item only after application ACK.
- `firmware/components/gas_risk`: calibrated analog-signal risk policy. It remains `UNAVAILABLE` until actual sensor calibration data exists.
- `firmware/environmental_node`: review application wiring the custom BME280 driver to NVS persistence and MQTT delivery. Configure Wi-Fi, broker URI and device ID with `idf.py menuconfig`.

See [device delivery design](docs/device_delivery.md) for topic contracts and safety boundaries.

## Scope and verification boundary

This repository currently verifies the software pipeline using simulated, ESP32-shaped telemetry. It does not claim that CSI capture, BME280 register access, TinyML inference, MQTT delivery, or flash persistence work on physical hardware yet. Those are separate hardware acceptance gates.

## API contract

`POST /api/v1/telemetry` accepts one idempotent event at a time. The `event_id` must be stable across client retries. The full OpenAPI schema is available at `/docs` while running.

## Tests

```powershell
pytest
```
