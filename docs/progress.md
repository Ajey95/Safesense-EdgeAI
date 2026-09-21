# SafeSense implementation status

Status words are deliberate:

- **HOST VERIFIED:** portable logic or local service is covered by passing host tests.
- **TARGET BUILD VERIFIED:** the ESP-IDF application compiled successfully for `esp32s3`; this does not prove physical behavior.
- **PENDING DEVICE TEST:** electrical, radio, flash, reboot, or timing behavior needs the actual boards.
- **RELEASE BLOCKED:** an artifact exists but does not meet its evidence threshold.

| Area | Status | Evidence and remaining gate |
|---|---|---|
| Custom BME680 library | HOST VERIFIED / TARGET BUILD VERIFIED | Register protocol, `0x61` chip ID, calibration, compensation, heater maths, forced-mode adapter; physical reading accuracy pending |
| Relative gas policy | HOST VERIFIED | Warm-up, validity, EMA baseline, warning/critical ratios; target-room calibration pending |
| Node protocol | HOST VERIFIED | Fixed 50-byte big-endian packet, CRC32, version, sequence, freshness; real packet-loss/radio check pending |
| CSI preprocessing | HOST VERIFIED / TARGET BUILD VERIFIED | Invalid-frame rejection, I/Q amplitude, 48 carriers, 100 frames; physical ESP32-S3 CSI pending |
| TinyML | RELEASE BLOCKED | Full-INT8 tooling and guarded runtime exist; candidate macro-F1 0.326 is below the 0.80 gate |
| Fusion and outputs | HOST VERIFIED / TARGET BUILD VERIFIED | Critical precedence, `UNKNOWN != VACANT`, LED/buzzer mapping; GPIO polarity/timing pending |
| NVS persistence | HOST VERIFIED / TARGET BUILD VERIFIED | Portable reboot/duplicate/full/corrupt-store tests and ESP-IDF NVS adapter; physical reset pending |
| MQTT reliability | HOST VERIFIED / TARGET BUILD VERIFIED | Exact ACK parser plus a broker/bridge/API/ACK round trip on port 1884; board-to-broker integration pending |
| Backend/SQLite | HOST VERIFIED | Validation, idempotency, WAL/FULL sync, incidents, acknowledgement |
| Dashboard | HOST VERIFIED | Contract tests plus dark/light desktop and 390 × 844 visual inspection; live hardware feed pending |

## Current automated proof

- 23 Python tests pass.
- 7 portable C suites pass.
- Python source bytecode compilation passes.
- Both applications build successfully for ESP32-S3 with ESP-IDF 6.1.
- A real local MQTT publish completed bridge ingestion, durable API storage, and the exact application ACK.
- The live dashboard was inspected in a real browser and truthfully showed unavailable CSI/model evidence.

## Remaining physical acceptance

1. Flash both boards and verify BME680 address, chip ID, readings, heater flags, and disconnect state.
2. Confirm Node 1 UDP rate/CRC and Node 2 physical CSI windows.
3. Confirm green/yellow/red LED polarity and active/passive buzzer configuration.
4. Demonstrate queued event survival across a physical reset and exact ACK drain through the broker.
5. Collect target-room CSI and pass the model release gate before enabling INT8 inference.
