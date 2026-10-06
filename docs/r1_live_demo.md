# SafeSense R1 live demo (24 September 2026)

Use PowerShell in `D:\SafeSense`. The verified ports today are TX `COM11` and RX
`COM13`. The bridge helper
detects and restores whichever profile is connected when it starts.

The R1 view shows selected fields from the real local API. It does not alter
the firmware message or the database row. Do not display the full UART stream
or the full dashboard if the review scope is limited to BME680 temperature,
humidity and pressure, CSI, persistence and communication.

## Before the audience arrives

Check that both boards appear and that the API and R1 view answer:

```powershell
Set-Location D:\SafeSense
Get-CimInstance Win32_SerialPort | Select-Object DeviceID,Description
Invoke-RestMethod http://127.0.0.1:8000/health
Invoke-WebRequest http://127.0.0.1:8501 -UseBasicParsing | Select-Object StatusCode
```

If the API or view is not running, start these in separate PowerShell windows:

```powershell
Set-Location D:\SafeSense
& .\.venv\Scripts\python.exe -m uvicorn safesense.main:app --host 127.0.0.1 --port 8000
```

```powershell
Set-Location D:\SafeSense
$env:SAFESENSE_R1_REVIEW='1'
& .\.venv\Scripts\python.exe -m streamlit run dashboard\app.py --server.address 127.0.0.1 --server.port 8501
```

Open `http://127.0.0.1:8501`. The detailed dashboard layout is preserved;
the R1 mode selects the temperature, humidity, pressure, CSI and communication
fields. The "Origin from API alone" row remains `UNVERIFIED` because the API
cannot independently identify a physical board. Match the event ID with the
two UART logs and bridge output when presenting the physical link.
The System node rows show `REPORTED ONLINE` from the saved link report while
fresh, then `LAST REPORTED ONLINE · STALE`. Stored BME680 and CSI values remain
visible with a stale label after the 15-second freshness window.

A stale event is expected until the bridge
forwards a new one. An initial preflight found both NVS queues at 16/16 and RX
returning HTTP 503; a later bridge preflight forwarded records successfully.
Run the bridge again near the presentation for a fresh end-to-end event.

## Member 1 — custom BME680 driver

Show presentation slides 2–4, point to I2C address `0x76`, `GPIO21` SDA,
`GPIO22` SCL, calibration block parsing and temperature compensation. In a
PowerShell window run the host test:

```powershell
Set-Location D:\SafeSense
& 'C:\Espressif\v6.1\esp-idf\export.ps1'
mingw32-make -C firmware/tests test_bme680_driver
& .\firmware\tests\test_bme680_driver.exe
```

Expected host result: `bme680_driver tests passed`.

In another window capture selected live UART lines. The helper prints the
three BME680 readings and the evidence lines needed below; it does not change
what either board emits:

```powershell
Set-Location D:\SafeSense
& 'C:\Users\AJEYA\.espressif\python_env\idf6.1_py3.12_env\Scripts\python.exe' .\scripts\capture_r1.py --tx COM11 --rx COM13 --seconds 300 |
  Tee-Object -FilePath (Join-Path $env:TEMP 'safesense-r1-live.log')
```

Point to `Custom BME680 initialized at 0x76` and a live `BME680 T=... RH=...
P=...` line. The latter is a selected-field display of the UART line.

## Member 2 — NVS and exact acknowledgement

The capture should show `Restored ... pending` after board boot. In another
PowerShell window, run the bounded bridge. It polls RX, forwards queued
records to the local API, ACKs matching event IDs, and restores the original
Wi-Fi profile:

```powershell
Set-Location D:\SafeSense
& .\scripts\run_r1_bridge_demo.ps1
```

Point to `rx_persisted=True`, `forwarded event=... backend=HTTP POST RX=ACKED`,
then a TX/RX matching event ID in the UART window. If it reports `deferred`
or no forwarded ID, the live end-to-end claim has not passed; check API health,
RX AP connection and the queue, then rerun.

## Member 3 — CSI preprocessing

The bridge prints RX `csi_frames`, `csi_windows`, `measured_carriers` and
`csi_rssi_dbm`. In the UART window, show the latest diagnostic windows:

```powershell
Select-String (Join-Path $env:TEMP 'safesense-r1-live.log') -Pattern 'CSI window ready' |
  Select-Object -Last 5
```

Explain that the ready window has 100 frames and the classic ESP32 reports
47 measured carriers plus one masked carrier. Activity is `UNKNOWN` until a
validated model is released.

## Member 4 — API, SQLite and live R1 view

Open `http://127.0.0.1:8501`. If the page says the event is stale, rerun the
bridge while the page is visible. It refreshes every two seconds.

The bridge writes its last forwarded ID to a temporary file. Use it to show
the exact same record returned by FastAPI:

```powershell
$id = (Get-Content (Join-Path $env:TEMP 'safesense-r1-event-id.txt') -Raw).Trim()
if (-not $id) { throw 'No event was forwarded in this run.' }
$record = (Invoke-RestMethod http://127.0.0.1:8000/api/v1/overview).telemetry |
  Where-Object event_id -EQ $id | Select-Object -First 1
if (-not $record) { throw 'The forwarded ID is not in the latest API page.' }
[pscustomobject]@{
  event_id = $record.event_id
  backend_ingress = $record.backend_ingress
  server_received = $record.received_at
  temperature_c = $record.payload.environment.temperature_c
  humidity_pct = $record.payload.environment.humidity_pct
  pressure_pa = $record.payload.environment.pressure_pa
  csi_window_frames = $record.payload.csi.window_frames
  measured_carriers = $record.payload.csi.selected_subcarriers
  rx_queue_persisted = $record.payload.communication.rx_queue_persisted
} | Format-List
```

Match that `event_id` to the bridge output and the R1 view. Backend ingress is
observed by FastAPI; the RX persistence flag is reported by the receiver.
