# V1 RX End-to-End Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a real, persisted TX→RX→local backend→dashboard path on the two classic ESP32 boards and diagnose MQ-135 without inventing a gas reading.

**Architecture:** RX soft AP accepts TX HTTP JSON and commits it to NVS before ACK. A laptop HTTP polling bridge posts that event to FastAPI and ACKs RX only after matching backend acceptance. CSI capture runs on RX; absent model and MQ signal remain unavailable.

**Tech Stack:** ESP-IDF 6.1, C, Python 3.12, FastAPI, Streamlit, SQLite, HTTP, NVS, Wi-Fi CSI.

**Spec:** `docs/superpowers/specs/2026-09-24-v1-rx-end-to-end-design.md`

## Global Constraints

- Stay on `v1`, preserve all existing dirty changes, and flash COM11 only after MAC `8c:94:df:90:1f:ec` and COM12 only after MAC `8c:94:df:90:dd:4c`.
- TX's custom BME680 library remains the production sensor driver.
- `gas_risk=UNAVAILABLE`, MQ raw ADC `0` is not ppm or a healthy gas signal, and CSI activity remains `UNKNOWN` without a released model.
- HTTP 202 and an exact event ID plus `ACCEPTED` ACK are required before TX drops an event; RX drops only after matching backend acceptance.
- Local demo AP credentials are not cloud credentials; generated `sdkconfig` remains ignored.

## Review Focus

- A malformed or oversized TX POST receives non-2xx and never enters RX NVS; test the parser and request-size gate.
- A duplicate pending event receives an ACK without a second NVS entry; test queue count and response.
- RX NVS full means TX keeps its head; test non-2xx and TX ACK rejection.
- Backend timeout, 422 or wrong event ID means bridge does not ACK RX; test these paths.
- Missing BME680 or zero MQ ADC stays unavailable in backend JSON/dashboard; test conversion and view.

---

### Task 1: RX contract and persistent HTTP server

**Files:** Create `firmware/components/rx_protocol/`, `firmware/node2_csi_gateway/` source and `firmware/tests/test_rx_protocol.c`; modify `firmware/tests/Makefile`.

**Interfaces:** `rx_parse_tx_event(json, length, out_event_id)` validates schema and event ID; RX returns exact 202 ACK after `delivery_queue_enqueue` in namespace `ssrx`. GET `/api/v1/pending` returns the queued head; POST `/api/v1/forward-ack` removes only a matching head.

- [ ] Write parser tests for valid TX JSON, malformed/trailing JSON, wrong schema, wrong ID, and >768 bytes. Run `mingw32-make -C firmware/tests test_rx_protocol` and observe RED.
- [ ] Implement the smallest portable parser and run the focused host test GREEN.
- [ ] Write tests for duplicate pending and mismatched ACK queue behavior; run RED, implement queue lookup and handler logic, run GREEN.
- [ ] Add RX soft AP, HTTP server and CSI callbacks; run `idf.py set-target esp32` and `idf.py build` in `firmware/node2_csi_gateway`.

### Task 2: Laptop bridge and backend receipt

**Files:** Create `scripts/rx_http_bridge.py`, `tests/test_rx_http_bridge.py`; modify `src/safesense/main.py`, `src/safesense/schemas.py`, `tests/test_api.py`, `src/safesense/dashboard_view.py`, `tests/test_dashboard_view.py`.

**Interfaces:** Bridge consumes RX pending JSON, yields a valid `TelemetryIn` with original event ID and observed sensor values, POSTs `/api/v1/telemetry`, checks response `event_id`, then POSTs RX ACK. Missing sensors map to `None` and degraded states, never 0 as a stand-in.

- [ ] Write conversion and backend-response tests for valid BME, missing BME, MQ raw zero, mismatch and backend failure; run `python -m pytest tests/test_rx_http_bridge.py tests/test_api.py -q` and observe RED.
- [ ] Implement bridge conversion, backend event-ID response and nullable unhealthy temperature; rerun GREEN.
- [ ] Write dashboard evidence tests that distinguish RX-reported HTTP receipt from cryptographic device proof; run RED, implement display, rerun GREEN.
- [ ] Run the full Python suite and verify no test fixture is labeled as physical-device proof.

### Task 3: Physical two-board acceptance and MQ diagnosis

**Files:** Modify local ignored `sdkconfig` for TX/RX and docs `PROJECT_MEMORY.md`, `docs/review_readiness.md`, RX/TX READMEs. No sensor calibration formula until voltage evidence exists.

**Interfaces:** RX soft AP `192.168.4.1`, TX destination `http://192.168.4.1/api/v1/tx/environment`, laptop bridge polls RX and posts local backend.

- [ ] Verify both MACs and COM ports; flash RX COM12 and final TX COM11 firmware, then capture RX AP and TX connection logs.
- [ ] Show TX POST+exact ACK and RX queued event with the same ID; reboot RX and verify pending record persists if backend not yet ACKed.
- [ ] Join the laptop to RX AP, run backend/bridge, and verify matching event ID in RX ACK, API SQLite row and dashboard JSON. If local network policy blocks this, record the exact gate without claiming end-to-end success.
- [ ] Capture MQ ADC status/raw samples and document the physical VCC/AO/GND voltage checks required for ADC `0`; do not claim calibration or normal air quality.
- [ ] Run all C and Python suites, both ESP32 builds, `git diff --check`, then report achieved and unverified gates precisely.
