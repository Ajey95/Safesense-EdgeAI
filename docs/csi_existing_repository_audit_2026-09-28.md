# Existing CSI implementation audit — 2026-09-28

User request: find GitHub projects that have already implemented our sensing
work. This review inspected author READMEs, GitHub repository trees and selected
source/result files. No third-party code or checkpoints were executed, no
dataset/model payload was downloaded, and no maintainer was contacted.
Published results below are author-reported, not reproduced SafeSense results.

## Reusable candidates

| Repository | Existing work | Actual availability / boundary |
| --- | --- | --- |
| [WiMANS](https://github.com/huangshk/WiMANS) | Multi-user identity, location and activity benchmark; MLP/LSTM/CNN/other training models and experiment runner | Author dataset supports 0–5 users. Current repository tree contains no model checkpoint files. Runner tasks are identity/location/activity, not count; add a dedicated count target/output from annotations. Capture differs from SafeSense ESP32. |
| [SenseFi](https://github.com/xyanchen/WiFi-CSI-Sensing-Benchmark) | Activity benchmark loaders, training/evaluation code and linked pretrained weights | README links processed data and pretrained models on Google Drive. Checkpoint access/loading was not verified. Good offline activity shortcut on matching data; not an existing multi-person counter. |
| [Wi-Fi Vision](https://github.com/Abinand2631/Wifi-Vision) | Two-receiver ESP32 pipeline, TEDNet pose model, live scripts and Streamlit UI | `models/tednet_3d_best.pth` exists (3,855,110 bytes). Needs one TX plus two RX boards. Training uses pose-coordinate MSE; live posture labels use heuristics. No verified people count or pet exclusion. |
| [wifi-csi-occupancy](https://github.com/venkatasasikiranreddykotapati/wifi-csi-occupancy) | ESP32-S3 pair + Raspberry Pi; feature extraction, ML and grouped evaluation | README reports 86.2% balanced accuracy for presence and 52.4% for exact 0–3 count. Four example recordings are included; full dataset is available on request. No checkpoint files found in the current tree. |
| [CSI-Bench](https://github.com/guozhen-jenn-zhu/CSI-Bench-Real-WiFi-Sensing-Benchmark) | Training/evaluation framework including Human/Pet/IRobot/Fan classification | Source supports separate specialist tasks and joint activity/identity/proximity tasks. Current README specifies corrected Kaggle Version 12. No checkpoint files found in the tree; not a trained joint count/activity/pet solution. |
| [WiVi32](https://github.com/cvwifi-lab/WiVi32-A_People_Counting_Tool) | ESP32 CSI + synchronized vision data collection and processing for counting | README describes 60,044 samples and 0–7/7+ occupancy labels. Full data, backend and mobile code require an access request; no checkpoint files found. Not a dependable immediate-download option for the two-day deadline. |
| [RuView](https://github.com/ruvnet/RuView) | Large ESP32-S3 sensing platform, UI, model workflow and committed count artifacts | Actual `count_v1.safetensors` and `count_v1.onnx` exist. Current count results do not establish multi-person performance; see artifact audit below. Separate pose benchmarks must not be read as ESP32 count/activity accuracy. |

## Code/artifact findings that affect selection

WiMANS [runner instructions](https://github.com/huangshk/WiMANS#experiments)
list identity, location and activity tasks. Its `benchmark/wifi_csi/train.py`
implements actual learned multi-label inference. Treat it as a reusable
baseline framework; no plug-in count checkpoint was found in this review.

Wi-Fi Vision's [training script](https://github.com/Abinand2631/Wifi-Vision/blob/main/train.py)
uses MSE for 3D coordinate regression, not a directly supervised activity
classifier. Its [live script](https://github.com/Abinand2631/Wifi-Vision/blob/main/6_test_live_v2.py)
classifies posture from predicted joints and labels activity below a calibrated
motion threshold as Empty Room. That logic can miss stationary occupants and
must not override SafeSense's UNKNOWN != VACANT contract. A checkpoint's
existence or low coordinate MSE is not count/activity acceptance evidence.

RuView's [count artifact results](https://github.com/ruvnet/RuView/blob/main/v2/crates/cog-person-count/cog/artifacts/count_train_results.json)
currently report v0.0.2, evaluation accuracy 0.6232558, MAE 0.3767442,
215 evaluation samples, and per-class support only for counts 0 and 1.
The split is random 80/20. Its [component README](https://github.com/ruvnet/RuView/blob/main/v2/crates/cog-person-count/cog/README.md)
still describes older v0.0.1 as single-session solo data with a degenerate
counter. These sources are at different versions. The current JSON is evidence
of an evaluated 0/1 experiment, not accurate counting of 2+ people or a room-
separated result. Within-one-person accuracy of 100% is uninformative for an
evaluation restricted to 0 and 1. No runtime reproduction was attempted.

## Recommendation

Keep WiMANS as the primary recorded-data count/activity route. Reuse its
baseline structure, add our bounded count task, evaluate by recording group,
and display predictions in our existing dashboard. SenseFi's linked models
are a secondary way to accelerate an activity-only matching-dataset replay.
Existing local WISDOM remains the data fallback. Wi-Fi Vision is a useful
architecture reference if a third ESP32 and target-room data become available,
but does not satisfy the no-collection count requirement out of the box.

No reviewed repository was verified to deliver the complete combination of
live SafeSense-compatible human count, per-person activities and animal
exclusion without target-hardware/room validation. Reuse choices must preserve
attribution and be checked against the selected source/data/model license.
