# SafeSense rubric readiness

This matrix maps every rubric mark to code, automated proof, and one concise demonstration. It does not convert host proof into hardware proof.

| Rubric item | Status | Code and test evidence | Live review demonstration |
|---|---|---|---|
| Custom library implementation (5) | HOST + TARGET BUILD VERIFIED; device pending | `firmware/components/bme680/`; `firmware/tests/test_bme680_driver.c`; Node 1 ESP-IDF 6.1 build | Open register/calibration/compensation code; run C suite; when hardware arrives show chip ID `0x61`, live values, and disconnect error |
| Local database / persistence (5) | HOST VERIFIED; device pending | `firmware/components/delivery/`; `test_delivery_queue.c`; SQLite WAL/FULL persistence | Run queue tests; on hardware queue with broker offline, reboot, show restore, then ACK drain |
| Edge analytics / ML preprocessing (5) | HOST VERIFIED; model release blocked | `firmware/components/csi/`; `test_csi_gas.c`; `tests/test_csi.py`; release helpers | Show rejected invalid frame, 48 amplitudes, and a `100 × 48` window; explain why the model returns `UNKNOWN` |
| Communication pipeline (5) | HOST + TARGET BUILD VERIFIED; device pending | Node protocol, MQTT bridge, exact ACK parser, API idempotency; protocol/ACK/API tests; real local MQTT round trip | Publish an event, show SQLite/dashboard result and exact ACK; on hardware show MQTT retry after outage |
| GUI / dashboard prototype (5) | HOST VERIFIED | `dashboard/app.py`, `dashboard_view.py`, `test_dashboard_contract.py`; browser QA | Open dashboard and walk Environment, CSI, Human Context, System, Review Evidence, Events, and acknowledgement |
| Contribution, presentation, Q&A (25) | Materials ready; team action required | `review_demo.md`, `reviewer_qna.md`, this matrix | Each member truthfully names owned files, explains one design choice, and demonstrates one failure case |

## Review-safe claims

- The BME680 driver and portable algorithms are independently implemented and host tested.
- The two ESP32-S3 target applications build successfully with ESP-IDF 6.1.
- The dashboard/backend software path is live and testable using the simulator.
- Physical flashing, electrical behavior, CSI radio behavior, and reboot proof are pending until the boards are connected over USB.
- The INT8 candidate exists but is not released; firmware correctly reports `UNKNOWN`.

Do not claim BSEC IAQ, calibrated ppm, production safety certification, physical validation, or a released HAR model.

## Contribution worksheet

Replace the role labels with the real team before presenting. Preserve honest ownership.

| Member | Owned implementation | Files they can explain | Failure case to demonstrate |
|---|---|---|---|
| Member 1 | Custom BME680 path | driver, adapter, gas policy | missing sensor / invalid gas flag |
| Member 2 | CSI and fusion | capture, preprocessing, model gate, fusion | invalid frame / stale CSI |
| Member 3 | Persistence and communication | queue, NVS, MQTT, bridge | broker outage / wrong ACK / reboot |
| Member 4 | Backend and dashboard | schemas, database, API, Streamlit | duplicate event / API unavailable / incident ACK |

Detailed presentation steps are in [review_demo.md](review_demo.md); likely questions are answered in [reviewer_qna.md](reviewer_qna.md).
