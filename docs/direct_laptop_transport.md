# SafeSense single-board Wi-Fi and Bluetooth delivery

The classic ESP32 sensor board uses its custom BME680 driver and MQ-135 raw
ADC. In direct-laptop mode it hosts the 2.4 GHz `SafeSense-TX-Laptop` Wi-Fi
network. The nearby Windows laptop connects to that network and runs
`scripts.direct_laptop_receiver` on port 8765. The receiver announces its
current Wi-Fi address by UDP; the ESP32 then POSTs each event directly to the
laptop. The receiver commits the exact ID and payload to local SQLite before
replying `{ "event_id": "...", "status": "ACCEPTED" }`. The ESP32 removes an
event from its NVS queue only after matching that ACK. The laptop separately
syncs the event to the SafeSense backend.

For a forecast alert without a Wi-Fi ACK, the ESP32 also sends the same event
ID by Bluetooth Classic SPP. `scripts.bt_alert_receiver` journals that alert
before sending `ACK|ID`, reports the receipt to the backend, and attempts
local speech. A Bluetooth ACK proves laptop journal storage, not speech
playback or backend storage. Wi-Fi and Bluetooth use the same ESP32 radio, so
this fallback cannot overcome every radio failure.

When an environmental sample lacks a Wi-Fi ACK, TX also sends its full sensor
JSON as `DATA|...` over the paired SPP link. The laptop validates and commits
it to `data/live/direct_bt.db` before returning `ACK|ID`; it then syncs the
sample to the backend with a distinct Bluetooth ingress marker. Live Hardware
shows fresh BME680 and MQ-135 readings as **DIRECT BLUETOOTH** while Windows
stays on another Wi-Fi network. This is a separate receipt from an alert.

## Running the route

1. Verify the board MAC before flashing. The board used for the current lab
   session is `8c:94:df:90:1f:ec` on COM11; port numbers can change. Back up
   the existing 4 MB flash image first. The local backup directory is
   `output/hardware_backup/` and is excluded from Git.
2. Build and flash `firmware/node1_sensor_tx` under ESP-IDF 6.1, with
   `CONFIG_SAFESENSE_TX_DIRECT_LAPTOP_AP=y`. The SSID and demo password are in
   its Kconfig defaults. Keep the generated `sdkconfig` private.
3. Join the laptop to the ESP32's `SafeSense-TX-Laptop` Wi-Fi network. This
   temporarily replaces its normal Wi-Fi connection; the dashboard remains
   reachable at `http://127.0.0.1:8000/forecast?view=live`.
4. Run the local backend on `127.0.0.1:8000` and run
   `.venv/Scripts/python -m scripts.direct_laptop_receiver --port 8765`.
   The laptop receiver binds port 8765; Windows Firewall must allow inbound
   TCP from the ESP32's `192.168.4.0/24` network. Its local journal is
   `data/live/direct_laptop.db`.
5. Pair Windows Bluetooth with `SafeSense-TX-Alert`, find the outgoing SPP
   COM port, and run `.venv/Scripts/python -m scripts.bt_alert_receiver
   --port COMx`. The SPP receiver journal is separate from the Wi-Fi journal.
6. In **Live Hardware**, inspect a fresh direct Wi-Fi sensor event and its
   backend storage. To test fallback, select **Inject Wi-Fi receiver fault**
   and then **Send transport test alert**. The fault makes the laptop HTTP
   receiver reject a real ESP32 POST; it does not disable the Wi-Fi radio.
   The test alert is labelled and is not a forecast accuracy result. Verify
   the Bluetooth receiver's exact-ID receipt, then turn the fault off and
   verify the ESP32 drains its queued Wi-Fi events. On another Wi-Fi network,
   the dashboard rejects this request and prompts for the ESP32 AP.
7. For a Bluetooth-only transport check while Windows remains on another
   network, run `.venv/Scripts/python -m scripts.bt_alert_receiver --port COMx
   --send-test`. The paired laptop sends one `TEST` command over SPP; the board
   creates a labelled test alert at its next sample and expects an exact-ID
   `ACK|ID`. Restart the receiver without `--send-test` for normal operation.
   This verifies Bluetooth alert delivery, not a forecast or Wi-Fi repair.

## Proof boundaries

- A laptop Wi-Fi ACK means the local SQLite journal committed the exact event.
  The backend has its own stored-event timestamp and may lag during outages.
- The BT receiver's ACK means its journal stored an alert with that ID. An
  unpaired laptop, absent outgoing COM port, or stopped receiver leaves BT
  unconfirmed.
- The synthetic-trained TinyML forecast is not validated as a real hazard
  detector. The transport test exercises delivery only.
- The demo network uses a shared lab password and an unauthenticated HTTP
  event protocol within the AP subnet. It is for a nearby controlled review,
  not a public or safety-certified deployment.

## Physical check on 2026-10-06

- Board MAC `8c:94:df:90:1f:ec` on COM11. The connected BME680 responds at
  I2C `0x77` on GPIO21/GPIO22; firmware now probes both `0x76` and `0x77`.
- The ESP32-to-laptop Wi-Fi path delivered real BME680 and MQ-135 samples, with
  exact event IDs stored in the laptop journal and backend. Example event
  `tx-3f4ec03b44a16c5dc5c98404` contained 30.61 °C, 68.84% RH,
  97,208.48 Pa, 27,366 Ω BME680 gas resistance and MQ-135 ADC 142.
- On Windows `Amrita` Wi-Fi, the paired outgoing Bluetooth port was COM15.
  A labelled test alert `tx-b5a58d68bafed12fe1b3b23e` was stored by the
  laptop and backend, and the board logged the same ID with `state=STORED`.
- With Windows still on `Amrita`, the updated firmware sent real Bluetooth
  sensor event `tx-93a6153a6e87907efefba3bf`; laptop and backend stored
  BME680 34.27 °C, 51.86% RH, 97,141.6 Pa, 24,237.09 Ω gas resistance,
  and MQ-135 ADC 126. Multiple subsequent samples arrived about every 10 s.
  The browser rendered **LIVE BLUETOOTH READING** after its UTC timestamp
  parsing was corrected.
- The TX NVS queue was already full at 16 records while the laptop was away
  from the ESP32 AP. The Bluetooth alert still succeeded, but that test event
  was not stored in the TX queue. Queue capacity and urgent-event retention
  need improvement before claiming durable delivery during long Wi-Fi outages.
