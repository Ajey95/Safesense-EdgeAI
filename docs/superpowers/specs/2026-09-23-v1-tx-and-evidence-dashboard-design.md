# V1 TX and evidence dashboard design

Date: 2026-09-23
Branch: `v1`
Status: design for user review; no implementation claim

## Intent and success criteria

Finish the classic-ESP32 sensor/TX side with the connected BME680 and MQ-135,
using a custom sensor driver, then adapt the updated V2 dashboard into V1 to
show real stored JSON and honest communication evidence. RX implementation is
a subsequent phase. The rubric calls for a custom I2C driver without an
external sensor library, persistent local logging, edge preprocessing, a
functional MQTT/HTTP/WebSocket JSON pipeline with reliability, and a dashboard.
It does not mandate MQTT specifically.

TX is complete when the production firmware builds for classic ESP32, runs on
the actual TX board, reads all four BME680 channels plus MQ-135 ADC, persists
pending messages across reboot, and receives exact application ACKs from a
test HTTP endpoint. The eventual two-board TX-to-RX path remains unverified
until RX is implemented and tested with TX. Dashboard completion means the UI
shows backend-stored data, not hard-coded review claims, and accurately names
which communication hop was observed.

## Approach and boundaries

Use a dedicated `firmware/node1_sensor_tx` ESP-IDF application on V1. This
keeps the existing `firmware/environmental_node` MQTT review prototype intact
and avoids overwriting user changes. Port the repository's own register-level
`firmware/components/bme680` implementation from branch
`v2-bme680-esp32s3` into V1, adapting its ESP-IDF I2C adapter and build for
classic ESP32/ESP-IDF 6.1. Do not link the external `esp-idf-lib/bme680`
diagnostic dependency into production TX firmware. The diagnostic remains a
hardware cross-check only.

TX samples BME680 at the observed I2C address `0x76` on SDA GPIO21/SCL
GPIO22. It samples MQ-135 AO through the confirmed 10 kΩ/10 kΩ divider into
GPIO34 (ADC1 channel 6). The firmware records raw ADC, not ppm, CO₂, or a
certified hazard level. BME680 gas resistance is recorded in ohms; a zero or
invalid/warming sample is unavailable rather than a valid gas reading. Until
measured baselines and thresholds are configured and validated, `gas_risk`
remains `UNAVAILABLE`; a raw value never silently becomes `NORMAL`.

TX uses the existing Wi-Fi infrastructure to send two distinct streams:

1. Low-rate versioned JSON sensor messages by HTTP POST to the future RX
   endpoint. A stable `event_id` and sequence number survive retry/reboot.
   TX first commits each message to its bounded NVS queue and removes it only
   when the HTTP response body names the exact `event_id` with status
   `ACCEPTED`. Timeout, non-2xx response, malformed body, and mismatched ACK
   retain the message. The RX contract is that it sends `ACCEPTED` only after
   it has durably accepted the message, and duplicate IDs are idempotent.
2. Regular lightweight UDP probe packets addressed to RX for CSI observation.
   These are intentionally not written to NVS. RX will measure packet rate
   and CSI when built; TX does not claim to perform CSI inference.

The proposed RX HTTP path is `/api/v1/tx/environment`; TX's destination URL,
Wi-Fi credentials, sample interval, and UDP destination are configured locally
and never committed as secrets. The request includes schema version,
`event_id`, TX device ID, sequence number, timestamp `null` when unsynced,
temperature °C, humidity %, pressure Pa, BME680 gas resistance Ω or `null`,
MQ-135 raw ADC or `null`, per-sensor validity, and `gas_risk=UNAVAILABLE` unless
a separately validated policy is later added. It does not contain invented RX
activity or connectivity state. The test endpoint must implement the same ACK
contract, so TX can be verified before RX exists.

## Dashboard and backend evidence

Selectively port `dashboard/app.py` and `src/safesense/dashboard_view.py` from
V2 into V1, preserving the current V1 dashboard edit and the Environment,
Wi-Fi CSI, Human Context, System, and Recent Events layout. Retain the V2
freshness and unavailable-state behavior, but remove its hard-coded
`HOST VERIFIED` review badges and firmware-name-based device-source guess.
Remove MQTT-specific UI claims for the new HTTP path. A software test can be
shown, but must not be presented as device proof.

The existing backend already stores `TelemetryEvent.payload`, `event_id`,
`received_at`, and fusion outcome. Extend the overview response to expose
the stored event ID and server-receipt timestamp. The backend can truthfully
label the ingress to `/api/v1/telemetry` as `HTTP POST` because that endpoint
handled the request; this proves only the backend hop, not that a physical TX
or RX sent it. The dashboard adds an expandable, escaped/raw JSON telemetry
view, the matching event ID, server receipt time, freshness, and evidence
labels such as `Backend ingress: HTTP POST` and `TX→RX: UNVERIFIED` until live
two-board evidence exists. It never derives physical origin from a
`firmware_version` string. If no report exists, show waiting/unavailable.

After RX is built, a physical demonstration must match the same `event_id`
across TX serial output, RX receive/ACK log, backend stored event, and
dashboard JSON. The UI alone cannot prove device origin; do not add a
`DEVICE VERIFIED` badge solely because data reached the API.

## Error handling and verification

- Custom BME680 host tests cover chip-ID rejection, calibration/compensation,
  heater/gas validity, missing sensor, and I2C read failure. The driver must
  build with no external sensor library and be compared on hardware with the
  prior external-library diagnostic measurements.
- TX tests cover JSON bounds/units, unavailable gas semantics, NVS restore,
  exact ACK matching, non-2xx/malformed/mismatched responses, and retry with
  stable event IDs. A local HTTP receiver allows these checks before RX code.
- Hardware checks capture a continuous TX boot/read/send/ACK trace and a
  reboot while the endpoint is offline. A zero MQ-135 ADC value or missing
  BME680 must be reported as observed, not declared healthy by assumption.
- Backend/dashboard tests confirm the overview's event ID/receipt time/raw
  payload, HTML escaping, stale-data handling, and no unsupported proof badge.
  Inspect actual Streamlit desktop and narrow views in light and dark themes.
- Run the full Python and portable C suites, the classic-ESP32 build, and live
  COM11 serial checks before claiming TX completion. RX delivery and
  end-to-end backend HTTP remain explicit later gates.

## Non-goals for this phase

No RX firmware change, no released CSI activity model, no gas ppm/IAQ claim,
no cloud deployment claim, and no fabricated communication or hardware proof.
