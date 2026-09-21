# SafeSense project context

## Approved hardware and architecture

The project targets exactly one BME680, two ESP32-S3 boards, resistors, LEDs, and a buzzer.

- Node 1: BME680 custom I2C driver, relative gas policy, SoftAP, sensor LED, and 50 Hz protected environment/probe packets.
- Node 2: CSI capture and preprocessing, guarded TinyML adapter, deterministic fusion, three status LEDs, buzzer, NVS transition queue, and MQTT delivery.
- Laptop: broker, bridge, FastAPI, SQLite, and Streamlit.

## Safety invariants

- `UNKNOWN` is never equivalent to `VACANT`.
- Critical environmental risk remains `INCIDENT` even with stale or missing CSI.
- Missing/invalid evidence is `UNAVAILABLE` or `DEGRADED`, never fabricated zero or normal.
- BME680 gas resistance is not BSEC IAQ, gas identity, ppm, or certification.
- Records are persisted before publish and removed only by an exact accepted ACK for the same ID.
- The current INT8 candidate is release blocked; default firmware inference returns `UNKNOWN`.

## Verification snapshot — 2026-09-22

- Python: 25 tests passing.
- Portable C: 7 suites passing.
- Target builds: Node 1 and Node 2 compile for `esp32s3` with ESP-IDF 6.1; images are 781,520 and 899,840 bytes respectively.
- MQTT: local broker on port 1884 completed publish → bridge → API/SQLite → exact `ACCEPTED` ACK.
- Dashboard: live page inspected; software-generated telemetry is labelled `SOFTWARE TEST`, unavailable hardware stays `UNKNOWN`/`UNAVAILABLE`, the incident list is bounded, and no internal instructions are displayed.
- Physical flashing and device validation remain pending because no ESP32-S3 serial port is currently detected.

## Reviewer entry points

- `docs/review_readiness.md` — rubric evidence matrix.
- `docs/review_demo.md` — exact demonstration sequence.
- `docs/reviewer_qna.md` — technical Q&A.
- `docs/progress.md` — verified versus pending status.

Never store Wi-Fi, MQTT, GitHub, or other credentials in this file or the repository.
