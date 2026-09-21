# SafeSense Implementation Progress

This page separates host-verified software from physical-hardware and model-release evidence.

| Area | Status | Evidence / remaining gate |
|---|---|---|
| System architecture | Implemented | Two ESP32 applications, reusable edge components, local backend and dashboard are present. |
| Custom environmental driver | Host verified | Register-level BME280 driver passes a Bosch reference-vector test; physical sensor acceptance remains. |
| Local flash persistence | Implemented | NVS queue restores pending records and removes them only after application ACK; physical reboot demonstration remains. |
| CSI TX/RX path | Implemented | Reconnecting Wi-Fi station, controlled UDP transmitter, non-blocking CSI callback and queue exist; physical radio validation remains. |
| CSI preprocessing | Host verified | Invalid-first-word rejection, I/Q amplitude, 48-carrier physical order and 100-frame windows are tested. |
| TinyML model pipeline | Implemented but release rejected | Full INT8 candidate is 6,464 bytes, but unseen-room macro-F1 is 0.326 versus the 0.80 release gate. Target-room data is required. |
| Fusion | Host verified | C and Python implementations fail closed; critical environmental risk cannot be vetoed by uncertain CSI. |
| MQTT delivery | Implemented | Persistent JSON, QoS 1, exact application ACK and retry behavior are wired; broker/device integration remains to be demonstrated physically. |
| Backend lifecycle | Host verified | Pydantic validation, idempotent ingestion, SQLite persistence, incidents, acknowledgement and WebSocket fan-out are tested. |
| Dashboard | Verified locally | Streamlit displays all rubric-facing telemetry and system states with honest unavailable/unknown values. |
| Controlled end-to-end validation | Pending hardware | Requires ESP-IDF build, flashing, BME280 measurements, reset persistence, CSI capture, MQTT delivery and target-room testing. |

## Current proof

- Thirteen Python tests and three portable C suites pass.
- Generated databases, datasets, model candidates, firmware builds and credentials are excluded from Git.
- The public-data model is retained only as an evaluated candidate and is not packaged into firmware.
- Review evidence, demo sequence and Q&A are documented in [review_readiness.md](review_readiness.md).

## Next physical milestones

1. Install ESP-IDF and compile all three firmware applications.
2. Validate BME280 chip ID, readings and disconnect behavior on the chosen board.
3. Demonstrate NVS persistence across a physical reset with the broker offline.
4. Capture MQTT publish, backend acceptance, exact ACK and queue drain.
5. Validate CSI capture from the fixed TX/RX geometry.
6. Collect a trace-separated target-room dataset and retrain before enabling TFLite Micro.
