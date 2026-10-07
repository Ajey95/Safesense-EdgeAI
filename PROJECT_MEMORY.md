# SafeSense Software Context

## Forecast dataset card timing and preparation — 2026-10-06

The published `Ajeya95/environmental-forecast-v1` card now includes the verified
600/160 episode and 90,600/24,160 row split, relative one-minute index
0–150, channel bounds, four-decimal CSV export, Parquet validation, and the
distinction between published rows and trainer-only scaling. The card upload
is Hugging Face commit `b369e25fdcba3310138816ec4db4b9ae94a329b7`;
public readback matched `huggingface/environmental-forecast-v1/README.md`
byte for byte. The generator's room labels are scenarios, not physical
collection locations, and no collection dates or measured sampling interval
exist for these rows. The user's pasted physical-recordings draft was not
published because it described the generated train/test rows as sensor
recordings.

## Formula and architecture slides — 2026-10-06

The current 20-slide final-review deck is
`output/presentations/SafeSense_Final_Review_Presentation_2026-10-06_v6.pptx`.
Slide 7 explains the seeded synthetic generator's five channel formulas and
760-episode train/test split. Slide 13 embeds the corrected GPT-generated
architecture image from `docs/architecture-assets/safesense-architecture-gpt-2026-10-06.png`:
one sensor ESP32, Wi-Fi to a laptop, and Bluetooth Classic SPP alert fallback
to the same laptop. Delivery/status slides now reflect the later physical
check in `docs/direct_laptop_transport.md`: real BME680/MQ-135 Wi-Fi events
and a labelled Bluetooth transport test had matching laptop receipts. Those
checks do not validate real-room forecast accuracy or confirmed speech.
The 16-record TX queue filled during the Bluetooth test, so urgent-event
retention across long outages remains open. The deck passed package, layout,
font, native-chart, and Artifact Tool import validation, and all 20 slides
were rendered for visual review. Earlier sections below describe prior
snapshots and may state older route status.

## Cited forecast dataset card and review slides — 2026-10-06

The dataset at `Ajeya95/environmental-forecast-v1` is the project-generated synthetic forecast export: its manifest, compressed CSV, and train/test Parquet SHA-256 values match the local release. Its user-edited README incorrectly said every reading was captured. The card was replaced at Hugging Face commit `47a8d31afae1e59ed4ee8526e9f3762f171d5e47` with explicit synthetic provenance, operational-source citations, sensor limits, and the new repository ID; public readback matched the local card by SHA-256. `README.md` and `docs/forecast_lab.md` now link to that dataset. The 18-slide final-review deck is `output/presentations/SafeSense_Final_Review_Presentation_2026-10-06_v4.pptx`; slides 16–17 explain the published scenario rationale and the remaining real-room validation gate, with direct source links in speaker notes. Presentation package, layout, font, chart, and import checks passed. No physical forecast accuracy is claimed.

## Scenario dashboard audit and route labels — 2026-10-06

All eight held-out synthetic scenarios load in the dashboard. At default seed
17, `bakery_restart` and `server_airflow` can show no crossing at reviewed
minutes; after reveal the page calls these confirmed no-breach controls when
the simulator agrees. `bakery_cooling` at minute 110 exposes a genuine model
false alert. The page now names false alerts and missed breaches explicitly,
without changing the dataset, model, or evaluation data. Simulated delivery
labels follow the single-board ESP32 → laptop Wi-Fi/Bluetooth plan; the
optional two-board TX replay is identified separately. Physical direct-laptop
delivery remains unverified. Chrome browser smoke covered all eight scenario
selections and the reveal/fault controls; `tests/test_forecast_demo.py` passed
7 tests and `node --check web/forecast/app.js` passed.

## Final review presentation — 2026-10-06

Created a 16-slide PowerPoint in
`output/presentations/SafeSense_Final_Review_Presentation_2026-10-06_v3.pptx`.
It explains the 70→48→24→30 synthetic environmental forecast, the laboratory
closed-room use case, the held-out trend comparison, the unreleased Wi-Fi CSI
activity experiment, Bluetooth and voice receiver software, and a concrete
final-review plan. The plan follows the latest single-board choice: real
ESP32 sensor history and on-device inference, Wi-Fi delivery directly to the
laptop, Bluetooth fallback to that laptop, exact event-ID receipts, and an
audible speech check. These final-review route steps remain planned and must
not be presented as achieved by the current physical direct-USB stream.
Sources and limitations are in slide speaker notes. The artifact finalizer
passed package, layout, font, import, and native-chart checks; all 16 slide
renders were visually reviewed.

## Live refresh diagnosis — 2026-10-05

The Live Hardware **Refresh now** control reads current backend records. It
could not produce a new physical sample after COM12 disappeared from Windows;
the running direct USB bridge kept retrying that missing port. COM11 was then
verified as the same sensor board by ESP32 MAC `8c:94:df:90:1f:ec` and live
BME680/MQ-135 JSON output. The old bridge was stopped and a new bridge started
with `--port COM11`; changing physical values again reached FastAPI/SQLite and
the page showed LIVE USB READING. The refresh control now shows a timed result,
explains when no newer sample exists, and queues a manual check if an automatic
poll is in progress. Desktop and mobile browser checks verified the stale-state
feedback with no page errors. Future COM remaps require verifying the board ID
and updating the bridge's `--port` setting.

## Single-board direct live sensor route — 2026-10-05

The user switched scope from two-board TX→RX delivery to showing the currently
connected sensor board directly in the dashboard. The sensor ESP32 MAC is
`8c:94:df:90:1f:ec` (COM12 initially, COM11 after re-enumeration). It runs
its physical BME680/MQ-135 JSON streaming firmware at 115200 baud; it was not
reflashed. The new
`scripts/direct_serial_bridge.py` reads and validates its JSON, converts
pressure hPa→Pa, retains MQ-135 as raw ADC, and POSTs an exact `usb-...`
sample ID every ~2 seconds to the existing local `/api/v1/telemetry` endpoint.
`web/forecast/live.js` merges backend-stored direct samples from
`/api/v1/overview` with the RX-specific live API and renders a clearly labeled
**DIRECT USB** route. It shows stale after 45 seconds without a new stored
sample. A browser check saw `LIVE USB READING`, all five sensor fields, ten
history rows and no page errors; the bridge continued storing changing values.
Focused direct-bridge/live API tests passed (7). No second board, Wi-Fi RX ACK,
Bluetooth delivery, TinyML forecast, or SOS receipt is implied by this mode.

The other board was previously COM11, MAC `8c:94:df:90:dd:4c`. COM port labels
do not identify a board across reconnects. Before the scope change,
both 4 MB flash images were backed up under
`output/hardware-backups/2026-10-05/` and the RX SafeSense image was flashed
to COM11 with hash verification. It booted its AP but restored 16 old pending
records; the laptop briefly connected to the AP. The RX bridge was stopped,
the laptop returned to its ordinary Wi-Fi, and COM11 later disappeared from serial
enumeration. The original RX image remains available for restoration if that
board is reused elsewhere.

## Live hardware check — 2026-10-05

The user connected two USB serial devices. Windows enumerated CP210x adapters
on COM11 and COM12. A bounded 115200-baud read of COM12 yielded changing
JSON sensor samples with `sensor_status: "OK"`; one sample reported BME680
temperature 33.623 °C, humidity 65.955%, pressure 978.009 hPa, gas resistance
305607.719 Ω, and MQ-135 raw ADC 2505. This confirms a physical serial sensor
stream, not calibrated gas concentration or end-to-end SafeSense delivery.
COM11 repeatedly printed only `,"event_changed":false}` fragments, which did
not identify it as the expected RX gateway. The laptop remained on its ordinary
Wi-Fi network; a scan did not show `SafeSense-RX-V1`. No RX HTTP bridge or
Bluetooth listener process was running, and `/api/v1/live` returned no event,
Bluetooth receipt, or bridge heartbeat. Both serial ports were closed after
the read. Do not describe the Live Hardware dashboard as receiving physical
TX→RX telemetry until the intended firmware, RX AP, bridge, and exact-ID
receipts are observed. No firmware was flashed in this check.

## 60-percent interim review preflight — 2026-09-30

The user has an interim review on 2026-10-01 and says the milestone is about
60 percent of the entire project, with no itemized percentage rubric supplied.
Present the implemented V1 chain as the milestone: custom BME680 sensing,
TX/RX NVS persistence with exact ACK, CSI diagnostic preprocessing, local
FastAPI/SQLite ingestion, and the Streamlit evidence view. The released model,
human count, animal exclusion and analog MQ-135 validation remain future work;
do not assign a fabricated numeric completion score to these modules.

Fresh preflight on 2026-09-30: `.venv/Scripts/python.exe -m pytest -q`
passed 31 tests with two deprecation warnings; `mingw32-make -C firmware/tests
test` passed all seven C host programs. Local API `/health` returned HTTP 200,
but the dashboard was not running on port 8501 and `Win32_SerialPort` listed
no present serial boards. The last physical TX/RX and dashboard evidence is
dated 2026-09-24 in `docs/evidence/`; do a fresh hardware preflight before
claiming a live demo on review day. If boards remain absent, show the dated
recorded evidence and host tests, clearly labelled as such. Use
`docs/r1_live_demo.md` for the bounded review sequence; avoid older V2/MQTT
instructions in `docs/progress.md` for the current V1 path.

The user clarified that the reviewer expects CSI activity output and human
count/animal exclusion, beyond a telemetry dashboard. Both ESP32 boards, the
intended room, and two people are available for recording today; animal-only
and human-plus-animal scenes are unavailable. Therefore prioritize a bounded
target-room 0/1/2-person CSI experiment and single-person activity, with raw
frame export and laptop inference as new implementation work. The current RX
exports diagnostic counters but no labelled raw CSI stream, so data collection
cannot begin from the existing API alone. Keep complete recording sessions
apart for evaluation and use a fresh held-out review-day session. Treat
unsupported or failed count/activity outputs as experimental/UNKNOWN.
Animal exclusion remains unvalidated until animal-only and mixed-scene data
can be collected; public pet-only data cannot prove mixed-scene performance.

## Training data and challenge refresh — verified 2026-09-29

User asked what data is available to train the model and what the challenges
are. Rechecked the local data tree, WISDOM trace hashes, cache headers, saved
candidate manifest, preprocessing and author dataset pages. WISDOM remains the
only labelled CSI activity dataset in this workspace: 26 trace files, 24 unique
contents, six labels and four locations. The derived cache has 9,829 windows
of shape 100 x 48 (5,503 train / 2,499 validation / 1,827 test); these are not
independent recordings or new data. No WiMANS payload was found locally.

WiMANS remains the recommended external count/activity replay source; ESP-Fi
HAR and Home HAR support activity experiments, CSI-Bench supports a separate
motion-source task, and EHUCOUNT/WiVi32/ESP32-S3 occupancy are counting sources
with differing access and hardware constraints. No reviewed source establishes
the complete joint human-count/activity/mixed-human-pet requirement on our
hardware. Principal challenges are room/device transfer, missing joint labels,
stationary versus empty confusion, recording leakage, matching preprocessing,
and edge deployment. Saved candidate metrics remain 0.31148 accuracy and
0.32587 macro-F1; those saved results were inspected, not reproduced today.
No dataset download, training, service startup or device operation occurred.

## Existing implementation search — verified 2026-09-28

User requested repositories that already implement our work. Source review is
saved in `docs/csi_existing_repository_audit_2026-09-28.md`. WiMANS contains
real training code for identity/location/activity but no committed checkpoints
or dedicated count task; retain it as the primary framework and add bounded
count output. SenseFi links pretrained activity weights, not a multi-person
counter. Wi-Fi Vision has a 3.86 MB pose checkpoint and dashboard, needs three
ESP32 boards, and labels low motion Empty Room in live heuristics; do not reuse
that vacancy logic. The ESP32-S3 occupancy thesis reports 52.4% balanced
accuracy for exact 0–3 count, includes only sample data, and has no committed
checkpoint. WiVi32 complete data/code require an access request. CSI-Bench
provides task code rather than a committed joint count/activity/pet model.
RuView contains count artifacts, but current v0.0.2 results are 62.3% eval
accuracy on counts 0/1 only (random split); older component docs describe a
degenerate v0.0.1 counter. No verified 2+ count capability follows. No repo
code/checkpoint was run or adopted; no datasets/models downloaded or author
contact made. Main public-data scope and evidence requirements remain intact.

## Public-data scope decision — 2026-09-28

User requested a final dataset decision and what can be achieved "100%".
Recommended scope is saved in `docs/csi_final_scope_2026-09-28.md`:
WiMANS is primary for a held-out recorded-CSI demo with bounded 0/1/2 human
count plus room-level activity labels; existing WISDOM is the activity-only
fallback. Defer other new datasets and animal discrimination for the two-day
deadline. Count and activity predictions must be actual inference, with
ground truth separate. No per-person assignment, 3+ rejection, arbitrary-room
or live ESP32 accuracy is promised. 100% accuracy is not guaranteed; access,
archive/resource feasibility and held-out performance remain unverified.
If WiMANS is blocked, use WISDOM replay without a counting claim. This is the
current public-data scope recommendation and supersedes target-room collection
as the immediate path. No download or training has started in this decision
turn, and no capability is marked achieved.

## External dataset search — verified 2026-09-28

User requested GitHub and other public datasets after the local inventory.
Source/access-route findings are saved in
`docs/csi_public_dataset_search_2026-09-28.md`. No new dataset payload,
training or execution of third-party code occurred. ESP-Fi HAR is an
ESP32 activity expansion candidate (seven dynamic activities, four rooms;
615 MB Git LFS archive). WiMANS best matches count plus simultaneous
activity on recorded data (0–5 users, 11,286 samples; Intel 5300 capture).
CSI-Bench has Human/Pet/IRobot/Fan labels in its separate motion-source
task; current author README points to corrected Kaggle Version 12.
The motion-source capture described by the paper uses NXP 2 x 2 hardware,
and non-human recordings are collected without humans present. It does not
prove mixed human/pet counting on ESP32. Home HAR uses ESP32-C6 with seven
home activity labels and separate sessions. UT-HAR, NTU-Fi HAR, a small
ESP32 spectrogram dataset on Zenodo, EHUCOUNT and Widar3.0 are also linked.
Only WISDOM remains confirmed local. Recommend WISDOM/ESP-Fi HAR for
ESP32-oriented activity work, or WiMANS for a separately evaluated replay
demo of count and activities. No full joint count/activity/animal-exclusion
dataset or ready-to-deploy model was verified. These findings expand the
available public-data options; they do not change existing release gates.

## Local dataset inventory — verified 2026-09-28

Latest user request is to identify data already available for training without
collecting new recordings. No new download or training was started for this
audit. WISDOM is the one real labelled CSI activity dataset on disk, stored
under both `data/public/wisdom/human_activity_recognition` and
`data/public/wisdom_har`; these are copies of the same dataset, not independent
datasets. Each contains 26 trace files with 24 unique SHA-256 contents. The
two walking_fast aliases duplicate walking in lab and parking. Across copies,
24 of 26 matching file paths are byte-identical; do not claim all files match.

Original labels: empty, standing, sitting, sittingupdown, jumping, walking.
Locations: indoor lab/corridor and outdoor parking/yard. The cached
`data/cache/wisdom48_windows.npz` contains 9,829 real 100 x 48 windows:
5,503 train (12 recording groups), 2,499 validation (6 groups), and 1,827 test
(6 groups). These windows are derived from WISDOM, not extra recordings.
No labelled multi-human-count or animal/human discrimination dataset was
found in the current data assets. Empty versus occupied activity labels can
support a presence experiment, not general exact human counting.

The physics augmentation generator is available but produces synthetic data;
it cannot supply independent human-count, pet-rejection or target-room proof.
The 54 current-measurement CSVs are ESP32 power measurements, not CSI activity
examples. Review SQLite databases contain telemetry, not labelled raw CSI.
The saved real-plus-synthetic three-class candidate still reports accuracy
0.31148 and macro F1 0.32587 on held-out lab recordings and is not released.
For conservative three-state training, use empty -> vacant, standing/sitting
-> stationary, walking -> walking; sittingupdown is dynamic and should not
be silently grouped with stationary. Without target-room collection, an
evaluated public-recording replay demo is feasible; live room performance,
multiple-person counts and animal exclusion remain unverified.

## CSI training scope and readiness — 2026-09-28

Final approach recommendation requested: the concrete proposed two-day design
is saved in `docs/csi_two_day_decision.md`. It uses existing V1 TX/RX boards,
USB raw-CSI collection, separate laptop Random Forest activity/count
experiments, and the existing local API/SQLite/Streamlit. Core motion,
environment and quality/event outputs are the priority; 0/1/2 count and
single-person activity output require separate proposed held-out gates.
The document is a reviewable recommendation, not achieved capability or an
approved production model. No implementation, training or flashing started.
Latest serial enumeration again returned no ports.
The written design alone was committed as `930167e` on `v1`; source changes
and the pre-existing working tree were not included. The user then said
`continue`, accepting progression from the written design, and subsequently
steered work to the local dataset inventory above. No new dependency was
installed and no device was contacted or flashed.

Latest deadline constraint: the user must show output in two days and wants
an impressive, useful demonstration. Recommendation is now to time-box work
around the existing V1 pair and local laptop/dashboard; the earlier radar
and multi-receiver strategy remains a longer-term option, not the immediate
delivery plan. This is a recommendation, not an approved implementation spec.

Proposed two-day core: live CSI amplitude/motion trend, measured signal
quality/freshness, motion/no-significant-motion/unknown state, existing BME680
temperature/humidity/pressure, and timestamped saved activity events. A
manually armed movement alert can demonstrate room monitoring, with no claim
that CSI motion alone distinguishes humans from pets or indicates danger.
Do not derive vacancy or human count from no motion. A target-room
vacant/stationary/walking classifier is a stretch feature only if separate
recording-session tests support it; saved public-data candidate is still
rejected. Exact people counts, per-person mixed activity and animal exclusion
remain longer-term goals unless real independent evidence is obtained.

Proposed schedule: first establish timestamped raw CSI export and matching
preprocessing, collect independent short takes at several positions, compare
motion/statistical-feature baselines and a small classifier on the laptop,
then test on fresh Day-2 takes, integrate the actual measured outputs, and
rehearse a live enter/walk/stop/leave plus signal-loss demonstration. Preserve
actual held-out metrics and a clearly labelled recorded replay backup. If
stationary-versus-vacant fails, retain the truthful motion output. No new
capture/training/firmware change has started; Windows serial enumeration
again returned no ports. Access to boards and intended demo room remains
necessary before physical work can begin.

Latest scope correction: the user wants the number of humans and their
activities, with animals excluded from the human count even when present.
This supersedes the initial three-state-only scope below. Maximum supported
human count, animal types, anonymous counts per activity versus individual
tracking, and acceptable hardware additions have not been settled. The
current three-class model cannot produce that expanded output.

Feasibility assessment: bounded people counting and human/non-human motion
discrimination have research demonstrations, but they do not establish the
combined capability on this V1 pair. One TX/RX link observes overlapping
human/animal channel effects; per-person simultaneous activity separation
and stationary occupancy are material risks. More spatial links can improve
observability but do not guarantee success. A proposed first experiment
would bound count (for example 0/1/2), report anonymous activity counts, and
include empty, animal-only, human-only, and mixed human/animal recordings.
These bounds are proposals, not accepted requirements or achieved outputs.
No new training, firmware changes or physical collection has been performed.

Strategy recommendation requested on 2026-09-28 (not yet approved as an
implementation design): for the complete camera-free goal, evaluate a
tracking-capable mmWave radar as the spatial/counting source, with CSI as
additional room-motion evidence. Radar target classification, stationary
people, occlusion and pet rejection still require actual acceptance tests;
a generic presence-only radar is not sufficient. If CSI-only is mandatory,
evaluate a multi-receiver prototype (one TX with spatially separated RXs;
three RXs is a proposed trial, not a proven optimum) and infer on the laptop
initially. The question of allowed hardware/sensors is pending user input.

Proposed first pilot: 0/1/2 humans and walking/stationary/unknown activity,
using synchronized raw recordings from empty, pet-only, human-only and mixed
human/pet scenes. Start with interpretable feature baselines, then a small
temporal multi-output model if evidence warrants it. Humans and pets must be
allowed to coexist in labels; do not hard-gate all human outputs with a
mutually exclusive human-versus-animal classifier. Freeze preprocessing and
split whole recording sessions/days before windowing. Report exact human
count accuracy, mean count error, activity-count errors, human misses,
pet-only false human detections, abstention coverage, and latency separately.
Unknown counts must remain unknown rather than default to zero. Expand to
new rooms, more people or embedded inference only after relevant held-out
evidence passes. These are proposed steps, not measured capabilities.

WiMANS is a useful multi-user benchmark/design reference, not a compatible
ready-to-deploy ESP32 model: its paper describes Intel 5300 3x3 antenna links,
30 subcarriers per link and nominal 1,000 packets/s, unlike this V1 capture.
Sources: https://github.com/huangshk/WiMANS and
https://www.ti.com/tool/TIDEP-01000 (radar counting/tracking reference).

Primary research checked for this assessment:
- Wi-CaL (2022), multiple ESP32 Wi-Fi links for counting/localization:
  https://doi.org/10.1109/ACCESS.2022.3155812
- Multi-person ESP32 gait-separation limitations (2026 preprint; this is
  gait identification, not direct proof that bounded counting is impossible):
  https://arxiv.org/abs/2601.02177
- Large-scale Wi-Fi sensing deployment study, pet false positives and
  multi-user interference (2025): https://arxiv.org/abs/2506.04322

Initially the user selected `vacant`, `stationary`, and `walking` as activity
states. `UNKNOWN` remains an inference fallback for missing, stale,
poor-quality or uncertain CSI; it is not an empty-room label. The intended
first result is room-specific occupancy/activity context from the existing
V1 two-board setup. A read-only Windows serial-port enumeration returned no
ports in this session; board availability remains to be confirmed. No
firmware was flashed and no new training was launched.

Current checkout is `v1`, with substantial pre-existing uncommitted work.
Read-only source inspection confirms that `node2_csi_gateway` queues raw
128-byte I/Q frames internally, builds masked diagnostic windows, and exports
CSI counters/quality metadata. It does not export labelled raw recordings or
invoke an activity model. Existing UART capture helpers select diagnostic
lines, not per-frame training samples. Target-room labelled recordings were
not found in the inspected data layout (`public`, `cache`, `review-qa`).

The saved `safesense3_fixed_real_plus_synth` manifest reports INT8 test accuracy
0.311483 and macro-F1 0.325867 on 2,090 real lab windows after corridor training,
with no validation partition. A fresh release-verifier invocation rejected
it with `release requires a trace-separated validation partition`; its
reported macro-F1 also falls below the existing 0.80 gate. These are saved
experiment metrics, not a new evaluation or live-device performance claim.

The next proposed design is labelled target-room capture, identical training
and inference preprocessing, whole-session train/validation/test separation,
a simple feature baseline followed by the existing small CNN, and INT8 plus
physical latency/memory verification before integration. Stationary occupancy
versus an empty room is a central acceptance risk; inspect per-class recall
and occupied-to-vacant errors as well as macro-F1. Different-room performance
requires a separately held-out room.

Before collection, settle the classic-ESP32 invalid-first-word policy:
the gateway currently zero-masks the affected +1 carrier in a 48-wide tensor,
whereas Python replay preprocessing rejects such frames. These diagnostic
windows are explicitly excluded from released inference today. Any new model
must version and validate a single matching carrier/mask contract on both
sides. Also preserve timestamps/source identity and measure actual sample
rate/dropouts; 100 frames represent about two seconds only at 50 valid Hz.

## Current V1 live status — 2026-09-24

Presentation handoff: `output/presentations/SafeSense_V1_Four_Members_No_Gas_Updated.pptx`
and `output/pdf/SafeSense_V1_Four_Members_No_Gas_Updated.pdf` contain 14
slides: a live-command cover, three slides per member (two implementation
slides and one recorded output slide), and R2 model training and validation.
The presentation keeps MQ-135 discussion only on its R2 slide. Slides 1-13
also omit gas-resistance fields, readings and gas-related demo commands.
Member 1's three slides show custom BME680 implementation, calibration block
parsing, and recorded temperature, humidity and pressure output. Its second
slide uses consecutive lines of our custom driver with I2C connections as
context.
The output slides use exact serial lines, a read-only SQLite extract, and a
copied Streamlit screenshot in `docs/evidence/`. The prior physical and delivery checks
are assigned to R1 closeout, and remain pending where not demonstrated.
The final PDF was rendered and checked for 14 pages,
readable custom BME680 code, working command structure, and absence of
internal grading text. The underlying live metrics are the specific
2026-09-24 observations below, not a guarantee that future runs match.

R1 demo update on 2026-09-24: `dashboard/app.py` with
`SAFESENSE_R1_REVIEW=1` preserves the detailed dashboard layout while showing
selected BME680 temperature/humidity/pressure, CSI, and delivery fields. It
omits the deferred analog channel from the view and does not alter stored data.
The header now identifies backend HTTP ingress; "Origin from API alone" remains
UNVERIFIED because the API cannot independently attest the physical board.
When a record becomes stale, the R1 page retains its last stored BME680/CSI
values with explicit stale labels. The two System node rows use the saved
TX/RX link report as REPORTED ONLINE while fresh and LAST REPORTED ONLINE
when stale; they do not claim independent device attestation.
`scripts/run_r1_bridge_demo.ps1` forwards RX records, saves the last forwarded
event ID in `%TEMP%\safesense-r1-event-id.txt`, and restores the Wi-Fi profile
that was connected before the bridge. The demo laptop currently exposes TX on
COM11 and RX on COM13 (COM12 is absent); the laptop used its classroom Wi-Fi profile.
A 12-second serial preflight showed both NVS queues full at 16, RX HTTP 503
for TX writes, BME680 initialization at 0x76, and CSI window logs. A bounded
bridge preflight then connected to the RX AP after disconnecting the campus
profile, forwarded queued records with matching RX ACK, and restored
the prior Wi-Fi profile. Final event `tx-ed4506ce186c876c65e356ca` was found in
FastAPI with T 30.82 C, RH 52.76%, P 96,827.25 Pa, 100 CSI window frames,
47 measured carriers, and RX persistence reported true. Run the bridge again
near the live presentation for a fresh dashboard row.

The two connected classic ESP32 boards were TX COM11 (`8c:94:df:90:1f:ec`)
and RX COM12 (`8c:94:df:90:dd:4c`) for the original capture; RX enumerated
as COM13 at the latest demo preflight. Both were built/flashed with ESP-IDF 6.1 on
branch `v1`. RX runs `firmware/node2_csi_gateway/` as a lab SoftAP at
`192.168.4.1`; TX runs `firmware/node1_sensor_tx/` and joins it. TX commits
bounded BME680/MQ-135 JSON to its NVS queue, HTTP POSTs it to RX, and removes
each record only after RX returns the exact event ID plus `ACCEPTED`. RX
commits its own NVS queue before ACK, and the laptop bridge posts each pending
record to the local FastAPI service, checks the backend's matching ID, then
ACKs RX. Exact event IDs were matched across simultaneous TX/RX UART logs,
bridge ACK output and backend SQLite; the Streamlit JSON view separately
displayed later live records from the same link. For example,
`tx-4150c72f78e8090a0d86eff7` reached the API with RX-reported HTTP/NVS
metadata, BME680 T 29.96 °C, RH 70.85 %, P 97,422 Pa, gas 24,393 Ω,
and MQ-135 ADC 0. A later live RX HTTP poll reported 1,461 CSI frames,
69 completed 100-frame diagnostic windows, RSSI -50 dBm, and 47 measured
subcarriers. On the classic ESP32 every captured frame marked its first four
bytes invalid; only the affected +1 carrier is zero-masked and explicitly
counted. No activity model was released, so activity is `UNKNOWN` and fusion
is `DEGRADED`. The BME680 custom library is the TX rubric driver; the
external library was only an earlier cross-check.

MQ-135 AO still reads raw ADC 0 through the confirmed 10 kΩ / 10 kΩ divider
into GPIO34. The ADC call works, but this does **not** prove the MQ module's
power, heater or analog output works. No ppm or gas alarm is claimed. The
dashboard says `UNVERIFIED (ADC ZERO)` and preserves `UNAVAILABLE` risk.
The remaining physical check is a voltage measurement at MQ VCC, module AO,
and GPIO34-to-GND; no software can prove those voltages remotely.

During a long RX-full period, an earlier TX NVS snapshot showed metadata
`head=0,count=16` but no `e00` blob; `e01`–`e15` survived. After a read-only
NVS backup, the new queue recovery skips only a confirmed `NVS_NOT_FOUND`
head and retains the other records. RX and TX stack-size issues encountered
during live HTTP traffic were fixed; host tests cover exact ACK, duplicate,
malformed JSON, legacy V1 records, NVS metadata rollback/recovery, CSI
masking, backend/bridge, and dashboard behavior. Latest full suite: seven C host
test programs and 31 Python tests passed on 2026-09-24. Desktop and mobile
Playwright checks displayed the live event and JSON without console errors.

The laptop has one Wi-Fi adapter, so the bridge only forwards while that
adapter is joined to the RX AP. The bounded `scripts/run_rx_bridge_demo.ps1`
switches from the current Wi-Fi profile, forwards pending events, then
restores the named profile; it is a lab demo, not a continuously running service.
FastAPI on localhost:8000 and Streamlit on localhost:8501 were started for
this live check. For continuous collection, keep the laptop on the RX AP
with a second internet connection, or redesign the RX-host transport. Do not
describe the current bounded demo as unattended continuous delivery.

## Earlier V1 TX-only status — 2026-09-24 (historical)

The classic-ESP32 TX application is now `firmware/node1_sensor_tx/` on branch
`v1`. It was built with ESP-IDF 6.1 and flashed to COM11 after verifying MAC
`8c:94:df:90:1f:ec`. Its custom BME680 library reads the attached 0x76 chip
over GPIO21/GPIO22; live corrected TX readings were about 29.7 °C, 72 %RH,
97,350 Pa, and 29,142 Ω after heater stabilization. The custom driver's
initial 0x8A-aligned calibration read intermittently produced zero temperature
trim and false 0 °C; reading from 0x89 and skipping the first byte corrected
the live result. A host regression rejects zero trim. A separate external-lib
diagnostic read the same hardware at about 29.8 °C, 70 %RH, and 973.4 hPa.
MQ-135 AO via the user-confirmed 10k/10k divider on GPIO34 repeatedly reads
raw ADC 0; this does not establish a functioning calibrated gas channel.

The TX app persists bounded JSON in NVS, retries HTTP POST until an exact RX
`ACCEPTED` ACK, and can send UDP CSI probes. Wi-Fi SSID and RX URLs are unset,
so HTTP delivery, RX capture, and full end-to-end communication are **not**
verified. A one-time migration discarded the 16 pre-fix `sstx` test records
after backing up the 24 KB NVS partition to a local Temp file; corrected
records were observed persisting and restoring after reboot. The V2 dashboard
layout was ported into V1; it shows stored API JSON and HTTP ingress evidence,
but explicitly marks TX→RX and device origin `UNVERIFIED`. The backend schema
now accepts BME680 gas resistance and validity without implying ppm or IAQ.
All six host C suites and 20 Python tests passed. Browser checks showed the
dashboard in desktop/light and mobile/dark with no mobile overflow. The data
visible in that browser run came from host API tests, **not** the physical TX.

Next: implement/configure RX to ACK TX JSON and forward a backend-compatible
envelope, then prove the same live event ID across TX serial, RX receipt, API
storage, and dashboard. Do not count the backend's HTTP POST alone as proof of
TX→RX origin. See `firmware/node1_sensor_tx/README.md` and the two V1 plans in
`docs/superpowers/plans/`.

## Prior live hardware update — 2026-09-23, V1 branch (historical)

TX is a classic ESP32 (MAC ending `1f:ec`) observed on COM11; RX is a separate
classic ESP32 observed on COM12. The replacement TX sensor answered at I2C
`0x76` (SDA GPIO21, SCL GPIO22) with BME680 chip ID `0x61`. A standalone
ESP-IDF 6.1 test in `firmware/bme680_hardware_check/` was built and flashed to
TX. Ten live samples gave 30.73–30.48 °C, 67.82–67.15 %RH, and
973.78–973.84 hPa. Gas resistance was 0 Ω in sample 1, then 2637–8803 Ω
over samples 2–10 while warming up. This confirms the connected sensor can
produce all four raw channels; accuracy, stable gas baseline, MQ-135, and
full TX/RX telemetry were not validated by that test. At that time TX ran the
temporary diagnostic. The V1 environmental app's BME280/BMP280 driver was a
separate earlier path and is not the current BME680 TX application.

The software milestone notes below predate this live hardware test and contain
historical hardware-unavailable statements.

## Purpose

SafeSense is an indoor safety prototype that combines environmental readings, Wi-Fi CSI activity context, deterministic fusion, local persistence, telemetry delivery, and an operations dashboard.

## Current milestone

Starting from an empty repository on 2026-09-19. Hardware is not available yet, so the first deliverable is a software-complete vertical slice driven by a simulated ESP32-compatible telemetry producer.

The custom BME280 driver is implemented as a register-level ESP-IDF component with a transport abstraction and host-side test fixture. It remains pending physical-sensor acceptance testing.

Fusion is deterministic and implemented in portable C for the edge plus Python for the local service. It has four states: NORMAL, WARNING, INCIDENT, and DEGRADED. Critical environmental risk always opens an incident and cannot be vetoed by CSI. Stale/unknown/low-confidence CSI is DEGRADED, never VACANT. BME280 does not detect gas; environmental-risk classification must come from a separate calibrated sensor or the controlled simulator.

The CSI replay/preprocessing baseline is implemented in Python for 20 MHz ESP32 LLTF packets: reject `first_word_invalid`, use ESP32 I/Q ordering, retain the 48 usable 802.11a/g data subcarriers, then form 100-frame windows. It is an integration simulator, not a trained HAR model or physical validation result.

The Streamlit dashboard at `dashboard/app.py` is aligned to the review evidence without exposing setup or implementation instructions. It presents Environment (temperature, humidity, gas level, risk), Wi-Fi CSI (TX/RX state, RSSI, packet rate, quality), Human Context (activity and confidence), System (MQTT, local storage, ESP32), and Recent Events. Status fields are validated enums, dynamic text is HTML-escaped, absent evidence displays `UNKNOWN`/`UNAVAILABLE`, and dark/light plus desktop/mobile layouts were visually inspected. A simulator/replay can populate every review field, while physical firmware reports only states it can actually observe.

Dashboard UX prioritizes fused state, uses text plus color, preserves explicit degraded/error states, and uses an acknowledgement button rather than automatic incident resolution. UX research and the local-demo polling boundary are documented in `docs/dashboard_ux.md`.

Rubric items 2–4 are wired as a complete software path in `firmware/environmental_node`: custom BME280 reads are serialized as backend-compatible JSON, committed to a bounded NVS queue, restored after reboot, published with MQTT QoS 1, posted by the bridge, and removed only after an exact application ACK. Malformed, substring, fragmented, or non-accepted ACKs do not remove data. `UNAVAILABLE` is now a first-class environmental-risk state in Python and C fusion and fails closed to `DEGRADED`. The ESP-IDF application and physical reboot/MQTT evidence remain pending because neither the toolchain nor hardware is installed.

The rubric handoff is `docs/review_readiness.md`: it maps every mark to code evidence, gives the recommended live demonstration order, includes high-probability Q&A, and contains an individual-contribution worksheet. Actual member names, truthful ownership and rehearsal remain human tasks.

TinyML milestone (software-complete, model release blocked by evidence): training and firmware now use the same physical ESP32 carrier order, `(positive data carriers, then negative data carriers)`. Full-INT8 calibration is deterministic and balanced across all three classes. Training records both float and INT8 confusion matrices and quantization deltas. The TinyML CNN uses only two strided convolutions, mean, fully connected, and softmax; the candidate is 6,464 bytes and its largest inspected activation is 9,600 bytes. Firmware expects exactly the three product outputs (`vacant`, `stationary`, `walking`) and its two roughly 19 KB CSI buffers are in static memory rather than the 8 KB task stack.

The corrected real-plus-physics-synthetic corridor-to-lab experiment used 2,561 real plus 2,561 synthetic training windows and 2,090 untouched real lab test windows. Its INT8 accuracy is 0.311 and macro-F1 is 0.326 (float: 0.285/0.272). Calibration used 100 samples per class and the trace/hash leakage audit passed. Independent logistic and random-forest checks over temporal CSI statistics also failed to generalize (macro-F1 0.125 and 0.201), corroborating room/setup domain shift rather than a quantization-only defect. The candidate at `ml/models/safesense3_fixed_real_plus_synth/` remains rejected by the 0.80 macro-F1 gate and must not be converted into firmware release headers. Actual SafeSense-room/device collection is the remaining model-data gate. ESP-IDF/TFLM allocation and physical-device latency remain unverified because the toolchain and hardware are unavailable.

## Non-negotiable rules

- `UNKNOWN` activity is never equivalent to `VACANT`.
- Environmental danger remains actionable when CSI is stale, unavailable, or low confidence.
- Incident records need idempotency, timestamps, acknowledgement state, and persistence.
- Hardware-dependent claims remain unverified until tested on the actual devices.

## 2026-10-04 forecast lab extension

The user chose a 30-minute synthetic environmental forecasting demonstration with room themes, hidden simulator futures, a primary Wi-Fi TX→RX path and nearby-laptop Bluetooth fallback. The controlled fault toggle skips the TX HTTP send in serial demo mode; it does not disable RF. The new generator contains ten training families and eight entirely held-out families across cold storage, laboratory, classroom, bakery and server room. The data export and manifest are in `data/forecast_synthetic_v1.csv.gz` and `ml/forecast_release/synthetic_v1/`. The trainer exports the same 70→48→24→30 dense model to Python JSON and a TX C header. No future value or scenario key enters model features. On 160 held-out episodes at one fixed decision time, the saved synthetic-only run reports TinyML breach recall 0.789 / precision 0.750 and ten-minute trend recall 0.632 / precision 0.800; this does not validate any real hazard.

`dashboard/pages/Forecast_Lab.py` changes room theme, plays the timeline, shows current versus +30-minute predictions, reveals hidden future only on request, and distinguishes simulated receipts from optional TX hardware receipts. TX source adds model inference and a Bluetooth Classic SPP server; `scripts/bt_alert_receiver.py` journals exact event IDs, ACKs after fsync and attempts local Windows speech. No SOS service is contacted. In synthetic UART replay mode, generated samples are marked `simulated` and use a synthetic device ID. Existing RX/backend storage claims remain separate from laptop receipt or speech.

The original MQ-135 previously read ADC 0; the user now reports a working replacement module. Treat it as a distinct sensor. Its current raw ADC/voltage, calibration and physical forecast/Bluetooth route evidence remain to be captured. Five forecast-specific Python tests and the full 35-test suite passed before a later one-test addition; the final full suite and ESP-IDF build must be rerun at handoff. The ESP-IDF build first exposed an app-partition overflow after adding Classic Bluetooth; TX now has a 2 MB-compatible custom 0x1A0000 app partition and explicit Classic-only controller configuration. Build and physical validation are in progress at this note's timestamp.

The dedicated FastAPI `/forecast` page is now the primary forecast presentation. It matches the light-blue 1586 × 992 cold-storage reference structure and changes atmosphere with the selected room: distinct palette, generated sidebar illustration, icon, tagline and chart accent for laboratory, classroom, bakery and server room. It displays held-out synthetic episode data from `/api/v1/forecast/episode`, offers playback, a Wi-Fi failure toggle, voice demo, hidden-future reveal, and explicit connected-TX replay through `/api/v1/forecast/replay`. The browser check found no page errors or document overflow at desktop/mobile widths. Visual differences from the concept are intentional where that concept invented door/battery readings, a named recipient or confirmed cloud/voice delivery. `docs/forecast_frontend_fidelity.md` records the comparison.

The full Python suite now passes 36 tests. The ESP-IDF 6.1 TX normal build succeeded with a 0x149c90-byte image; the serial-simulation demo build also succeeded with a 0x14b540-byte image, about 20% app-partition space free. These are compile results only. No COM port was present during this milestone, so neither ESP32 route nor nearby Bluetooth receipt was physically retested, and the replacement MQ-135 still needs its own ADC/voltage recording. The generated local TX `sdkconfig` currently enables `CONFIG_SAFESENSE_TX_SCENARIO_SERIAL_DEMO=y`; the tracked `sdkconfig.defaults` leaves normal sensing as the default for a clean build. Follow `docs/forecast_lab.md` to enable/rebuild the demo firmware before serial replay.

The forecast frontend sidebar originally used same-page anchors. The user pointed out that the labels all moved within one screen. It now has distinct URL-addressable Overview, Forecast, Sensors, Sites, Alerts, Reports, Integrations and Settings views, with browser history and direct links. The Alerts/Sensors views spell out the actual policy: temperature, humidity and BME680 gas resistance can trigger on configured demo-range crossings; pressure and MQ-135 raw ADC are model inputs/outputs without alert bounds. Default cold-storage triggers on temperature; some classroom/lab episodes trigger on gas resistance. A Playwright pass clicked every view, deep linked to Alerts, used back navigation, selected a scenario from Sites, revealed report truth, toggled an integration fault, applied Settings and checked 390 px mobile overflow; no page errors were observed. Physical delivery remains unverified.

## 2026-10-04 live hardware integration

The sidebar now includes a separate Live Hardware screen at `/forecast?view=live`. It polls `/api/v1/live` every three seconds, shows the latest BME680 and MQ-135 raw readings, exact event IDs and sequence, RX NVS storage, backend SQLite storage, RX forward ACK, Bluetooth laptop receipt, bridge heartbeats, and recent deliveries. Readings older than 45 seconds are marked stale. Generic `/api/v1/telemetry` posts and synthetic UART replay records are excluded through the local RX bridge ingress marker and synthetic-mode field. These are process-reported signals, not cryptographic board attestation.

The RX bridge now sends a local ingress header, journals successful RX forward ACKs and syncs exact-ID receipts to FastAPI. The Bluetooth receiver journals before ACK, then syncs receipts and a listener heartbeat to FastAPI. BT alert frames now carry `R` for normal real-sensor mode and `S` for serial synthetic replay; legacy frames with unknown origin are excluded from the physical monitor. Backend receipt records are idempotent by event ID and hop. The normal TX Wi-Fi/NVS/RX exact-ACK path and RX persistence were already implemented; this milestone connects their evidence to the new screen. Details and run steps are in `docs/live_hardware_integration.md`.

No serial ports were present in this turn, so neither board was flashed or retested physically. TX normal-mode and serial-demo builds passed under ESP-IDF 6.1, as did the RX build, 43 Python tests, seven firmware host-test binaries, and desktop/mobile browser checks of the live view. The current live API correctly returns zero physical events and zero Bluetooth-only receipts; older generic API test rows are not shown. Real-model forecasts remain synthetic-trained and unvalidated for hazards. The replacement MQ-135 is user-reported working, but its current raw ADC capture and electrical validation have not been recorded here.

The forecast sidebar keeps its navigation in a scrollable flex region, with the original full-size decorative footer in normal document flow below it. At short desktop heights, only menu spacing contracts; the 174 px illustration remains unchanged and Settings is visible at a 1028 x 667 browser viewport. The artwork also appears on Live Hardware. The topbar snowflake beside SafeSense was replaced with a room-neutral shield and sensor-pulse SVG mark. The synthetic CSV was checked on disk: 114,760 one-minute rows from 600 training episodes (10 families) and 160 held-out episodes (8 families). The manifest, saved metrics, Python model and firmware model header exist. These are complete synthetic-demo artifacts, not real-room hazard validation.

## 2026-10-06 forecast communication diagram

The `/forecast` diagram now shows one conceptual Wi-Fi route, Sensor TX → Laptop RX, and a Bluetooth fallback route, Sensor TX → Mobile phone. The user asked to remove the separate RX ESP32 and bridge boxes from this diagram while keeping the existing Wi-Fi fault toggle and simulation behavior. Phone and laptop receipts remain labeled unverified in this view; the connected TX replay still reports its actual RX ESP32 ACK and paired-laptop Bluetooth receipt separately. The diagram edit does not change firmware or establish a physical phone receiver. Browser checks at 1586 × 992 and 390 × 844 showed the toggle updating both routes, no page errors, and no document overflow.

The SafeSense-generated synthetic forecast dataset was published publicly to `Ajeya95/safesense-synthetic-environmental-forecast-v1` on Hugging Face at commit `039d156a0eb10ddfccaa0dd90ece418e9e52d344`. The release contains split Parquet files, the exact compressed CSV export, manifest, generator source, and a card explicitly stating synthetic project provenance and no selected reuse license. Both Parquet splits were fetched back anonymously into `data/hf_fetched_synthetic_v1/` and matched the local release files by SHA-256. Hub Dataset Viewer split indexing first returned busy/500, then reported `pending` with no failed configs; check later before claiming viewer readiness. The existing trainer still generates its examples locally; publication did not change model training or validate hazards.

## 2026-10-06 single-board physical transport check

Classic ESP32 `8c:94:df:90:1f:ec` (COM11) now runs a direct-laptop SoftAP Wi-Fi
route and a paired Bluetooth Classic SPP alert route. The laptop receiver
journals Wi-Fi events by exact ID before ACK and syncs them to FastAPI; the
Bluetooth receiver journals before `ACK|ID`, syncs receipts, and attempts
local voice playback. The live dashboard separates physical readings and
labelled transport tests. The BME680 connected in this session uses I2C
`0x77`, discovered by probing `0x76`/`0x77`; MQ-135 GPIO34 reports raw ADC.

Physical Wi-Fi event `tx-3f4ec03b44a16c5dc5c98404` reached laptop and
backend with non-null BME680 temperature/humidity/pressure/gas and MQ-135
ADC. On regular `Amrita` Wi-Fi, Windows paired with `SafeSense-TX-Alert` on
outgoing COM15; a Bluetooth-only labelled test event
`tx-b5a58d68bafed12fe1b3b23e` was journalled, reported to the backend,
and the ESP32 logged `state=STORED` for that exact ID. The laptop remains on
`Amrita`, the injected Wi-Fi receiver fault is off, and the normal COM15
listener is running. The 4 MB pre-flash backup is in ignored
`output/hardware_backup/`. The TX NVS queue reached its 16-event cap while
Wi-Fi was absent; the Bluetooth test succeeded, but its TX-side queue
retention did not. Do not claim durable long-outage delivery or real hazard
forecast accuracy from this check. The dashboard now rejects Wi-Fi test
requests while the laptop route is off the ESP32 subnet, rather than claiming
an unverified send. The Live Hardware refresh text now names the ESP32 Wi-Fi
network when the direct route is stale, rather than telling users to inspect
the USB bridge. Runbook: `docs/direct_laptop_transport.md`.

Follow-up in the same hardware session: TX now sends complete environmental
JSON over Bluetooth SPP when the current sample lacks a Wi-Fi ACK. The paired
COM15 listener validates it, commits it to ignored `data/live/direct_bt.db`,
ACKs the exact ID, and syncs it to FastAPI with a distinct Bluetooth marker.
The Live Hardware view shows actual BME680 and MQ-135 values as
`DIRECT_BLUETOOTH` while Windows remains on `Amrita`. Physical event
`tx-93a6153a6e87907efefba3bf` reached both laptop and backend with real
sensor values; later samples continued at roughly 10-second intervals. A
browser check rendered `LIVE BLUETOOTH READING`. The browser's earlier stale
age was also inflated by parsing UTC-naive SQLite timestamps as local; direct
event timestamps are now normalized to UTC before freshness calculation.

## Initial architecture

One local FastAPI service, SQLite initialized from SQLAlchemy metadata, WebSocket dashboard fan-out, and Streamlit dashboard. ESP32 environmental firmware publishes the same validated telemetry envelope over MQTT through the local bridge. Formal versioned database migrations are not implemented and are outside the present review rubric.

## 2026-10-06 GitHub publication

At the user's request, the accumulated SafeSense V1, Forecast Lab, live-view,
firmware, web, test, documentation and synthetic forecast release sources were
committed as `6a0aa9c` and pushed to both `v1` and the default `main` branch of
`Ajey95/Safesense-EdgeAI`. The push was a fast-forward on both branches.
Local CSI capture JSONL, fetched dataset copies, SQLite files, flash backups,
generated build/presentation output and transient chart files remain on disk
and are ignored by Git. The synthetic dataset and released synthetic model
artifacts were included; they are not real-hazard validation. Before the push,
46 Python tests and all seven firmware host test programs passed, and the
staged changes passed `git diff --cached --check`. The physical phone receiver,
replacement MQ-135 ADC/voltage, and real-hazard forecast validation remain
open as described above.

## 2026-10-07 direct laptop transport GitHub update

Commit `59cd8ef` adds the classic ESP32 direct-laptop SoftAP HTTP
route, exact-ID laptop receiver, paired Bluetooth full sensor JSON fallback,
Live Hardware direct Wi-Fi/Bluetooth views, labelled transport test controls,
and the direct transport runbook. The 2026-10-06 physical check above is the
evidence for the two paths; no new physical test was run during this GitHub
update. The earlier AIRWISE discussion remains a proposal: no AIRWISE data,
training, or real-data evaluation was integrated in this snapshot. The
synthetic Hugging Face dataset card and README keep its provenance explicit.
Before publication, 49 Python tests passed, both changed dashboard scripts
passed `node --check`, and the ESP-IDF 6.1 TX build completed with a
0x14a080-byte image and 21% of the app partition free. The commit was pushed
as a fast-forward to both `origin/v1` and the default `origin/main`. The direct transport
runbook records the NVS queue-full limitation and the difference between
transport receipts and hazard forecast validation.
