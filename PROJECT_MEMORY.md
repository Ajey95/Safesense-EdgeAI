# SafeSense project context

## Approved hardware and architecture

The project targets exactly one BME680, two ESP32-S3 boards, resistors, LEDs, and a buzzer.

- Node 1: BME680 custom I2C driver, relative gas policy, SoftAP, sensor LED, and 50 Hz protected environment/probe packets.
- Node 2: CSI capture and preprocessing, guarded TinyML adapter, deterministic fusion, three status LEDs, buzzer, NVS transition queue, and MQTT delivery.
- Laptop: broker, bridge, FastAPI, SQLite, and Streamlit.

## Safety invariants

- `UNKNOWN` is never equivalent to `VACANT`.
- Critical environmental risk remains `INCIDENT` even with stale or missing CSI.
- Missing/invalid evidence is `UNAVAILABLE` or `DEGRADED`, never fabricated zero or normal.
- BME680 gas resistance is not BSEC IAQ, gas identity, ppm, or certification.
- Records are persisted before publish and removed only by an exact accepted ACK for the same ID.
- The current INT8 candidate is release blocked; default firmware inference returns `UNKNOWN`.

## Verification snapshot — 2026-09-22

- Python: 25 tests passing.
- Portable C: 7 suites passing.
- Target builds: Node 1 and Node 2 compile for `esp32s3` with ESP-IDF 6.1; images are 781,520 and 899,840 bytes respectively.
- MQTT: local broker on port 1884 completed publish → bridge → API/SQLite → exact `ACCEPTED` ACK.
- Dashboard: live page inspected; software-generated telemetry is labelled `SOFTWARE TEST`, unavailable hardware stays `UNKNOWN`/`UNAVAILABLE`, the incident list is bounded, and no internal instructions are displayed.
- This software-only snapshot was superseded by the first transmitter hardware check below.

## First transmitter hardware check — 2026-09-22

- One ESP32-S3 was detected as Espressif USB Serial/JTAG on `COM9` and identified as revision v0.2 with 4 MB flash and 2 MB PSRAM.
- Node 1 flashed successfully with verified image hashes and booted ESP-IDF 6.1.
- The `SafeSense-V2` SoftAP started on channel 6 with DHCP at `192.168.4.1`.
- The BME680 did not acknowledge either valid I2C address. Runtime evidence reports no response at `0x76` or `0x77` on SDA GPIO 8 / SCL GPIO 9, so sensor readings remain unavailable until power, pins, I2C mode, and pull-ups are corrected.

## First receiver hardware check — 2026-09-22

- The second ESP32-S3 was detected on `COM10` as revision v0.2 with 16 MB flash and 8 MB PSRAM.
- Its previous Arduino fan-test image was replaced by the freshly built Node 2 image at revision `7d2fe1f`; bootloader, partition table, and the 899,840-byte application all passed flash hash verification.
- Node 2 booted ESP-IDF 6.1, identified itself as `safesense_node2_csi_gateway`, and restored an empty persistent event queue successfully.
- The live run stopped at the explicit 30-second Node 1 connection gate because `SafeSense-V2` was unavailable. CSI capture, output GPIOs, and MQTT therefore remain unverified until Node 1 is powered and broadcasting during the receiver boot.

## Joint two-board check — 2026-09-22

- With both boards powered, Node 1 created `SafeSense-V2` on channel 6 and Node 2 joined at RSSI -41 dBm, received `192.168.4.2`, and registered with Node 1. The two-board Wi-Fi and UDP path is physically verified.
- Node 1 still reports `BME680_ERR_BUS` and no acknowledgement at either `0x76` or `0x77`; environment data remains unavailable.
- Node 2 entered `DEGRADED` with reason `ENVIRONMENT_UNAVAILABLE`, preserving the safety state instead of reporting a normal system.
- Board-to-laptop MQTT remains blocked: the laptop was on `amritanet.edu` at `10.12.114.40`, not the `192.168.4.x` SoftAP network, while Node 2's configured broker URI was `mqtt://192.168.4.2` (its own assigned address).
- The live logs also exposed two software follow-ups: Node 1 logs the repeated registration token at the 50 Hz probe cadence, and Node 2's zero-initialized pre-window activity is printed as `VACANT` with confidence `0.00` even though fusion correctly remains `DEGRADED`. The displayed activity must be initialized/reported as `UNKNOWN` before a valid CSI window.

## Laptop-on-SoftAP MQTT check — 2026-09-22

- The laptop joined `SafeSense-V2` as `192.168.4.3` while retaining internet through `Ethernet 2`; Node 1 at `192.168.4.1` and Node 2 at `192.168.4.2` were both reachable.
- Mosquitto listened on `0.0.0.0:1884`, and Node 2 was rebuilt/flashed with `mqtt://192.168.4.3:1884`; the flash hash verified and a TCP session from `192.168.4.2` reached the broker.
- A clean bridge instance passed the broker -> API -> exact ACK smoke test, but the physical Node 2 queue did not drain. The device published a real `esp32s3-v2` event, then later reported `No PING_RESP` and reconnected without a hardware event reaching the API.
- This is partial MQTT evidence only: network routing and broker reachability pass, while the physical exact-ACK drain and MQTT connection stability remain failed acceptance gates. The receiver's immediate subscribe-then-publish sequence is a suspected first-connect ACK race and needs an instrumented firmware fix before claiming end-to-end success.

## Reliability fixes and physical recheck — 2026-09-22

- Final automated verification after the reliability and stale-dashboard fixes: 28 Python tests and 9 portable C suites pass; both ESP32-S3 applications build with ESP-IDF 6.1.
- Node 2 now waits for the matching MQTT ACK subscription before publishing, allows one persisted record in flight, and retries the exact queue head after a 5-second application-ACK timeout. Physical logs verified subscribe → publish → exact accepted ACK, queue drain, and a connection that remained established for more than two minutes.
- The laptop bridge now restores its wildcard event subscription from the MQTT `on_connect` callback after every broker reconnect. This fixed the observed case where a restarted broker left the bridge connected but silently unsubscribed.
- Live receiver telemetry reached the API every 5 seconds with MQTT `CONNECTED`, physical CSI windows ready at about 50 packets/s, and activity `UNKNOWN`. `UNKNOWN` replaces the earlier false pre-model `VACANT` display.
- A transmitter restart exposed a retained receiver sequence counter that rejected the transmitter's reset sequence indefinitely. The protocol now accepts a new sequence epoch only when sender uptime rolls backward, while retaining ordinary duplicate rejection. Host tests and both ESP-IDF target builds pass for this fix.
- Node 1 was flashed on `COM9` with the current image and verified hashes. Repeated peer registration logs are now emitted only when the peer is new or its address changes.
- The latest Node 2 sequence-epoch image is built but not yet physically flashed because its former `COM10` USB serial device is absent from Windows enumeration. The receiver can continue running its prior image over Wi-Fi, but this final device acceptance remains pending until USB is reconnected.
- The BME680 electrical gate is unchanged: no acknowledgement at `0x76` or `0x77` on GPIO 8/9. The TinyML adapter remains `DISABLED_RELEASE_GATE`; no activity class is claimed without a released model.
- Dashboard telemetry older than 15 seconds is now fail-closed: it shows `STALE DATA`, changes connectivity/output claims to `UNKNOWN (STALE)`, hides stale sensor/CSI values, and reports the data age. Desktop and 390×844 browser checks pass with no current console errors or internal-instruction text.

## Reviewer entry points

- `docs/review_readiness.md` — rubric evidence matrix.
- `docs/review_demo.md` — exact demonstration sequence.
- `docs/reviewer_qna.md` — technical Q&A.
- `docs/progress.md` — verified versus pending status.

Never store Wi-Fi, MQTT, GitHub, or other credentials in this file or the repository.
