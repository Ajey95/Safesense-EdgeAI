# SafeSense Fusion Design

## Purpose

The fusion layer is a deterministic safety policy, not a second classifier. It combines an already-classified environmental risk with CSI activity context and component health. Its output must be explainable on the dashboard and reproducible during review.

## Evidence and boundary

- The BME280 measures temperature, humidity, and pressure. It is not a gas sensor. Environmental danger therefore enters this engine as a risk already determined by a separately calibrated gas/smoke sensor or controlled simulator input. Temperature or humidity thresholds are deliberately not invented in fusion code.
- ESP-IDF states that the CSI callback runs from the Wi-Fi task and should hand data to a queue for lower-priority work. CSI freshness and model confidence are therefore inputs to fusion, not assumptions.
- The fusion layer does not label `UNKNOWN` as `VACANT`. Missing, stale, or low-confidence CSI becomes `DEGRADED` human context.

## Decision table

| Priority | Conditions | State | Action |
|---|---|---|---|
| 1 | Environmental risk is `CRITICAL` | `INCIDENT` | Local alarm, persist event, publish incident |
| 2 | Environmental risk is `WARNING` | `WARNING` | Persist warning transition, publish state |
| 3 | Environmental sensor is unhealthy/stale | `DEGRADED` | Publish health fault; do not fabricate a safe state |
| 4 | CSI stale, `UNKNOWN`, or confidence below policy | `DEGRADED` | Publish CSI fault; activity remains unknown |
| 5 | Otherwise | `NORMAL` | Publish normal state |

Environmental criticality is evaluated before CSI availability. Thus a lost CSI link can never suppress a real environmental incident. The transition tracker emits a persistence action only when the fusion state changes; it prevents repeated samples from creating duplicate events. Incident resolution is intentionally an explicit operator/backend action, not an automatic clear.

## Configuration

`minimum_csi_confidence` defaults to 0.70 only as a software policy seed. It must be tuned against held-out, local-room validation data before demo claims. Environmental thresholds/calibration belong to the particular gas/smoke sensor module and its datasheet, not this generic fusion layer.

## Sources

- Bosch Sensortec, BME280 product page and datasheet: temperature, humidity, pressure capabilities and operating ranges.
- Espressif, ESP-IDF Wi-Fi CSI documentation: callback setup and queue-offloading guidance.
