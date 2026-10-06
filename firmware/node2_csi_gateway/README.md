# V1 classic-ESP32 RX/CSI gateway

This is the live RX board on branch `v1` (COM12, MAC
`8c:94:df:90:dd:4c` in the 2026-09-24 test). It creates the lab AP
`SafeSense-RX-V1` at `192.168.4.1`; the TX board joins that AP. The default
password in `main/Kconfig.projbuild` is for a local demo only, not deployment.

TX sends bounded JSON to `POST /api/v1/tx/environment`. RX validates the V1
schema and exact event ID, commits the JSON to its own `ssrx` NVS queue, then
returns HTTP 202 with matching `ACCEPTED`. A duplicate still in the queue is
acknowledged without a second enqueue. Invalid JSON or a full/unreadable queue
gets a non-2xx response, so TX retains its own NVS copy.

The laptop polls `GET /api/v1/pending`, posts the converted event to local
FastAPI, checks `accepted: true` and the exact backend event ID, then sends
`POST /api/v1/forward-ack`. Only the current RX queue head with that exact ID
is removed. RX reports its NVS receipt and CSI counters as metadata; the
dashboard labels these as RX-reported, not cryptographic device attestation.

TX also sends UDP probes to RX port 3333. The live classical ESP32 marked the
first four CSI bytes invalid on every observed packet. The diagnostic RX
pipeline masks the affected +1 carrier with zero and retains 47 measured
carriers in each 48-wide frame; it formed live 100-frame windows. The mask is
explicit in RX metadata. These windows are **not** passed to an activity
model. Activity remains `UNKNOWN`, confidence unavailable, and fusion
`DEGRADED` until a target-room model is validated and released.

## Build and run

From this directory with ESP-IDF 6.1 PowerShell environment:

```powershell
idf.py set-target esp32
idf.py build
idf.py -p COM12 flash monitor
```

Run the local backend and dashboard from the repository root in separate
terminals:

```powershell
.\.venv\Scripts\python.exe -m uvicorn safesense.main:app --host 127.0.0.1 --port 8000
.\.venv\Scripts\python.exe -m streamlit run dashboard\app.py
```

For continuous bridge polling, the laptop must remain connected to RX's AP:

```powershell
netsh wlan connect name=SafeSense-RX-V1
.\.venv\Scripts\python.exe -m scripts.rx_http_bridge
```

The demo laptop has only one Wi-Fi adapter, so joining RX's AP temporarily
disconnects its ordinary internet connection. For a bounded evidence run,
`scripts/run_rx_bridge_demo.ps1 -RestoreWifiProfile <profile-name>` forwards up to 22 queued events
and restores the named Wi-Fi profile automatically. Continuous collection requires keeping
the laptop on the RX AP plus a second internet path, or changing the
RX-to-host transport. The local FastAPI/Streamlit services can run without
internet once installed. The safety dashboard marks telemetry stale after 15
seconds without a newly forwarded record, so its live values disappear soon
after a bounded demo stops; stored JSON and event IDs remain visible.

## Evidence and remaining gates

RX boot restored its NVS queue after resets, accepted exact TX event IDs via
HTTP, and a laptop bridge delivered matching IDs to SQLite/Streamlit. A live
RX poll showed 1,461 CSI frames, 69 diagnostic windows, 47 measured carriers,
and -50 dBm RSSI; later runs exceeded 24,000 callbacks. The MQ-135 belongs
to TX and is still raw ADC 0; this RX firmware cannot make it healthy. No
calibrated gas-risk result or reliable activity classification is claimed.
