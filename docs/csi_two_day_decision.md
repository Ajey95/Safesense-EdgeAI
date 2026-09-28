# SafeSense: two-day CSI demonstration decision

Date: 2026-09-28. Status: recommended delivery design for review; physical
collection, model accuracy and demo readiness have not been established.

## Delivery objective

Demonstrate live room activity and environmental monitoring using the existing
V1 classic-ESP32 TX/RX pair, the local laptop, FastAPI/SQLite and Streamlit.
The broader goal of human-only counting and individual activities is retained,
but this deadline delivers only outputs supported by real held-out recordings.
No additional hardware is required for the proposed two-day scope.

## Architecture

TX Wi-Fi probes -> RX CSI capture -> USB serial collector -> laptop feature
extraction and inference -> local API/SQLite -> existing dashboard.

The existing environmental HTTP/NVS delivery remains the source of BME680
temperature, humidity and pressure. CSI inference is performed on the laptop;
the unreleased INT8 firmware model remains disabled.

Export timestamped raw I/Q plus source identity, validity and capture/drop
counters through a bounded nonblocking queue. Verify serial throughput before
collection. Training and live preprocessing must share a versioned carrier
order and invalid-first-word policy: classic ESP32 currently yields 47 measured
data carriers in a masked 48-wide frame. Diagnostic masking alone is not a
released model contract. Use 100-frame windows initially and reject windows
with material timing gaps. Measure actual duration and rate rather than assume
that every 100-frame window spans two seconds.

## Outputs and evidence boundaries

- Core: movement / no significant movement / unknown, a live CSI trend,
  signal freshness and quality, environmental readings, and saved events.
- Activity experiment: vacant / stationary / walking / unknown in controlled,
  single-person scenes. For multi-person scenes, report aggregate room motion
  unless mixed activity has independently been validated.
- Count experiment: estimated 0 / 1 / 2 humans, or null (display unavailable).
  Expose this numeric result only after the count experiment passes its own
  held-out gate. Do not infer count from activity labels or motion intensity.
- Model scores are labelled prediction scores, not measured accuracy or
  calibrated probabilities. Held-out evaluation results are shown separately.
- Manually armed movement alerts are monitoring events, not proof of human
  intrusion, danger, a fall, or an animal-free room.

No motion does not establish vacancy. Humans and pets may coexist. Animal
rejection, per-person simultaneous activities, counts above two, cross-room
generalization and embedded inference are outside the two-day acceptance scope.
Any unsupported or stale output stays unknown, never silently zero or vacant.
Experimental CSI output does not override the existing safety fusion policy.

## Data and model

Record independent takes with known 0/1/2 human counts. Include sitting,
standing, walking, varied positions and two-person still/moving combinations.
Manual annotations record the actual scene, session, room, placement and
participants; they must not be inferred from model output.

Split whole recording sessions before windowing. Use Day-1 training and
separate validation takes for selecting features and thresholds. Reserve fresh
Day-2 takes as the final test. Metadata such as session names, ground-truth
labels and participant IDs never enter the predictive features.

Start with a transparent motion baseline and separate Random Forest classifiers
on per-carrier amplitude and temporal statistics for activity and count. Use a
fixed random seed and save preprocessing, features, model, recording hashes,
partitions and confusion matrices. A larger neural model is not required for
this deadline. Random Forest API reference:
https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.RandomForestClassifier.html

## Proposed acceptance gates

Core acceptance requires repeatable live signal response, timestamped event
persistence, honest measured signal quality, and unknown output after signal
loss. Test malformed packets, timing gaps and train/live preprocessing parity.

For activity, retain the existing 0.80 macro-F1 target and require stationary
recall >= 0.80 on the untouched test. Report occupied-to-vacant errors.
For the count experiment, the proposed minimum is exact accuracy >= 0.80,
recall >= 0.80 for each 0/1/2 label, and mean absolute error <= 0.20. Evaluate
two stationary people and one moving person explicitly. Include at least three
independent held-out takes for every supported class; this is a pilot minimum,
not statistical evidence of general deployment reliability.

Set abstention thresholds using validation only. Report both classification
metrics across all eligible test windows and accuracy/coverage after abstention,
so rejecting most inputs cannot disguise a weak model. A failed experiment is
kept in the report and its numeric/class output is disabled in the live demo.
These thresholds are proposed demo criteria, not achieved metrics or a
production release approval.

## Two-day execution and handoff

Day 1: establish raw capture, verify quality/parity, collect labelled takes,
train baselines, and connect actual inference to the dashboard. Count trials
must not consume time needed for a working core demonstration.

Day 2: freeze models, test fresh recordings, apply the separate eligibility
gates, verify dashboard on desktop/mobile, and rehearse movement/stop/leave plus
signal-loss handling. Include held-out metrics and a clearly labelled replay
of recorded hardware data as a backup. Never present replay as live data.

Completion package: one-command local run instructions, saved model/config,
held-out evaluation report, dashboard, event persistence evidence and demo
recording. Physical work requires both boards and access to the intended room;
count collection additionally requires two volunteers. Windows currently
enumerates no serial ports. No flash or new training has occurred in this task.
