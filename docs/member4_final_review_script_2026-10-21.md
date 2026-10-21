# Member 4 final-review speaking script — delivery, evidence, and new-room collection

Prepared against the `D:\SafeSense` working tree on 21 October 2026. Approximate speaking time: **8–10 minutes**, plus questions. Line numbers refer to this snapshot and can move after edits. Say “I implemented” only for work you personally did; this script assigns a review section, not authorship.

## Before speaking

Open these tabs before the review:

1. `http://127.0.0.1:8000/forecast?view=live` for **Live Hardware** and the ESP32 NVS → databases card.
2. `http://127.0.0.1:8000/forecast?view=csi` for **Wi-Fi CSI Count**, live source, new-room capture, and downloads. If the view URL changes, use the dashboard's numbered navigation buttons.
3. `scripts/direct_laptop_receiver.py`, `scripts/bt_alert_receiver.py`, `scripts/wifi_demo_session.py`, `src/safesense/main.py`, `src/safesense/live_api.py`, `src/safesense/room_capture.py`, `src/safesense/export_api.py`, and `scripts/sos_voice.py`.

Check the displayed **event ID, transport, board capture age, laptop/backend times, actual connected SSID, and CSI source** before calling anything live. A running process, paired Bluetooth device, or old receipt is insufficient. The Wi-Fi visit currently restores the saved `Amrita` profile; confirm that profile exists on the presentation laptop. The SPP port has been `COM15` on this setup, but Windows can reassign it. Do not expose the Telegram token or contact IDs on screen.

## Spoken script

### 0:00–0:55 — Handoff from Member 3 and your contribution

> My teammate has shown how the ESP32 reads the BME680 and stores a sensor event in its 16-record flash queue. I take that same event ID from the board to the laptop, backend, and dashboard. I also own the guided collection path that lets a new room supply actual occupancy labels and export a dataset for later validation. My part answers two reviewer questions: “Did the data arrive?” and “Can another user collect defensible room data?”
>
> The board can send environmental records over its direct Wi-Fi access point or Bluetooth Classic SPP. The laptop keeps a durable journal before acknowledging them, then copies them into FastAPI and SQLite. A receiver acknowledgement and a backend receipt are separate steps, and I will point to both.

**Live action:** On **Live Hardware**, choose the newest *physical* sensor row. Read its event ID aloud, then point to transport and laptop/backend receipt times. If it is old, say “This is the last stored event; I am using it to trace the pipeline,” not “This is arriving now.”

### 0:55–2:25 — Wi-Fi path and exact event receipt

> The direct Wi-Fi route is ESP32 access point `SafeSense-TX-Laptop`, UDP discovery on port 3334, and HTTP to the laptop receiver on port 8765. In `direct_laptop_receiver.py:293–317`, the HTTP handler accepts only the expected route and size, parses the event, and writes it through `Receiver.accept`. In `:124–131`, the event ID is the SQLite key. If the same ID returns with different payload, it is rejected; if the payload is identical, it is a duplicate rather than a new event. Only after local storage does the HTTP handler return the accepted event ID.
>
> On the board, `main.c:447–449` requires both a successful HTTP status and an ACK matching that exact ID. In `main.c:517–531`, it removes the flash-queue head only after that check succeeds. This is why I compare IDs across the screen, rather than claiming delivery because an HTTP request merely completed.

**Open:** `scripts/direct_laptop_receiver.py:124–131`, then `:293–317`; `firmware/node1_sensor_tx/main/main.c:447–449` and `:517–531`.

```python
existing = db.execute("SELECT payload FROM events WHERE event_id=?", (event_id,)).fetchone()
if existing and existing[0] != raw:
    raise ValueError("event ID was reused with different data")
if not existing:
    pending = int(self.sos_voice and alert is not None and tx.get("simulated") is False)
    db.execute("INSERT INTO events (event_id,payload,sos_pending,observed_at_utc,capture_age_ms) "
               "VALUES (?,?,?,?,?)", (event_id, raw, pending, observed_at, age))
```

> Then `Receiver.sync_once`, lines 203–228, posts the stored record to `/api/v1/telemetry`. It marks the laptop record `backend_stored=1` only when the backend returns `accepted: true` with the same event ID. The backend's `main.py:56–86` deduplicates by event ID and records a delivery marker. The dashboard shows the stored evidence from those backend tables. A laptop ACK can therefore succeed during a backend outage, while the laptop journal remains pending for retry.

**Open:** `scripts/direct_laptop_receiver.py:203–228` and `src/safesense/main.py:56–86`. Point to **laptop_stored**, **backend_pending**, and the matching delivery row on the dashboard. `backend_pending` describes the laptop journal, not the ESP32 NVS queue.

### 2:25–3:50 — Bluetooth fallback and honest handoff check

> When Wi-Fi does not yield an exact ACK, the board can send the same queued sensor payload as `DATA|JSON` through Bluetooth Classic SPP. In `bt_alert_receiver.py:287–301`, the laptop commits it into `direct_bt.db` through the same `Receiver.accept` logic, sends `ACK|event_id`, then syncs to the backend. The SPP ACK means the laptop stored the record; it does not itself prove backend storage or Telegram delivery.
>
> Our laptop has one Wi-Fi adapter. The demo control **Use ESP32 Wi-Fi for 120s** joins the board AP, then restores `Amrita` in a `finally` block in `wifi_demo_session.py`. The important check is the connected SSID, not whether Windows accepted the connect command. The dashboard now shows a timestamped Wi-Fi/Bluetooth transition log. After returning, the **Return to Amrita · Bluetooth** or **Reconnect Bluetooth** action requests the SPP listener to reopen. The dashboard calls it **Bluetooth ready** only if a *new* Bluetooth frame arrives after the request and the same event ID has a backend receipt. It times out after 70 seconds rather than falsely claiming recovery.

**Live action:** If hardware and time permit, click **Use ESP32 Wi-Fi for 120s** and show `ON_SAFESENSE_AP`, a *new* Wi-Fi receipt, and return to `Amrita`. The transition log records each step and the probe outcome. Then show a *new* Bluetooth sensor receipt or the explicit handoff wait state. AP association can fail on Windows; report the actual status. Do not claim both routes delivered the same current event unless the IDs prove it.

**Open:** `scripts/bt_alert_receiver.py:287–301`, `scripts/wifi_demo_session.py:172–204`, and `src/safesense/live_api.py:218–249`.

### 3:50–5:00 — Failure I debugged: a living process with a dead link

> We found a particularly misleading failure after a physical ESP32 restart. The Bluetooth receiver process was still running and could report a heartbeat, but the SPP link had stopped delivering frames. The dashboard could still show old sensor rows, so a process heartbeat looked healthier than the actual data path. We reproduced that by comparing event IDs and timestamps across a board restart, then reopened the COM connection and watched for a new matching event.
>
> The fix is in `bt_alert_receiver.py:247–270`: when the laptop is back on `Amrita` and no frames arrive for the idle interval, the listener raises a serial exception and reopens the port. A dashboard handoff request can trigger the same reopen. The outer loop retries after a disconnect at lines 318–320. Our verification condition is a fresh frame plus backend receipt, not a green process indicator.

**If asked for the key line:** `idle_reconnect_due(...)` at `bt_alert_receiver.py:56–57` checks the restore SSID and elapsed time; the no-frame branch at `:262–270` forces a reconnect. The OS can still delay or fail radio association, so a timed-out handoff is a real failure status to report.

### 5:00–6:35 — Guided setup for a new user's room

> A Wi-Fi CSI model trained elsewhere cannot be assumed accurate in a new room. My setup flow asks for the room name, a 5–60 second capture interval, and the count that an operator actually observes: zero, one, or two people. The operator changes the label when the count changes. If nobody supplies a count, the rows remain unlabelled; a model prediction never becomes ground truth.
>
> In `room_capture.py:96–111`, `start` validates the room, interval, and label and creates a session. In `:113–127`, changing a label records that operator provenance and resets the next capture time. The API controls at `csi_count_api.py:204–244` are local dashboard controls. Only a complete finite **100-frame × 50-amplitude** window is saved; `room_capture.py:139–165` also requires the interval to be due and the sequence to advance. Prediction, quality, source, RSSI, and the operator label are stored separately. This keeps the dataset useful for later independent-session validation.

**Live action:** On **Wi-Fi CSI Count**, show *Live ESP32* source, start a session with a real room name and the genuinely observed count, wait for a complete window, change the label only if the actual occupancy changes, then stop. If no people-count ground truth can be staged, leave the label blank and explicitly show `UNLABELLED`. A missing complete window means there may be zero saved windows; do not imply a session ID alone proves data capture. The displayed count can remain `UNKNOWN` if the live window is incomplete or out of the model's recorded range.

**Open:** `src/safesense/room_capture.py:96–165` and `src/safesense/csi_count_api.py:204–244`.

```python
if window.shape != (100, 50) or not np.isfinite(window).all():
    raise ValueError("capture requires a finite 100-by-50 CSI window")
# Stored columns keep label_count / label_source separate from predicted_count.
```

### 6:35–7:45 — Raw packet journal and export provenance

> Packet capture and saved model windows are different data. `csi_count_api.py:267–304` validates incoming packet lines, journals accepted packets, keeps the rolling 100-frame buffer, and saves a room window when due. Wi-Fi UDP and Bluetooth SPP use the same local packet API, with source labels `ESP32_WIFI` and `ESP32_BLUETOOTH`; Bluetooth carries CSI captured by the ESP32 Wi-Fi radio, it does not measure CSI itself.
>
> Users can download readable `room-windows.csv`, detailed `csi-packets.csv`, wireless sensor and NVS queue CSVs, or the SQLite CSV ZIP. `export_api.py:165–192` puts all 128 signed raw I/Q values in a packet row **only when the board actually transmitted protocol-v2 full I/Q**. Earlier selected-only packet records stay selected-only; we do not fabricate missing raw values. `:300–318` describes readable and raw backup views inside the ZIP. For model training, `room_capture.py:175–197` exports `.npz` with `amplitudes`, `operator_labels`, and `model_predictions` as separate arrays. An unlabelled window exports `-1` as its label sentinel.

**Live action:** Download one CSV and point to `received_at_utc`, `source`, `label_source`, `full_128_iq_available`, and `source_format`. Do not project contact lists or bot secrets. To show the model-ready archive, use an existing completed session ID:

```powershell
$env:PYTHONPATH='src'
.\.venv\Scripts\python.exe -m scripts.export_room_csi SESSION_ID --out data/live/review_room.npz
```

**Open:** `src/safesense/csi_count_api.py:267–304`, `src/safesense/export_api.py:165–192`, `src/safesense/room_capture.py:175–197`, and `scripts/export_room_csi.py:11–24`.

### 7:45–8:45 — Telegram voice as the final optional hop

> On the Forecast or Alerts page, a scenario warning now sends a spoken forecast to the configured owner account automatically. `sos_voice.py` builds a message with room, channel, lead time, verification step, action, and event ID; it synthesizes speech, encodes audio, and submits it to Telegram. Real physical alerts and synthetic scenario voice keep separate provenance. A stable scenario event ID prevents repeated messages across refreshes or adjacent warning minutes; an offline dashboard retries while it stays open. The voice database records Telegram's returned message ID and leaves an ambiguous network result as `OUTCOME_UNKNOWN` for manual review.
>
> On October 21, the forecast page sent one scenario voice automatically, Telegram accepted it, and a repeat request returned `DUPLICATE` with no second send. That proves Telegram accepted the post, not that someone listened or acted. A physical sensor-triggered forecast-to-contact run still needs a fresh end-to-end test.

**Open:** `scripts/sos_voice.py:63–80`, `:106–123`, `:150–209`. If another member owns the forecast scenario explanation, keep this section to 30 seconds and hand them the screen.

### 8:45–9:25 — Close and handoff

> My contribution connects the physical event to durable, inspectable records and gives a new room a practical collection path. For every live claim I can show an ID, source, and timestamp. The remaining work is to collect independently labelled sessions in the target room, validate the CSI model there, and run a continuous physical sensor-to-forecast-to-contact test. Until those checks pass, `UNKNOWN` and unlabelled records are honest outputs, not failures to hide.

## Three debugging stories to rehearse

1. **Silent SPP after restart:** Process heartbeat remained, frames stopped. Compared fresh event IDs/timestamps; reopened COM; added idle and dashboard-requested reconnect (`bt_alert_receiver.py:247–270`, `live_api.py:218–249`).
2. **Windows AP transition:** `netsh connect` could return before the SSID actually changed. Added scan retries, association retry, actual-SSID check, bounded visit, and `finally` restoration (`wifi_demo_session.py:55–112`, `:172–204`). A failed association is reported as failure.
3. **Dataset honesty:** Early CSI records held only 50 selected I/Q pairs. Protocol v2 carries 128 raw values; export marks `FULL_128_RAW_IQ` or `SELECTED_50_IQ_ONLY`, and leaves absent raw data blank (`export_api.py:165–192`). Operator labels stay distinct from model predictions (`room_capture.py:175–197`).

## Reviewer questions and short answers

| Reviewer asks | Answer |
|---|---|
| “Bluetooth is paired. Does that prove data arrived?” | No. Show a new `DATA` event ID in the laptop journal and the matching backend receipt. Pairing and heartbeat do not prove frames are flowing. |
| “What if FastAPI is down?” | The laptop journals the sensor record before ACK, then keeps `backend_stored=0` and retries. Board ACK means laptop storage, while backend receipt is checked separately. |
| “Can duplicate sends create duplicate events?” | Same ID and same payload are accepted as a duplicate; reused ID with different payload is rejected by the laptop. Backend also deduplicates by event ID. |
| “Does 0/16 on the dashboard prove the queue is empty now?” | Only if the board's status observation is fresh. The card marks observations older than 45 seconds stale. Laptop receipt alone does not tell us current NVS depth. |
| “Why does the Wi-Fi switch sometimes fail?” | Windows and ESP32 share an association step; a connect request does not equal a connected SSID. We verify the SSID, report failure, and restore the saved laptop network. |
| “Where do labels come from?” | An operator supplies actual 0/1/2 occupancy during capture. Blank means unlabelled, and a model prediction is stored in a separate field. |
| “Why is live count UNKNOWN?” | It may lack a complete valid window, or the signal may be outside the recorded model domain. We need target-room labelled sessions and independent-session evaluation before claiming accuracy. |
| “Are all exported CSI packets full raw data?” | No. Protocol-v2 packets can contain all 128 I/Q values. Older packets retain only the 50 selected pairs and are marked accordingly. |
| “Does Telegram success mean a person was warned?” | It confirms API acceptance and a message ID. It does not confirm playback, reading, or action. |
| “What is the largest delivery outage you can survive?” | The board NVS queue is bounded at 16 records. It can fill; we do not claim unlimited buffering. |

## Live-demo fallback

If the AP does not associate, show its actual failure status, restore `Amrita`, then show a fresh Bluetooth event **only if one arrives**. If neither route is fresh, trace a previously stored event ID and state its timestamp. If the CSI collector does not complete a window, demonstrate the room controls and an existing saved session/export; do not invent a new labelled sample. If Telegram or internet is unavailable, show the implementation and previously recorded acceptance state without promising a new message. The demonstration succeeds as a code review when every evidence boundary is stated accurately.

## Verification performed while preparing this script

On 21 October 2026, the Python suite excluding the known local GCC launcher failure passed: **103 tests passed, 1 deselected, 2 dependency deprecation warnings**. A physical 120-second Wi-Fi visit then connected to the ESP32 AP, sent 2,852 CSI probes, restored `Amrita`, and produced fresh Wi-Fi and Bluetooth backend receipts. The dashboard showed the transition log and `READY` handoff. Telegram accepted one automatically sent scenario voice; playback was not verified. These checks do not establish target-room count accuracy or a physical sensor-triggered forecast alert.
