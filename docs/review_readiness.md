# SafeSense Rubric Readiness

This document maps the review rubric to repository and live-board evidence recorded on 2026-09-24 on branch `v1`. Software and serial/browser checks do not prove analog voltages or model accuracy.

## Readiness matrix

| Rubric item | Current status | Repository evidence | Still required at the review |
|---|---|---|---|
| Custom library implementation (5) | Live BME680 driver verified | From-scratch BME680 register/compensation driver in `firmware/components/bme680/`; host reference-vector/calibration tests; live ID `0x61` and temperature, humidity, pressure, gas-resistance readings on TX | Show the custom-driver serial readings. Sensor-disconnect handling is host-tested but still needs a live demonstration. MQ-135 analog output is unverified at raw ADC 0. |
| Local database / persistence (5) | Live TX and RX NVS queues verified | `firmware/components/delivery/delivery_queue.c` commits before transmission; TX pending count survived reset, RX persisted before its application ACK, and matching queued event IDs drained through the bridge | Reproduce an outage/reboot on both boards in one uninterrupted review demo. One historical TX head blob was missing and could not be recovered; the other 15 records survived repair. |
| Edge analytics / ML preprocessing (5) | Live CSI windows; model unreleased | `firmware/components/csi/` computes amplitudes and 100-frame windows; live RX recorded 1,461 frames and 69 diagnostic windows. The classic ESP32 marked its first four CSI bytes invalid, so one affected carrier was zero-masked and 47 of 48 carriers were measured | Show the live counters and masking metadata, not a claim of 48 fully measured carriers. The candidate model failed its release gate; activity is `UNKNOWN`, not a reliable classification. |
| Communication pipeline (5) | Live end-to-end demonstrated | TX NVS → HTTP JSON POST → RX NVS and exact `ACCEPTED` ACK → laptop bridge → FastAPI/SQLite → Streamlit. TX/RX serial logs, bridge output and backend record matched event IDs; see `PROJECT_MEMORY.md` | Re-run the bounded demo for fresh proof. The laptop has one Wi-Fi adapter; its bridge is not continuously connected after Wi-Fi is restored. MQTT is an older V1 alternative, not this live link. |
| GUI / dashboard prototype (5) | Live-data desktop/mobile browser checked | V2 layout ported to V1. Streamlit displays stored JSON, matching event ID, RX-reported HTTP/NVS metadata, BME680 values, MQ raw ADC 0 warning, fresh CSI counters and `UNKNOWN` activity | Keep the exact-event JSON visible. Do not present RX metadata as cryptographic attestation or ADC zero as proof the MQ-135 works. |
| Individual contribution, presentation and Q&A (25) | Materials ready; human rehearsal pending | Demo order and Q&A below | Add real member names and owned files, rehearse without reading, and ensure each person can explain their implementation |

## Recommended demonstration order

1. Open `firmware/components/bme680/bme680_driver.c` and show chip-ID verification, calibration parsing and compensation. Run its host test and show TX live readings.
2. With RX unavailable, capture a `Persisted event` JSON line, reset TX and show its pending count restored from NVS.
3. Bring up RX, show TX HTTP POST, matching RX `ACCEPTED` ACK and queue drain. Run the laptop bridge and match the same event ID in FastAPI/SQLite and the dashboard's stored JSON.
4. Show live CSI diagnostic windows and the reported 47-measured/one-masked carrier caveat. Do not present a live activity inference.
5. Open the Streamlit dashboard and show BME680 values, MQ ADC-zero warning, CSI status, communication evidence and stored JSON for the matched event.
6. End with the honest ML boundary: preprocessing and an inference plan are complete, but the public-data model failed the real-room release gate and is intentionally not enabled.

## Commands for the laptop demo

```powershell
.\.venv\Scripts\python.exe -m uvicorn safesense.main:app --host 127.0.0.1 --port 8000
.\.venv\Scripts\python.exe -m streamlit run dashboard\app.py
```

Run these in separate terminals. With both boards flashed and powered, connect the laptop to `SafeSense-RX-V1` and run `.\.venv\Scripts\python.exe -m scripts.rx_http_bridge` to forward RX's pending queue. On a laptop with one Wi-Fi adapter, the bounded lab helper `scripts/run_rx_bridge_demo.ps1 -RestoreWifiProfile <profile-name>` temporarily switches Wi-Fi, forwards up to 22 records and restores the named profile. It is not an unattended service. Confirm the backend and dashboard are running first. Live dashboard values become stale after 15 seconds without a newly forwarded record; stored JSON remains available for inspection.

Current TX and RX build/flash commands and lab AP settings are in `firmware/node1_sensor_tx/README.md` and `firmware/node2_csi_gateway/README.md`. The older `environmental_node`/MQTT path is not this live demonstration.

## Individual contribution worksheet

Fill this before presenting; do not claim shared or generated work as one person’s independent contribution.

| Member | Owned implementation | Files they must explain | Failure case they will demonstrate |
|---|---|---|---|
| Member 1 | Custom driver | BME680 driver and ESP-IDF adapter | Missing sensor / wrong chip ID |
| Member 2 | Persistence and communication | Delivery queue, TX HTTP protocol and RX gateway | RX offline, reboot, retry and ACK |
| Member 3 | CSI / edge analytics | CSI capture, preprocessing and model gate | Invalid frame and uncertain inference |
| Member 4 | Backend and dashboard | FastAPI, SQLite and Streamlit | Duplicate event, API unavailable, incident ACK |

Adjust the rows to match the team’s actual work.

## High-probability Q&A

**What makes the driver custom?** The current TX directly implements the BME680 register protocol, calibration decoding and compensation equations. ESP-IDF supplies only generic I2C transport. The external library was used for a separate diagnostic cross-check, not the rubric driver.

**What survives reboot?**  Each unacknowledged JSON record and queue metadata are committed to ESP32 NVS before publishing. Boot logs report the restored count.

**Why HTTP plus an ACK?** The current TX-to-RX design uses HTTP JSON, which the rubric permits alongside MQTT/WebSocket. An HTTP transport success alone is insufficient: TX retains the NVS record until the RX response contains the exact event ID and `ACCEPTED` status. RX then retains its own record until the backend confirms the same ID.

**How are duplicate messages handled?**  The stable `event_id` is unique in SQLite. Re-delivery returns the prior result instead of creating another telemetry event or incident.

**What happens when a gas sensor is absent?**  Risk is `UNAVAILABLE`, never silently `NORMAL`. Fusion becomes `DEGRADED`, while a real `CRITICAL` reading always creates an incident.

**What is CSI preprocessing?** ESP32 CSI contains interleaved imaginary and real samples. The strict pipeline computes amplitudes for 48 non-pilot data carriers in physical payload order and rejects invalid first words. On this live classic ESP32, every captured frame flagged the first four bytes invalid, so a separate diagnostic path masks the one affected carrier, keeps 47 measured carriers in a 48-wide frame, and builds 100-frame windows. These diagnostic windows are not model inference.

**Is the ML model complete?**  The full INT8 pipeline and firmware runtime are implemented, but the candidate achieved only 0.326 macro-F1 on an unseen real room. It is correctly blocked by the 0.80 release gate. The rubric’s preprocessing and inference-plan requirement is ready; reliable deployment needs target-room data.

**What breaks first?** Prolonged RX/Wi-Fi outage fills TX's 16-record NVS queue, and a stopped laptop bridge fills RX's bounded queue. Both report failures rather than silently claiming delivery. The one-adapter laptop bridge also stops seeing RX after Wi-Fi returns to its ordinary network.

## Physical evidence checklist

- [x] ESP-IDF 6.1 TX build/COM11 flash and RX build/COM12 flash verified
- [ ] TX and RX boards and BME680 visible in one uninterrupted video or live demonstration
- [x] BME680 chip ID and ten real diagnostic readings recorded; custom-driver live readings also observed
- [ ] Sensor disconnect produces an unhealthy/error state
- [x] Corrected TX NVS record/pending count shown before and after reset
- [x] TX HTTP event and matching RX ACK captured in serial logs
- [x] Matching RX-forwarded event captured in FastAPI/SQLite and Streamlit JSON view
- [x] RX diagnostic CSI windows observed; 47 measured and one masked carrier disclosed
- [ ] MQ-135 VCC, AO, and GPIO34 divider voltage measured; ADC remains zero
- [ ] Every member’s contribution row replaced with truthful names and ownership
- [ ] Every member rehearsed the Q&A relevant to their files
