# Deterministic safety fusion

Fusion is a safety policy, not another ML model. It combines BME680-derived environmental risk, evidence freshness, and CSI activity context into an explainable state.

## Environmental evidence

The BME680 measures temperature, humidity, pressure, and gas resistance. It does not directly report a certified gas type, concentration, or BSEC IAQ score. SafeSense compares gas resistance with a warmed EMA clean-air baseline:

- ratio above 0.75: `NORMAL`
- ratio at or below 0.75: `WARNING`
- ratio at or below 0.50: `CRITICAL`

These are conservative software defaults, not universal safety limits. Baseline updates occur only for valid normal samples, preventing a hazardous sample from dragging the reference downward. Target-room calibration remains mandatory.

## Decision table

| Priority | Condition | Fused state | Local action |
|---|---|---|---|
| 1 | Environmental risk `CRITICAL` | `INCIDENT` | Red LED, buzzer, persist/publish |
| 2 | Environmental risk `WARNING` | `WARNING` | Yellow LED, warning cadence, persist/publish |
| 3 | Sensor unhealthy/stale/unavailable | `DEGRADED` | Yellow degraded pattern, publish fault |
| 4 | CSI stale, `UNKNOWN`, or below confidence | `DEGRADED` | Activity stays unknown; publish fault |
| 5 | Healthy, fresh, no risk | `NORMAL` | Green LED |

`UNKNOWN != VACANT`. CSI can add human context, but it cannot veto a critical environmental reading. Invalid enum values also map to the degraded output pattern rather than creating false safe or incident claims.

## TinyML boundary

The CSI interface accepts exactly a `100 × 48` amplitude window. Firmware contains a guarded model adapter, but its default implementation returns `UNKNOWN`. The existing INT8 candidate failed the unseen-room macro-F1 release gate, so it is not enabled. A future model must pass leakage checks, held-out target-room evaluation, full-INT8 conversion checks, memory/latency checks, and a signed release manifest before firmware inclusion.

## Verification boundary

Portable C and Python tests verify decision priority and failure states. Real BME680 calibration, CSI generalization, LED/buzzer polarity, and timing need the two physical ESP32-S3 boards.
