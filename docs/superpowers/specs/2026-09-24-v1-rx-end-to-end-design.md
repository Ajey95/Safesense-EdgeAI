# V1 RX and end-to-end evidence design

Date: 2026-09-24. Branch: `v1`. Scope: complete the already-approved
TX→RX HTTP path on the two connected classic ESP32 boards, then RX→local
FastAPI→dashboard. The user asked for completion without further questions.

## Network and data flow

The current laptop network is WPA2-Enterprise, while V1 ESP32 station code
supports open/WPA2-PSK only. RX therefore runs an isolated WPA2-PSK soft AP
at `192.168.4.1`; TX joins as a station. This keeps the approved HTTP JSON
transport without needing the campus credentials. The laptop temporarily
joins that AP and runs a local bridge which polls RX by HTTP, posts to the
existing FastAPI service on loopback, then acknowledges RX by HTTP. RX does
not need inbound access to a laptop firewall port.

TX POST `/api/v1/tx/environment` carries the existing version-1 bounded
JSON. RX checks content length, valid schema and event ID, and commits the
original JSON to its own `ssrx` NVS queue. Only then it returns HTTP 202 with
the exact `{"event_id":"...","status":"ACCEPTED"}` body expected by TX.
Duplicate pending event IDs receive the same ACK without a second queue
entry. Queue-full, malformed JSON and persistence failures receive non-2xx
responses; TX retains its copy. RX exposes the pending head to the bridge.
The bridge validates and converts the TX sensor envelope to backend telemetry,
posts it with the same event ID, checks backend acceptance and matching ID,
then ACKs RX so its NVS head can be removed. Replayed API requests are
idempotent. The first live correlation uses TX serial, RX serial, backend
SQLite and dashboard JSON; no self-reported field alone proves device origin.

RX enables CSI capture while its AP is receiving TX UDP probes. It counts
accepted/rejected frames and reports actual RSSI and packet rate when
available. The existing 100×48 preprocessing remains available, but its
unreleased activity model cannot claim `VACANT`/`WALKING`/`STATIONARY`;
activity stays `UNKNOWN` until a model passes its release gate.

## MQ-135 boundary

TX continues to publish GPIO34 ADC1 channel 6 raw samples through the
confirmed 10k/10k divider. The attached module has repeatedly yielded 0.
No software conversion of 0 to ppm, CO2, NORMAL or a working gas alarm is
permitted. The firmware/dashboard must call the channel uncalibrated and
unavailable; live diagnosis should distinguish ADC read errors from an
actual zero and document the needed VCC/AO/GND voltage checks. The sensor's
heater requires a 5 V supply under its manufacturer's standard circuit.

## Acceptance

Host tests cover RX event parsing/ACK contracts, duplicate/full-queue
behavior, bridge conversion, backend idempotence and unavailable sensors.
Both ESP-IDF targets must build. Live acceptance requires identified COM11
TX and COM12 RX, TX HTTP 202+matching ACK, RX persisted/rebooted event,
bridge backend 202, SQLite row and dashboard JSON with one matching event ID.
CSI and MQ are reported only at the evidence level actually achieved.
