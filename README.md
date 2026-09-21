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

## Run the real MQTT path

The included broker configuration uses port `1884` because the standard Windows Mosquitto service may already own port `1883`. It allows anonymous access only for an isolated review network; do not expose it to a public or production network.

```powershell
& "C:\Program Files\mosquitto\mosquitto.exe" -c .\mosquitto-demo.conf -v
$env:SAFESENSE_MQTT_BROKER = "127.0.0.1"
$env:SAFESENSE_MQTT_PORT = "1884"
python scripts\mqtt_bridge.py
```

With the API, broker, and bridge running, verify the exact acknowledgement path:

```powershell
python scripts\mqtt_smoke_test.py
```

Before building Node 2 for the physical demo, join the laptop to the Node 1 SoftAP, obtain the laptop's `192.168.4.x` address with `ipconfig`, and set `SAFESENSE_MQTT_BROKER_URI` in `idf.py menuconfig` to `mqtt://<laptop-ip>:1884`. If Windows Firewall blocks the board, allow inbound TCP `1884` only for the private review network.

## Build and flash the two ESP32-S3 applications

ESP-IDF 6.1 is installed at `C:\Espressif\v6.1\esp-idf` on this workstation. Open an ESP-IDF shell, or initialize it from Command Prompt, then build each target:

```powershell
cmd /c "C:\Espressif\v6.1\esp-idf\export.bat && idf.py -C firmware\node1_sensor_tx build"
cmd /c "C:\Espressif\v6.1\esp-idf\export.bat && idf.py -C firmware\node2_csi_gateway build"
```

Connect one board at a time with a data-capable USB cable, replace `COMx` with its detected port, and flash/monitor the matching image:

```powershell
cmd /c "C:\Espressif\v6.1\esp-idf\export.bat && idf.py -C firmware\node1_sensor_tx -p COMx flash monitor"
cmd /c "C:\Espressif\v6.1\esp-idf\export.bat && idf.py -C firmware\node2_csi_gateway -p COMx flash monitor"
```

Exit the serial monitor with `Ctrl+]`. Do not flash Node 1 firmware onto the receiver board or Node 2 firmware onto the transmitter board.

## Verification

```powershell
python -m pytest -q
mingw32-make -C firmware/tests clean test
python -m compileall -q src scripts dashboard
```

Host tests verify the portable driver maths, gas policy, packet contract, CSI preprocessing, fusion, persistence semantics, API, MQTT acknowledgement, and dashboard contract. Both ESP-IDF 6.1 `esp32s3` applications compile successfully, and the laptop broker-to-bridge-to-API-to-ACK path has completed a real MQTT round trip. Flashing, physical BME680 readings, radio CSI, reboot persistence, LEDs/buzzer, and board-to-laptop MQTT remain explicit device gates because neither board is currently detected over USB.

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
