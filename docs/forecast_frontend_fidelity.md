# Forecast dashboard visual check

The primary page at `/forecast` uses the earlier light-blue SafeSense cold-storage reference as its 1586 × 992 desktop layout target. The alternate dark engineering concept was used only as a source of room-atmosphere direction; it has a different panel structure. The user clarified that selecting a scenario should change the dashboard's room theme.

Saved browser captures: [cold-storage view](evidence/forecast-ui-cold-storage.png) and [classroom view](evidence/forecast-ui-classroom.png).

| Reference feature | Browser implementation | Check |
|---|---|---|
| Navy top bar, 198 px left rail, pale blue main canvas | Same structure and dimensions at 1586 × 992 | Browser screenshot inspected |
| Heading, scenario selector, run button, simulation strip | Same order, proportions, and light card treatment | Scenario selection and playback clicked |
| Current / next 30 minutes / communication cards | Three-card row, live synthetic values, exact-ID route state | Wi-Fi fault toggle clicked; fallback labels changed |
| Forecast chart and response timeline | Two-card lower row with dynamic sensor trace and alert route events | Current versus forecast checked; gas-response trigger changes chart channel |
| Bottom status banner and snowy sidebar art | Same position and visual weight | Cold-storage default inspected at reference viewport |

The reference image included a named recipient, a cloud outage, battery, door position, and confirmed voice delivery. Those are not produced by this demo, so the implementation uses synthetic route labels and actual available sensor channels. It does not copy invented receipts or readings from the reference. The room selector swaps palettes, sidebar artwork, icon, tagline, and chart accent for cold storage, laboratory, classroom, bakery, and server room while preserving the reference layout.

Browser checks covered the desktop reference viewport and a 390 px mobile viewport. No page error or horizontal document overflow was observed. The mobile chart scrolls within its own panel so its axis labels remain readable. Physical TX/RX and Bluetooth receipts require a connected board and receiver; they were not established by browser checks.

The left rail now navigates to seven additional views rather than scrolling the forecast page. The Forecast view retains the reference geometry; the other views use the same design system for sensor readings, scenario selection, alert policy, baseline reports, transport status and simulation controls. Navigation, direct `?view=` links, browser history, site selection, report reveal, integration fault and settings were exercised in a browser. [Alerts view capture](evidence/forecast-ui-alerts.png).
