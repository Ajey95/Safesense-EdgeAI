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
| Node protocol | HOST VERIFIED / DEVICE VERIFIED | Fixed 50-byte big-endian packet, CRC32, version, freshness, duplicate rejection, and safe sequence-epoch reset after a transmitter reboot; two-board 50 Hz UDP path verified |
| CSI preprocessing | HOST VERIFIED / TARGET BUILD VERIFIED / DEVICE VERIFIED | Invalid-frame rejection, I/Q amplitude, 48 carriers, 100 frames; receiver produced physical ready windows at about 50 packets/s |
| TinyML | RELEASE BLOCKED | Full-INT8 tooling and guarded runtime exist; candidate macro-F1 0.326 is below the 0.80 gate |
| Fusion and outputs | HOST VERIFIED / TARGET BUILD VERIFIED | Critical precedence, `UNKNOWN != VACANT`, LED/buzzer mapping; GPIO polarity/timing pending |
| NVS persistence | HOST VERIFIED / TARGET BUILD VERIFIED | Portable reboot/duplicate/full/corrupt-store tests and ESP-IDF NVS adapter; physical reset pending |
| MQTT reliability | HOST VERIFIED / TARGET BUILD VERIFIED / DEVICE VERIFIED | Receiver waits for the ACK subscription, permits one in-flight record, retries an unacknowledged head after 5 seconds, and drains only an exact application ACK; physical receiver → broker → bridge → API → ACK flow verified on port 1884 |
| Backend/SQLite | HOST VERIFIED | Validation, idempotency, WAL/FULL sync, incidents, acknowledgement |
| Dashboard | HOST VERIFIED / LIVE FEED VERIFIED | Contract and browser checks; provenance and bounded incident list verified; physical receiver telemetry reached the API with MQTT connected, CSI ready, about 50 packets/s, and truthful `UNKNOWN` activity while the model remains blocked |

## Current automated proof

- 28 Python tests pass.
- 9 portable C suites pass.
- Python source bytecode compilation passes.
- Both applications build successfully for ESP32-S3 with ESP-IDF 6.1.
- A real local MQTT publish completed bridge ingestion, durable API storage, and the exact application ACK.
- Physical receiver records completed the same durable path, and MQTT stayed connected for more than two minutes.
- The receiver emits a 5-second live heartbeat while connected and republishes the persisted head if an application ACK is lost.
- The transmitter's current firmware suppresses repeated registration-token logs; its flash hash was verified on the physical ESP32-S3.
- The live dashboard was inspected in a real browser and truthfully showed `SOFTWARE TEST`, unavailable sensors/CSI, unknown nodes, and no fabricated hardware incident.

## Remaining physical acceptance

1. Correct the BME680 power/I2C wiring and verify chip ID, readings, heater flags, and disconnect state on the already-flashed Node 1.
2. Reconnect the receiver's USB port and flash the already-built sequence-epoch recovery image; the receiver is currently reachable over Wi-Fi but absent from Windows serial enumeration.
3. Confirm green/yellow/red LED polarity and active/passive buzzer configuration.
4. Demonstrate queued event survival across a physical receiver reset; exact ACK drain without a reset is already device verified.
5. Collect target-room CSI and pass the model release gate before enabling INT8 inference.
