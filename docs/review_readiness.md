# SafeSense Rubric Readiness

This document maps the review rubric to evidence that exists in the repository. “Software ready” means the implementation and host tests exist. It does not replace evidence recorded from the physical ESP32 and sensors.

## Readiness matrix

| Rubric item | Current status | Repository evidence | Still required at the review |
|---|---|---|---|
| Custom library implementation (5) | Software ready | Register-level BME280 protocol, calibration parsing, compensation and I2C adapter in `firmware/components/bme280/`; host reference-vector test in `firmware/tests/test_bme280_driver.c` | Connect the BME280, show chip ID `0x60`, display real temperature/pressure/humidity and unplug it to show an error |
| Local database / persistence (5) | Software ready | NVS-backed bounded queue in `firmware/components/delivery/delivery_queue.c`; environmental node logs restored record count at boot | With broker offline, persist a reading, reset the same board, show the restored count, reconnect and show the queue drain |
| Edge analytics / ML preprocessing (5) | Ready for this rubric | CSI I/Q → amplitude → exact 48 data carriers → 100-frame window in firmware and Python; invalid-first-word rejection; documented inference contract | Show a raw/rejected/accepted frame and a completed `100 × 48` window. Explain that the current INT8 candidate is rejected for accuracy and the firmware therefore returns `UNKNOWN` |
| Communication pipeline (5) | Software ready | Sensor JSON is persisted before MQTT QoS 1 publish; bridge posts to FastAPI; exact application ACK removes it; duplicate event IDs are idempotent | Configure a local broker and Wi-Fi, then show MQTT event, backend acceptance, ACK and dashboard update on the same live event |
| GUI / dashboard prototype (5) | Ready | Streamlit shows every reference field under Environment, Wi-Fi CSI, Human Context, System and Recent Events, plus optional CSI detail and incident acknowledgement | Run FastAPI, Streamlit and either the simulator or physical MQTT path |
| Individual contribution, presentation and Q&A (25) | Materials ready; human rehearsal pending | Demo order and Q&A below | Add real member names and owned files, rehearse without reading, and ensure each person can explain their implementation |

## Recommended demonstration order

1. Open `bme280_driver.c` and point out register reads, chip-ID verification, calibration registers and compensation. Show the host test, then show the real serial values.
2. Stop the MQTT broker. Wait for `Persisted reading; pending=1`, reset the ESP32 and show `Restored 1 pending telemetry record(s) from NVS`.
3. Start the broker and `scripts/mqtt_bridge.py`. Show the queued JSON event, the exact `ACCEPTED` ACK and the pending count draining.
4. Show one CSI frame becoming 48 amplitudes and then a `100 × 48` window. Corrupt `first_word_invalid` and show rejection.
5. Open the Streamlit dashboard and show state, environmental values, activity, link health, CSI plot and incident acknowledgement.
6. End with the honest ML boundary: preprocessing and an inference plan are complete, but the public-data model failed the real-room release gate and is intentionally not enabled.

## Commands for the laptop demo

```powershell
uvicorn safesense.main:app
streamlit run dashboard\app.py
python scripts\simulate_device.py
```

For MQTT, set `SAFESENSE_MQTT_BROKER` before running `python scripts\mqtt_bridge.py`. Configure the same URI, Wi-Fi and device ID in `firmware/environmental_node` with `idf.py menuconfig`.

Firmware build and flash commands are documented in `firmware/environmental_node/README.md`. The CSI transmitter and receiver also expose their Wi-Fi settings through `menuconfig` and now initialize their own network connection before sending or capturing packets.

## Individual contribution worksheet

Fill this before presenting; do not claim shared or generated work as one person’s independent contribution.

| Member | Owned implementation | Files they must explain | Failure case they will demonstrate |
|---|---|---|---|
| Member 1 | Custom driver | BME280 driver and ESP-IDF adapter | Missing sensor / wrong chip ID |
| Member 2 | Persistence and communication | Delivery queue, MQTT and bridge | Broker offline, reboot, retry and ACK |
| Member 3 | CSI / edge analytics | CSI capture, preprocessing and model gate | Invalid frame and uncertain inference |
| Member 4 | Backend and dashboard | FastAPI, SQLite and Streamlit | Duplicate event, API unavailable, incident ACK |

Adjust the rows to match the team’s actual work.

## High-probability Q&A

**What makes the driver custom?**  The project directly implements the BME280 register protocol, calibration decoding and compensation equations. ESP-IDF supplies only the generic I2C transport.

**What survives reboot?**  Each unacknowledged JSON record and queue metadata are committed to ESP32 NVS before publishing. Boot logs report the restored count.

**Why is MQTT QoS 1 not enough?**  QoS 1 confirms broker delivery, not successful backend storage. SafeSense waits for an application ACK containing the exact event ID and `ACCEPTED` status.

**How are duplicate messages handled?**  The stable `event_id` is unique in SQLite. Re-delivery returns the prior result instead of creating another telemetry event or incident.

**What happens when a gas sensor is absent?**  Risk is `UNAVAILABLE`, never silently `NORMAL`. Fusion becomes `DEGRADED`, while a real `CRITICAL` reading always creates an incident.

**What is CSI preprocessing?**  ESP32 CSI contains interleaved imaginary and real samples. The pipeline computes amplitude, retains the 48 non-pilot data carriers in physical payload order, rejects invalid first words and builds 100-frame windows.

**Is the ML model complete?**  The full INT8 pipeline and firmware runtime are implemented, but the candidate achieved only 0.326 macro-F1 on an unseen real room. It is correctly blocked by the 0.80 release gate. The rubric’s preprocessing and inference-plan requirement is ready; reliable deployment needs target-room data.

**What breaks first?**  With the current bounded design, prolonged broker outage fills the 16-record NVS queue. The node reports this explicitly; for the review, use low-frequency telemetry and restore connectivity before it fills.

## Physical evidence checklist

- [ ] Install ESP-IDF, build all three firmware applications and record the exact version/build result
- [ ] Board and BME280 visible in one uninterrupted video or live demonstration
- [ ] Chip ID and ten real readings recorded
- [ ] Sensor disconnect produces an unhealthy/error state
- [ ] NVS record shown before and after a physical reset
- [ ] MQTT event and matching ACK captured
- [ ] Same event visible in FastAPI/SQLite and Streamlit
- [ ] Every member’s contribution row replaced with truthful names and ownership
- [ ] Every member rehearsed the Q&A relevant to their files
