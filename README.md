# SafeSense EdgeAI

> **Review-ready software for one BME680 and two ESP32-S3 boards; physical acceptance is pending.**

SafeSense combines BME680 environmental sensing, Wi-Fi CSI human context, deterministic safety fusion, persistent delivery, a local FastAPI/SQLite service, and a Streamlit review dashboard. It fails closed: `UNKNOWN` activity is never treated as `VACANT`, and a critical environmental reading remains an incident even when CSI is unavailable.

![SafeSense two-node architecture](docs/architecture.svg)

## Actual hardware topology

- **Node 1 — ESP32-S3 + BME680:** custom register-level I2C driver, relative gas-resistance policy, status LED, SoftAP, and 50 Hz versioned/CRC-protected UDP probes.
- **Node 2 — ESP32-S3 gateway:** CSI capture, 100 × 48 preprocessing, release-gated TinyML inference, deterministic fusion, green/yellow/red LEDs, buzzer, 16-record NVS queue, and MQTT QoS 1 delivery.
- **Laptop:** local MQTT broker, FastAPI, SQLite, Streamlit, and exact application acknowledgement.

The BME680 gas channel reports gas resistance. SafeSense does **not** claim Bosch BSEC IAQ or a certified gas concentration. Warning and critical states are relative to a warmed clean-air baseline and must be calibrated in the target room.

## Implemented software

- Independent BME680 register protocol, chip-ID check (`0x61`), calibration parsing, temperature/pressure/humidity/gas compensation, heater calculation, and ESP-IDF I2C adapter.
- Sensor validity/warm-up handling and an EMA gas baseline that is updated only by normal samples.
- Versioned network-order Node 1-to-Node 2 packet with CRC32, freshness, and sequence validation.
- ESP32-S3 CSI callback offload, invalid-frame rejection, I/Q amplitude, 48 data carriers, and 100-frame windows.
- Fail-closed fusion and local LED/buzzer state mapping.
- NVS persistence before publish; records are removed only after an exact `ACCEPTED` ACK for the same `event_id`.
- FastAPI validation, idempotent SQLite storage, incidents, acknowledgement, and Streamlit review dashboard.
- Full-INT8 training/conversion pipeline. The current candidate is intentionally disabled because it failed the unseen-room release threshold.

## Run the review software

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python -m uvicorn safesense.main:app --host 127.0.0.1 --port 8000
```

In a second terminal:

```powershell
python -m streamlit run dashboard\app.py --server.port 8501
```

In a third terminal:

```powershell
python scripts\simulate_device.py
```

Open `http://127.0.0.1:8501`. See [the review runbook](docs/review_demo.md) for the mark-by-mark demonstration and [reviewer Q&A](docs/reviewer_qna.md) for presentation preparation.

## Verification

```powershell
python -m pytest -q
mingw32-make -C firmware/tests clean test
python -m compileall -q src scripts dashboard
```

Host tests verify the portable driver maths, gas policy, packet contract, CSI preprocessing, fusion, persistence semantics, API, MQTT acknowledgement, and dashboard contract. ESP-IDF compilation, flashing, physical BME680 readings, radio CSI, reboot persistence, LEDs/buzzer, and end-to-end MQTT remain explicit device gates because the hardware/toolchain is not available in this environment.

## Repository map

```text
firmware/node1_sensor_tx/       ESP32-S3 + BME680 + SoftAP/probe transmitter
firmware/node2_csi_gateway/     ESP32-S3 CSI/fusion/output/NVS/MQTT gateway
firmware/components/bme680/     Custom BME680 driver and ESP-IDF adapter
firmware/components/            CSI, fusion, delivery, protocol and output components
src/safesense/                  FastAPI, SQLite and dashboard view model
dashboard/                      Streamlit review dashboard
ml/                             Training, INT8 conversion and release gates
tests/                          Python verification
firmware/tests/                 Portable C verification
docs/                           Architecture and review handoff
```

SafeSense is an academic prototype, not a certified life-safety or air-quality system.
