# Dashboard UX Decisions

The dashboard is an operations view that doubles as the review evidence surface. It puts the fused safety state first, then shows the BME680, CSI, two-node, output, persistence, and model-release evidence needed to explain the prototype.

## Applied decisions

- Critical state, warning, degraded telemetry, and normal status use text plus color. The state is never encoded by color alone.
- The layout keeps the most safety-relevant information above the fold and groups supporting diagnostics beneath it.
- Values update from a bounded local-demo refresh interval; an unavailable API is shown as an explicit error state rather than a blank dashboard.
- Incident acknowledgement is an explicit button with disabled completion state. It does not automatically resolve an incident.
- Missing BME680 values render as `UNAVAILABLE`; zero is never substituted for a missing measurement and degraded data is never shown as safe.
- The summary identifies generated events as `SOFTWARE TEST`. Smoke events keep physical node and sensor fields `UNKNOWN`/`UNAVAILABLE`, so laptop-path verification cannot look like attached hardware.
- The System card separates Node 1 and Node 2, and shows the actual LED/buzzer state, NVS queue depth, and CSI callback drops.
- The Review Evidence card distinguishes verified software from the pending physical-device test. It does not turn a successful ESP-IDF build into an unobserved hardware claim.
- The TinyML release state remains visible. A rejected or absent candidate is shown as release-gated instead of being represented as a working activity model.
- The Streamlit page uses semantic headings and native buttons. The design avoids tiny text, excessive decoration, automatic animation, and inaccessible color-only indicators.
- Only the three newest active incidents are expanded; any additional count is stated without discarding records from SQLite.

## References

- WCAG 2.2 contrast minimum: text should meet 4.5:1 contrast except for stated exceptions.
- W3C ARIA status guidance: application status updates should be programmatically available to assistive technology.

## Local-demo boundary

The three-second refresh is appropriate for this local review dashboard, but a deployed multi-user operations surface should consume server-pushed updates (for example, WebSocket/SSE fan-out) rather than use client polling.
