# Dashboard UX Decisions

The dashboard is intentionally an operations view, not a presentation screen. It puts the fused safety state first, then shows the evidence an operator needs to interpret it: activity/CSI quality, environment, CSI profile, device health, and the incident queue.

## Applied decisions

- Critical state, warning, degraded telemetry, and normal status use text plus color. The state is never encoded by color alone.
- The layout keeps the most safety-relevant information above the fold and groups supporting diagnostics beneath it.
- Values update from a bounded local-demo refresh interval; an unavailable API is shown as an explicit error state rather than a blank dashboard.
- Incident acknowledgement is an explicit button with disabled completion state. It does not automatically resolve an incident.
- The Streamlit page uses semantic headings and native buttons. The design avoids tiny text, excessive decoration, automatic animation, and inaccessible color-only indicators.

## References

- WCAG 2.2 contrast minimum: text should meet 4.5:1 contrast except for stated exceptions.
- W3C ARIA status guidance: application status updates should be programmatically available to assistive technology.

## Local-demo boundary

The three-second refresh is appropriate for this local review dashboard, but a deployed multi-user operations surface should consume server-pushed updates (for example, WebSocket/SSE fan-out) rather than use client polling.
