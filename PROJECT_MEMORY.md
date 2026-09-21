# SafeSense Software Context

## Purpose

SafeSense is an indoor safety prototype that combines environmental readings, Wi-Fi CSI activity context, deterministic fusion, local persistence, telemetry delivery, and an operations dashboard.

## Current milestone

Starting from an empty repository on 2026-09-19. Hardware is not available yet, so the first deliverable is a software-complete vertical slice driven by a simulated ESP32-compatible telemetry producer.

The custom BME280 driver is implemented as a register-level ESP-IDF component with a transport abstraction and host-side test fixture. It remains pending physical-sensor acceptance testing.

Fusion is deterministic and implemented in portable C for the edge plus Python for the local service. It has four states: NORMAL, WARNING, INCIDENT, and DEGRADED. Critical environmental risk always opens an incident and cannot be vetoed by CSI. Stale/unknown/low-confidence CSI is DEGRADED, never VACANT. BME280 does not detect gas; environmental-risk classification must come from a separate calibrated sensor or the controlled simulator.

The CSI replay/preprocessing baseline is implemented in Python for 20 MHz ESP32 LLTF packets: reject `first_word_invalid`, use ESP32 I/Q ordering, retain the 48 usable 802.11a/g data subcarriers, then form 100-frame windows. It is an integration simulator, not a trained HAR model or physical validation result.

The Streamlit dashboard at `dashboard/app.py` is aligned to the review evidence without exposing setup or implementation instructions. It presents Environment (temperature, humidity, gas level, risk), Wi-Fi CSI (TX/RX state, RSSI, packet rate, quality), Human Context (activity and confidence), System (MQTT, local storage, ESP32), and Recent Events. Status fields are validated enums, dynamic text is HTML-escaped, absent evidence displays `UNKNOWN`/`UNAVAILABLE`, and dark/light plus desktop/mobile layouts were visually inspected. A simulator/replay can populate every review field, while physical firmware reports only states it can actually observe.

Dashboard UX prioritizes fused state, uses text plus color, preserves explicit degraded/error states, and uses an acknowledgement button rather than automatic incident resolution. UX research and the local-demo polling boundary are documented in `docs/dashboard_ux.md`.

Rubric items 2–4 are wired as a complete software path in `firmware/environmental_node`: custom BME280 reads are serialized as backend-compatible JSON, committed to a bounded NVS queue, restored after reboot, published with MQTT QoS 1, posted by the bridge, and removed only after an exact application ACK. Malformed, substring, fragmented, or non-accepted ACKs do not remove data. `UNAVAILABLE` is now a first-class environmental-risk state in Python and C fusion and fails closed to `DEGRADED`. The ESP-IDF application and physical reboot/MQTT evidence remain pending because neither the toolchain nor hardware is installed.

The rubric handoff is `docs/review_readiness.md`: it maps every mark to code evidence, gives the recommended live demonstration order, includes high-probability Q&A, and contains an individual-contribution worksheet. Actual member names, truthful ownership and rehearsal remain human tasks.

TinyML milestone (software-complete, model release blocked by evidence): training and firmware now use the same physical ESP32 carrier order, `(positive data carriers, then negative data carriers)`. Full-INT8 calibration is deterministic and balanced across all three classes. Training records both float and INT8 confusion matrices and quantization deltas. The TinyML CNN uses only two strided convolutions, mean, fully connected, and softmax; the candidate is 6,464 bytes and its largest inspected activation is 9,600 bytes. Firmware expects exactly the three product outputs (`vacant`, `stationary`, `walking`) and its two roughly 19 KB CSI buffers are in static memory rather than the 8 KB task stack.

The corrected real-plus-physics-synthetic corridor-to-lab experiment used 2,561 real plus 2,561 synthetic training windows and 2,090 untouched real lab test windows. Its INT8 accuracy is 0.311 and macro-F1 is 0.326 (float: 0.285/0.272). Calibration used 100 samples per class and the trace/hash leakage audit passed. Independent logistic and random-forest checks over temporal CSI statistics also failed to generalize (macro-F1 0.125 and 0.201), corroborating room/setup domain shift rather than a quantization-only defect. The candidate at `ml/models/safesense3_fixed_real_plus_synth/` remains rejected by the 0.80 macro-F1 gate and must not be converted into firmware release headers. Actual SafeSense-room/device collection is the remaining model-data gate. ESP-IDF/TFLM allocation and physical-device latency remain unverified because the toolchain and hardware are unavailable.

## Non-negotiable rules

- `UNKNOWN` activity is never equivalent to `VACANT`.
- Environmental danger remains actionable when CSI is stale, unavailable, or low confidence.
- Incident records need idempotency, timestamps, acknowledgement state, and persistence.
- Hardware-dependent claims remain unverified until tested on the actual devices.

## Initial architecture

One local FastAPI service, SQLite initialized from SQLAlchemy metadata, WebSocket dashboard fan-out, and Streamlit dashboard. ESP32 environmental firmware publishes the same validated telemetry envelope over MQTT through the local bridge. Formal versioned database migrations are not implemented and are outside the present review rubric.
