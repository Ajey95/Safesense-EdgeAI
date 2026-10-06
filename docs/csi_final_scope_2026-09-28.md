# SafeSense public-data demonstration scope — 2026-09-28

## Dataset decision

Primary: [WiMANS](https://github.com/huangshk/WiMANS), for a recorded-CSI
experiment with bounded human count and simultaneous room activity labels.
Start with recordings containing 0, 1 or 2 humans. Its annotated user counts
provide ground truth; activity labels provide the activities present in the
room. Nothing means no scripted activity, not an empty room. The nine source
activity labels remain distinct; no arbitrary posture/occupancy conversion.

Fallback: existing local WISDOM, for an activity-only recorded-CSI demo.
Use empty/vacant, standing or sitting/stationary, and walking as the initial
three-state experiment. Exclude jumping and sittingupdown for that baseline.
Do not infer multi-person counts from WISDOM or duplicate its two copies.

Defer ESP-Fi HAR, CSI-Bench, Home HAR and other datasets until the primary
demo is evaluated. Adding unrelated capture platforms and label sets is not
necessary for the two-day delivery. This narrows the earlier search options;
the earlier target-room collection design is not the current public-data path.

## Deliverable and intended outputs

A local software demo replays held-out public CSI recordings, runs actual
model inference, and displays estimated count (bounded 0–2), room-level
activity labels, signal plot, prediction scores, and a timestamped timeline.
Recorded-source labels must be visible. Ground truth must be shown separately
from model predictions and must never generate the displayed prediction.
No individual identities or per-person activity assignment are promised.

Training/evaluation should report exact count accuracy, mean absolute count
error, activity precision/recall/F1, and any abstention coverage. Split whole
recording groups before windowing; fit preprocessing on training data only.
Inspect WiMANS annotations, class coverage, archive size, access and local
runtime before committing to model choices or announcing measured results.
The supported 0–2 range describes this pilot's selected recordings; it is not
a claim that a model trained on this subset can detect or reject 3+ people.

## What cannot be guaranteed

There is no honest guarantee of 100% model accuracy or reliable live ESP32
performance from public data alone. WiMANS capture hardware differs from the
SafeSense pair. No new WiMANS payload or trained baseline exists locally yet;
download/resource feasibility and held-out model performance remain gates.
If WiMANS is blocked by access, size or insufficient results for the deadline,
ship the evaluated WISDOM activity replay and clearly omit the count claim.

Human-versus-animal discrimination, counting humans in mixed human/pet scenes,
live hardware acceptance, per-person mixed activity and arbitrary-room
generalization are outside this two-day commitment. Unknown results must not
be rendered as zero humans or an empty room. An activity model and complete
software demo can be delivered without claiming an unmeasured accuracy target.

This file records the final recommended scope, not achieved model capability.
No dataset download, training, firmware change or flashing occurred in this
decision turn.
