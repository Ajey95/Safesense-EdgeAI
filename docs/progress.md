# SafeSense implementation status

Status words are deliberate:

- **HOST VERIFIED:** portable logic or local service is covered by passing host tests.
- **SOURCE COMPLETE:** target source exists, but the ESP-IDF toolchain was not available for compilation.
- **PENDING DEVICE TEST:** electrical, radio, flash, reboot, or timing behavior needs the actual boards.
- **RELEASE BLOCKED:** an artifact exists but does not meet its evidence threshold.

| Area | Status | Evidence and remaining gate |
|---|---|---|
| Custom BME680 library | HOST VERIFIED / SOURCE COMPLETE | Register protocol, `0x61` chip ID, calibration, compensation, heater maths, forced-mode adapter; physical reading accuracy pending |
| Relative gas policy | HOST VERIFIED | Warm-up, validity, EMA baseline, warning/critical ratios; target-room calibration pending |
| Node protocol | HOST VERIFIED | Fixed 50-byte big-endian packet, CRC32, version, sequence, freshness; real packet-loss/radio check pending |
| CSI preprocessing | HOST VERIFIED / SOURCE COMPLETE | Invalid-frame rejection, I/Q amplitude, 48 carriers, 100 frames; physical ESP32-S3 CSI pending |
| TinyML | RELEASE BLOCKED | Full-INT8 tooling and guarded runtime exist; candidate macro-F1 0.326 is below the 0.80 gate |
| Fusion and outputs | HOST VERIFIED / SOURCE COMPLETE | Critical precedence, `UNKNOWN != VACANT`, LED/buzzer mapping; GPIO polarity/timing pending |
| NVS persistence | HOST VERIFIED / SOURCE COMPLETE | Portable reboot/duplicate/full/corrupt-store tests and ESP-IDF NVS adapter; physical reset pending |
| MQTT reliability | HOST VERIFIED / SOURCE COMPLETE | Exact ACK parser and API/bridge contract; physical broker integration pending |
| Backend/SQLite | HOST VERIFIED | Validation, idempotency, WAL/FULL sync, incidents, acknowledgement |
| Dashboard | HOST VERIFIED | Contract tests plus dark/light desktop and 390 × 844 visual inspection; live hardware feed pending |

## Current automated proof

- 21 Python tests pass.
- 7 portable C suites pass.
- Python source bytecode compilation passes.
- Dashboard interaction, narrow/desktop layout, light/dark themes, and console output were inspected in a real browser.

## Remaining physical acceptance

1. Install a supported ESP-IDF version and compile both `esp32s3` applications.
2. Flash both boards and verify BME680 address, chip ID, readings, heater flags, and disconnect state.
3. Confirm Node 1 UDP rate/CRC and Node 2 physical CSI windows.
4. Confirm green/yellow/red LED polarity and active/passive buzzer configuration.
5. Demonstrate queued event survival across a physical reset and exact ACK drain through the broker.
6. Collect target-room CSI and pass the model release gate before enabling INT8 inference.
