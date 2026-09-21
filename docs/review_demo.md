# SafeSense review demonstration

## Before the review

Use three PowerShell terminals from the repository root. Install once:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

Terminal 1 — API:

```powershell
python -m uvicorn safesense.main:app --host 127.0.0.1 --port 8000
```

Terminal 2 — dashboard:

```powershell
python -m streamlit run dashboard\app.py --server.port 8501
```

Terminal 3 — simulated two-node telemetry:

```powershell
python scripts\simulate_device.py
```

Open `http://127.0.0.1:8501`. Run verification before presenting:

```powershell
python -m pytest -q
mingw32-make -C firmware/tests clean test
```

## Eight-minute presentation order

### 1. Problem and topology — 45 seconds

Show `architecture.svg`. State the real inventory: one BME680, two ESP32-S3 boards, resistors, LEDs, buzzer, and a laptop. Node 1 senses and creates CSI traffic; Node 2 captures CSI, fuses risk, drives local outputs, persists transitions, and reports them.

### 2. Custom BME680 library — 75 seconds

Open `firmware/components/bme680/bme680_driver.c` and point to:

- chip ID `0x61` validation;
- factory calibration decoding;
- temperature/pressure/humidity/gas compensation;
- heater resistance and duration calculation;
- transport abstraction that keeps sensor logic independent of ESP-IDF.

Run the portable C suite. Say clearly: host maths is verified; physical I2C/heater accuracy is pending. Do not describe gas resistance as ppm or certified IAQ.

### 3. Persistence and communication — 75 seconds

Open `delivery_queue.c`, `delivery_ack.c`, and the Node 2 log path. Explain:

1. state transition is written to NVS;
2. MQTT QoS 1 publishes it;
3. backend validates and durably stores it;
4. only an exact `ACCEPTED` ACK for that `event_id` removes it;
5. duplicate delivery is safe because the API is idempotent.

Run `test_delivery_queue`. With hardware, additionally demonstrate broker offline → queue depth one → board reset → restored one → broker online → exact ACK → queue zero.

### 4. Edge preprocessing and inference plan — 75 seconds

Open the CSI component. Trace callback copy/queue → invalid-first-word rejection → I/Q amplitude → 48 selected carriers → 100-frame window. Show the C/Python tests. Explain that the current INT8 candidate failed the unseen-room macro-F1 gate, so the safe stub returns `UNKNOWN`. This is a deliberate release control, not a hidden success claim.

### 5. Fusion and physical outputs — 60 seconds

Show the decision table in `fusion_design.md`. Demonstrate:

- critical environment + unknown CSI → `INCIDENT`;
- stale sensor → `DEGRADED`;
- stale CSI → `DEGRADED`, not `VACANT`;
- state maps to LED/buzzer patterns.

### 6. Dashboard — 90 seconds

Walk the screen in order:

1. overall state;
2. Environment, including gas resistance, baseline, ratio, validity, and freshness;
3. Human Context and CSI quality/window/model release;
4. System connectivity, two nodes, LED/buzzer, NVS depth, and drops;
5. Review Evidence boundary;
6. Recent Events and incident acknowledgement.

Point out `PENDING DEVICE TEST`. The dashboard intentionally contains operational evidence only—not setup notes, secrets, or development instructions.

### 7. Close — 30 seconds

Summarize what is host verified and what must wait for the hardware: ESP-IDF compilation, real readings, CSI capture, GPIO polarity, physical reset persistence, broker delivery, and target-room model evidence.

## Physical acceptance checklist

- [ ] Record ESP-IDF version and successful builds of both applications.
- [ ] Show both ESP32-S3 boards and BME680 in one uninterrupted demo.
- [ ] Verify chip ID, stable readings, gas-valid/heater-stable flags, and disconnect handling.
- [ ] Verify UDP rate/CRC and real CSI window formation.
- [ ] Verify every LED and buzzer state/polarity.
- [ ] Demonstrate NVS survival across reset and exact MQTT ACK drain.
- [ ] Confirm the same event in serial log, SQLite/API, and dashboard.
- [ ] Collect target-room CSI and pass the model gate before enabling INT8.
