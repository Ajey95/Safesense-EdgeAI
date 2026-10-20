# CSI presentation preview, 2026-10-14

The Live ESP32 tab currently falls back to **generated preview data** when the
backend reports `NO_FRESH_LIVE_CSI`. JavaScript in `web/forecast/csi.js` creates
a changing 100-frame signal trace and 50 pair values. The displayed people
count starts at 3 and alternates with 2 every 20 seconds. Both the count and values
are illustrative; no people-count model receives these generated values.
The bottom list contains 50 generated 100-frame window summaries at first
load, then rolls forward one window per refresh. It shows each window's
displayed count, mean amplitude, and amplitude range. The initial 50 rows are
generated on page load, not historical hardware recordings.

The personal dashboard uses live-recording wording for this fallback; those
labels do **not** establish a hardware capture. It switches to the real packet
path only if `/api/v1/csi-count/status` reports `LIVE_ESP32_SERIAL` from fresh
accepted `WISDOM_CSI` serial packets. At the time of this change, COM11 was the
only connected ESP32, identified as the environmental sensor board with MAC
`8c:94:df:90:1f:ec`. It had not emitted CSI packets, and live ESP32
people-count accuracy has not been measured.

The recorded replay tab remains a separate path backed by PRoFENCH/WiVi32
held-out windows and the trained 0/1/2 research model. Its 85.6% score is a
within-recording result, not accuracy for this room or board.
