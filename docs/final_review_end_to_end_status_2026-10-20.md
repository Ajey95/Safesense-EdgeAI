# SafeSense end-to-end check — 2026-10-20

This check uses the connected classic ESP32 on COM11, paired Bluetooth COM15, the local FastAPI server, and the owner's configured Telegram bot. A successful component test is not evidence of validated room occupancy or hazard detection.

| Area | Result | Fresh evidence and limit |
| --- | --- | --- |
| Backend and dashboard | Working locally | `/health` returned `ok`; all nine dashboard sections rendered without browser errors. The five-step review flow rendered problem, live hardware, CSI, forecast, and alert screens. |
| BME680 and pressure | Working in this session | Board and backend reported fresh healthy samples around 30 °C, 70% RH, 97,638 Pa, and 35,511 Ω, with matching event IDs. The user clarified that MQ-135 is not installed today; its 0 raw ADC is expected and is not a failed test of the separate module. |
| USB sensor and CSI bridge | Working in this session | COM11 reader remained running and continued journaling physical sensor events. |
| Wi-Fi transport switch | Working in this timed check | A 45-second ESP32 AP visit sent 902 CSI probes, produced physical Wi-Fi backend receipts, drained the TX queue, and restored the laptop to `Amrita`. Windows connection and restoration took additional time; zero-delay switching is not established. |
| Bluetooth sensor fallback | Working after listener restart; recovery gap | The prior COM15 listener kept reporting a fresh heartbeat but stopped receiving samples; TX NVS reached its 16-record limit. Restarting the listener restored exact-ID SPP ACKs and drained the queue to zero. Automatic recovery from this silent stale connection is unverified. |
| Timed CSI capture and label controls | Collector working; no verified room labels yet | An unlabelled audit session saved six complete 100×50 windows at 5-second intervals during the AP visit. Start, stop, label change, persistence, and export tests passed. No 0/1/2 ground-truth captures were made in this check because the actual count was not supplied. |
| Live CSI people count | Not validated | The six fresh audit windows all had `OUTSIDE_RECORDED_SIGNAL_RANGE`; the model withheld a count. With the laptop back on Amrita there are no fresh CSI packets, so the dashboard shows `UNKNOWN`. The 85.65% baseline is from later windows of the same recorded sessions and is not a new-room result. |
| Forecast scenario | Working as a synthetic demonstration | The default cold-storage episode predicted a temperature crossing at +25 minutes; the dashboard and API agreed. |
| Real sensor-triggered forecast | Not testable with today's hardware | Firmware contains the 61-sample, 60-minute history and TinyML inference path, but `update_forecast_history` clears history when MQ-135 is unhealthy or its signal is zero. MQ-135 is not installed today; occasional near-zero ADC noise can still pass the current `> 0` check, so that check alone does not prove a connected sensor. The synthetic model has not been validated for physical hazards. |
| Telegram voice | Scenario delivery working | One new synthetic forecast scenario voice was accepted by Telegram for the sole configured contact: event `scenario-519402f1-b111-4e37-8239-d1cb8d6b995c`, message ID 7, journal state `ACCEPTED_BY_TELEGRAM`. Playback and a real sensor-triggered voice alert were not verified. |
| Firmware and software checks | Passing with configured toolchain | ESP-IDF 6.1 TX build completed. The full Python suite passed 79 tests; seven C host test programs passed; JavaScript syntax and the live CSI UI test passed. The first GCC run failed because the MSYS2 UCRT directory was late in `PATH`; prepending `C:\msys64\ucrt64\bin` made the complete checks pass. |
| E-drive CSI dates | Reconstructed files verified | Both extracted E-drive copies had all eight CSV hashes match their reconstruction manifests. Dates span 2026-09-25 to 2026-10-18 and are explicitly reconstructed, not exact capture dates. The redundant extracted folder remains because an earlier automatic approval review blocked deletion. |
| Implementation-only handoff | Out of date | `implementation_only/` lacks `src/safesense/room_capture.py`, and sampled CSI/SOS/dashboard files differ from current source. Refresh the minimal copy and ZIP before handing it off. The working tree is also not committed. |

## Gates before claiming every feature is finished

1. Connect the MQ-135 module, verify a nonzero and varying raw ADC signal, then accumulate 61 valid one-minute readings and verify a safe, controlled real-input forecast path. Do not create hazardous conditions.
2. Collect operator-confirmed 0/1/2-person CSI sessions in the target room; train and evaluate on independent sessions before displaying a live count.
3. Make the Bluetooth listener detect and recover from a silent stale SPP connection, then repeat the Wi-Fi-to-Bluetooth switch without manually restarting the listener.
4. Verify the physical alarm outputs and a real sensor-alert-to-contact event separately from the synthetic scenario, if those are final-review requirements.
5. Refresh the implementation-only bundle and keep source, model assets, and demo instructions together for handoff.

No claim of 100% accuracy or production safety readiness is supported by this check.

## Fresh recheck later on 2026-10-20

- The backend health endpoint returned `ok`; the live hardware dashboard displayed fresh BME680 readings and exact-ID Bluetooth/backend receipt. The forecast dashboard displayed five synthetic channels and a +25-minute temperature breach in the selected held-out scenario.
- A new bounded Wi-Fi visit connected to `SafeSense-TX-Laptop`, sent 998 CSI probes, stored four physical `DIRECT_WIFI` events among the 20 most recent delivery events, and restored the laptop to `Amrita`. Bluetooth continued to store physical sensor events after the switch.
- The new unlabelled room capture session `1bf78434-1602-4fd8-930b-a16349b06440` stored seven 100×50 windows at five-second intervals. All seven had `OUTSIDE_RECORDED_SIGNAL_RANGE` and no prediction. After the AP visit, live CSI correctly returned `UNKNOWN` / `NO_FRESH_LIVE_CSI`.
- The full Python suite passed 79 tests; seven C host test programs and the live CSI UI test passed. The forecast API returned five channels, six horizons, and the expected synthetic breach. The existing owner voice event remained `ACCEPTED_BY_TELEGRAM` (message ID 7); no new voice was sent during this recheck.
- The user clarified that MQ-135 is not connected today. Its live ADC values near zero (including a later raw value of 5) do not establish whether the module works when installed. Physical forecast history, a real sensor-triggered alert, new-room CSI accuracy, and automatic recovery from a silent stale Bluetooth connection remain unverified.
- The actual dashboard **Use ESP32 Wi-Fi for 45s** button was pressed in a later check. Its bounded visit connected to the AP, sent 1,057 CSI probes, stored physical Wi-Fi events, and automatically restored `Amrita`. After return, the Bluetooth receiver log journaled the same fresh physical event ID seen by the backend (`tx-10ef78d0c26ce3fa04b09427`); the backend displayed `USB_SERIAL` for that event because USB had stored it first. The separate **Return to Amrita · Bluetooth** button was not directly exercised while the AP was active; it was disabled once automatic restoration completed. This check does not remove the earlier silent stale Bluetooth listener recovery gap.
