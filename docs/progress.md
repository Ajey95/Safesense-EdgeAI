# SafeSense implementation status

Status words are deliberate:

- **HOST VERIFIED:** portable logic or local service is covered by passing host tests.
- **TARGET BUILD VERIFIED:** the ESP-IDF application compiled successfully for `esp32s3`; this does not prove physical behavior.
- **PENDING DEVICE TEST:** electrical, radio, flash, reboot, or timing behavior needs the actual boards.
- **RELEASE BLOCKED:** an artifact exists but does not meet its evidence threshold.

| Area | Status | Evidence and remaining gate |
|---|---|---|
| Custom BME680 library | HOST VERIFIED / TARGET BUILD VERIFIED / DEVICE BLOCKED | Register protocol, `0x61` chip ID, calibration, compensation, heater maths, forced-mode adapter and `0x76`/`0x77` detection; Node 1 currently receives no I2C acknowledgement on GPIO 8/9 |
| Relative gas policy | HOST VERIFIED | Warm-up, validity, EMA baseline, warning/critical ratios; target-room calibration pending |
| Node protocol | HOST VERIFIED | Fixed 50-byte big-endian packet, CRC32, version, sequence, freshness; real packet-loss/radio check pending |
| CSI preprocessing | HOST VERIFIED / TARGET BUILD VERIFIED | Invalid-frame rejection, I/Q amplitude, 48 carriers, 100 frames; physical ESP32-S3 CSI pending |
| TinyML | RELEASE BLOCKED | Full-INT8 tooling and guarded runtime exist; candidate macro-F1 0.326 is below the 0.80 gate |
| Fusion and outputs | HOST VERIFIED / TARGET BUILD VERIFIED | Critical precedence, `UNKNOWN != VACANT`, LED/buzzer mapping; GPIO polarity/timing pending |
| NVS persistence | HOST VERIFIED / TARGET BUILD VERIFIED | Portable reboot/duplicate/full/corrupt-store tests and ESP-IDF NVS adapter; physical reset pending |
| MQTT reliability | HOST VERIFIED / TARGET BUILD VERIFIED | Exact ACK parser plus a broker/bridge/API/ACK round trip on port 1884; board-to-broker integration pending |
| Backend/SQLite | HOST VERIFIED | Validation, idempotency, WAL/FULL sync, incidents, acknowledgement |
| Dashboard | HOST VERIFIED | Contract and browser checks; software-test provenance and bounded incident list verified; live hardware feed pending |

## Current automated proof

- 25 Python tests pass.
- 7 portable C suites pass.
- Python source bytecode compilation passes.
- Both applications build successfully for ESP32-S3 with ESP-IDF 6.1.
- A real local MQTT publish completed bridge ingestion, durable API storage, and the exact application ACK.
- The live dashboard was inspected in a real browser and truthfully showed `SOFTWARE TEST`, unavailable sensors/CSI, unknown nodes, and no fabricated hardware incident.

## Remaining physical acceptance

1. Correct the BME680 power/I2C wiring and verify chip ID, readings, heater flags, and disconnect state on the already-flashed Node 1.
2. Flash Node 2 and confirm Node 1 UDP rate/CRC plus physical CSI windows.
3. Confirm green/yellow/red LED polarity and active/passive buzzer configuration.
4. Demonstrate queued event survival across a physical reset and exact ACK drain through the broker.
5. Collect target-room CSI and pass the model release gate before enabling INT8 inference.
