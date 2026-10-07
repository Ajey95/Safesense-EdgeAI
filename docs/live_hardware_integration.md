# Live hardware readings and delivery trace

Open `/forecast?view=live` after starting the local backend and receiver for the selected hardware route. The view reads backend-stored physical telemetry from direct laptop Wi-Fi, paired laptop Bluetooth, direct USB, or the optional RX bridge. It does not show the synthetic forecasting episode. It refreshes every three seconds and labels the latest reading stale after 45 seconds without a newly stored event.

## Current single-board wireless route (2026-10-06)

The [direct laptop transport runbook](direct_laptop_transport.md) covers the ESP32 access point, laptop HTTP receiver, Bluetooth SPP receiver, exact-ID acknowledgements, and the labelled fault test. Physical BME680 and MQ-135 samples reached the laptop and backend over both Wi-Fi and Bluetooth. The Live Hardware screen labels these **DIRECT WIFI** or **DIRECT BLUETOOTH** and keeps transport receipts separate from backend storage. Those checks establish packet delivery for the recorded setup; they do not validate the synthetic-trained forecast as a real hazard detector.

## Current single-board USB route (2026-10-05)

The sensor board is ESP32 MAC `8c:94:df:90:1f:ec`. It was originally on COM12 and re-enumerated as COM11 on 2026-10-05; confirm the current port before starting the bridge. Its firmware emits newline-delimited physical BME680 and MQ-135 JSON samples at 115200 baud. To show those readings without the second ESP32, keep the backend running and start this bridge from the repository root using its current port:

```powershell
.\.venv\Scripts\python.exe -m scripts.direct_serial_bridge --port COM11 --api http://127.0.0.1:8000 --interval 2
```

Then open [Live Hardware](http://127.0.0.1:8000/forecast?view=live) and look for **DIRECT USB** and **LIVE USB READING**. The bridge converts BME680 pressure from hPa to Pa, preserves MQ-135 as raw ADC, validates the board's `sensor_status: OK` sample, and posts it to local FastAPI/SQLite. The dashboard reads backend-stored direct samples from `/api/v1/overview` and labels them separately from RX-bridge telemetry. A missing or stopped bridge causes the latest reading to become stale after 45 seconds. This direct route has no RX queue, Wi-Fi ACK, Bluetooth receipt, TinyML forecast validation, or SOS claim. The scenario forecast page remains synthetic.

**Refresh now** checks the backend for a newer stored sample and reports when none has arrived. It does not reopen a serial port. On 2026-10-05 COM12 disappeared from Windows while the same sensor board appeared on COM11 (MAC verified). Moving the bridge to COM11 restored live readings; the dashboard correctly kept the old sample stale until a new one reached the backend.

On 2026-10-05, the bridge stored changing COM12 readings and the Live Hardware page rendered fresh temperature, humidity, pressure, BME680 gas resistance, and MQ-135 raw ADC values. The second board is not used for this route.

## Optional two-board Wi-Fi route

## Physical route

1. The normal TX firmware reads BME680 temperature, humidity, pressure and gas resistance plus MQ-135 **raw ADC**. It assigns an event ID and sequence, commits the JSON to TX NVS, then sends HTTP over Wi-Fi to RX. A matching RX application ACK removes the TX queue head. TX's own receipt of that ACK is visible in serial logs, not inferred by the backend.
2. RX stores the exact event ID in its NVS queue before replying. The laptop RX bridge polls that queue, validates the receipt, posts the sample to local FastAPI with the bridge ingress marker, checks backend acceptance and the exact ID, then asks RX to clear that head. The bridge journals the successful RX forward ACK and syncs it to FastAPI. Its heartbeat indicates whether the laptop polling process is active; a heartbeat is not proof that the radio link is healthy.
3. For a forecast alert that has not received an RX ACK, TX sends `ALERT|event|room|horizon|channel|R` over Bluetooth Classic SPP to a paired nearby laptop. The laptop appends the alert to `data/bt_alert_receipts.jsonl`, flushes it to disk, and only then replies `ACK|event`. It separately syncs the receipt to FastAPI and attempts local Windows speech. The `R` field marks normal real-sensor mode; `S` marks synthetic UART replay. Older frames with no field have unknown origin and are excluded from the physical monitor.

The live view displays RX NVS storage, backend SQLite storage, RX queue clearance, and nearby laptop Bluetooth storage separately. A missing or stale receipt is **unconfirmed**, not a successful delivery. The backend cannot directly attest that TX received its Wi-Fi ACK, that speech finished, or that an outside recipient heard an alert. The local ingress markers identify the bridge process; they are not cryptographic board attestation.

## Start the stack

Build and flash `firmware/node1_sensor_tx` with `CONFIG_SAFESENSE_TX_SCENARIO_SERIAL_DEMO` **off** and `CONFIG_SAFESENSE_TX_DIRECT_LAPTOP_AP` **off**, then configure the TX station for RX's `192.168.4.1` access point. Build and flash `firmware/node2_csi_gateway` on the other classic ESP32. Confirm actual COM ports before flashing; previous COM11/COM12 identities are historical.

Install the demo extra for the Bluetooth serial port, then run the services in separate terminals from the repository root:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[demo]"
.\.venv\Scripts\python.exe -m uvicorn safesense.main:app --host 127.0.0.1 --port 8000
netsh wlan connect name=SafeSense-RX-V1
.\.venv\Scripts\python.exe -m scripts.rx_http_bridge --rx http://192.168.4.1 --api http://127.0.0.1:8000
.\.venv\Scripts\python.exe scripts/bt_alert_receiver.py --port COM16 --api http://127.0.0.1:8000
```

Use the actual outgoing Bluetooth COM port after pairing with `SafeSense-TX-Alert`; `COM16` is an example. The RX bridge and Bluetooth listener run independently. The laptop needs to stay connected to RX's AP for continuous Wi-Fi forwarding. Its local FastAPI service does not require internet.

Open [Live Hardware](http://127.0.0.1:8000/forecast?view=live). The screen should show an RX bridge heartbeat, then a recent event ID with five sensor fields and RX/backend timestamps. The Bluetooth listener heartbeat means the COM process is running, not that TX is paired. A Bluetooth-only alert can appear while Wi-Fi delivery is unavailable. The dashboard's forecast fault toggle remains a **synthetic demo control**; it does not cut a real radio connection.

## Current evidence boundary

The direct laptop Wi-Fi and Bluetooth routes have physical sample receipts in the recorded setup. Direct USB and optional TX→RX are separate routes with their own evidence; neither can be inferred from the other. MQ-135 raw ADC is not a calibrated gas concentration. The synthetic-trained forecast still needs 61 valid one-minute samples before a real-sensor model alert and is not validated for real hazard prediction. The TX NVS queue filled during a prolonged Wi-Fi absence in the recorded session, so long-outage durability is not established.
