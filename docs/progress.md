# SafeSense Implementation Progress

This page separates **what is established in the current project design** from what is still being implemented or experimentally validated. It exists so the repository can be used as proof of ongoing work without presenting unfinished modules as complete.

## Current status

| Area | Status | Notes |
|---|---|---|
| System architecture | Defined | Two ESP32 edge nodes + incident backend flow documented. |
| Environmental sensing path | In progress | Sensor acquisition and threshold/risk logic are part of the active prototype work. |
| Wi-Fi TX/RX sensing path | In progress | ESP32 radio sensing setup is being developed for CSI/RSSI feature collection. |
| CSI/RSSI preprocessing | In progress | Feature/window construction is being refined for TinyML input. |
| TinyML presence/activity model | In progress | On-device inference path and validation are ongoing. |
| Edge risk + presence fusion | Designed / in progress | Final confirmation logic combines environmental risk with inference evidence. |
| MQTT/HTTP event transport | Designed | Structured telemetry/incident interfaces are part of the target architecture. |
| Backend incident lifecycle | Designed / prototype scope | Validation, persistence, deduplication, dashboard state and acknowledgement flow are planned as the backend boundary. |
| Controlled end-to-end validation | Pending | Requires repeatable hardware experiments and measured false-positive/false-negative behaviour. |

## What this repository currently proves

- A concrete system architecture for an **ESP32 + Wi-Fi sensing + TinyML** edge pipeline.
- Defined responsibilities between environmental sensing, radio sensing, TinyML inference, edge fusion and cloud incident handling.
- A privacy-oriented design that avoids using a camera for human-presence/activity evidence.
- A risk-triggered inference strategy rather than treating every sample as an emergency.
- A clear engineering path for MQTT/HTTP transport, retry/buffering, incident deduplication and acknowledgement handling.

## What is not being claimed yet

- Production readiness.
- Certified environmental safety thresholds.
- Guaranteed Wi-Fi CSI accuracy across arbitrary rooms/hardware geometries.
- A fully validated activity classifier under all radio conditions.
- Safety-critical reliability or emergency-service integration.

## Next validation milestones

1. Stabilize ESP32 TX/RX placement and reproducible Wi-Fi observations.
2. Record labelled CSI/RSSI windows for a small, controlled set of presence/activity classes.
3. Build the preprocessing pipeline and quantify feature stability.
4. Train/convert a TinyML-friendly model and measure on-device latency, memory use and confidence behaviour.
5. Integrate environmental-risk triggering with the inference path.
6. Emit a structured incident JSON only after the fusion decision.
7. Validate buffering/retry and duplicate-event suppression during temporary network failure.
8. Run a controlled end-to-end demonstration and document observed false positives/false negatives.

## Related embedded proof of work

A completed STM32 embedded project is available separately at:

- [Ajey95/TrolleyMakers](https://github.com/Ajey95/TrolleyMakers)

That repository demonstrates STM32F401CCU6 peripheral integration including RFID over SPI, I2C LCD interfacing, GPIO controls and embedded application logic.
