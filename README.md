# SafeSense EdgeAI

> **Status: software-complete academic Edge AI / IoT prototype; hardware validation pending**

SafeSense combines environmental sensing, Wi-Fi CSI activity context, deterministic safety fusion, persistent ESP32 delivery, a local FastAPI backend, and a Streamlit operations dashboard. The design is privacy-oriented and fail-closed: uncertain CSI is never treated as proof that a room is vacant, and environmental danger cannot be suppressed by the ML result.

## Architecture

![SafeSense architecture](docs/architecture.svg)

More detail: [architecture](docs/architecture.md), [implementation progress](docs/progress.md), and [review readiness](docs/review_readiness.md).

## Implemented software

- Custom register-level BME280 I2C driver with factory-calibration decoding and compensation equations.
- ESP32 NVS telemetry queue with restore-after-reboot behavior.
- MQTT QoS 1 delivery retained until an exact backend `ACCEPTED` acknowledgement.
- ESP32 CSI capture and preprocessing: I/Q amplitude, 48 data carriers, invalid-frame rejection, and 100-frame windows.
- Deterministic edge and backend fusion with explicit `UNKNOWN`, `UNAVAILABLE`, and `DEGRADED` behavior.
- FastAPI ingestion, validation, idempotency, SQLite persistence, incidents, acknowledgement, and WebSocket fan-out.
- Streamlit dashboard covering Environment, Wi-Fi CSI, Human Context, System health, and Recent Events.
- Fully INT8 TinyML conversion and guarded TFLite Micro runtime. The current public-data candidate remains rejected by the accuracy gate and is not enabled in firmware.

## Run locally

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
uvicorn safesense.main:app --reload
```

In a second terminal:

```powershell
streamlit run dashboard\app.py
```

In a third terminal, use either the general telemetry simulator or CSI replay:

```powershell
python scripts\simulate_device.py

$env:PYTHONPATH = "src"
python scripts\replay_csi.py
```

## Repository structure

```text
dashboard/                    Streamlit review dashboard
docs/                         Architecture, safety and review evidence
firmware/components/          Reusable ESP-IDF drivers and edge components
firmware/environmental_node/  BME280 → NVS → MQTT application
firmware/csi_transmitter/     Controlled Wi-Fi CSI traffic source
firmware/csi_receiver/        CSI capture, preprocessing and guarded inference
ml/                           Preprocessing, augmentation, training and release gates
scripts/                      Simulator, CSI replay and MQTT bridge
src/safesense/                FastAPI, SQLite, fusion and realtime backend
tests/                        Python tests
```

## Verification

```powershell
pytest
mingw32-make -C firmware/tests test
```

Host verification covers the custom driver, CSI preprocessing, fusion, API behavior, synthetic augmentation, representative INT8 calibration, and dashboard startup. ESP-IDF compilation and physical sensor/radio/reboot evidence require the target toolchain and hardware.

## Scope

SafeSense is a student prototype, not a certified safety system. Sensor thresholds, physical ESP32 behavior, RF inference accuracy, false-positive/false-negative rates, and alert behavior require controlled target-room validation before real-world safety-critical use.
