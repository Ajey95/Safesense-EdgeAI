# Public CSI dataset search — 2026-09-28

The user requested GitHub repositories and other datasets that could support
training without personally collecting data. This is a source and access-route
review. No additional dataset payload was downloaded, no repository code was
executed, and no new model was trained. HAR means human activity recognition;
datasets from wearable accelerometers or video are not CSI training data.

## Shortlist

| Dataset / author source | Relevant contents | Access and fit |
| --- | --- | --- |
| [WISDOM](https://github.com/senselab-iitm/wisdom) | ESP32 CSI; empty, standing, sitting, sittingupdown, jumping, walking; four locations | Already local. GitHub scripts link to public Google Drive data/models. Fastest existing activity baseline. |
| [ESP-Fi HAR](https://github.com/AutoSmartGroup/ESP-Fi-HAR) | ESP32 amplitude; run, fall, walk, turn, jump, squat, arm wave; four indoor environments | GitHub lists a 615 MB Git LFS RAR archive and PyTorch benchmarks. Input is 1 x 950 x 52, unlike our 100 x 48. Strong activity expansion candidate; no empty/static class in its seven labels. |
| [WiMANS](https://github.com/huangshk/WiMANS) | 11,286 three-second samples; 0–5 simultaneous users; nine activities; user/location/activity annotations | [Author-linked Kaggle dataset](https://www.kaggle.com/datasets/shuokanghuang/wimans). Best shortlist match for combined count and simultaneous activity experiments. Intel 5300 capture, not an ESP32 model. |
| [CSI-Bench](https://github.com/guozhen-jenn-zhu/CSI-Bench-Real-WiFi-Sensing-Benchmark) | Separate activity, fall and other tasks; MotionSourceRecognition distinguishes Human, Pet, IRobot and Fan | [Author-linked Kaggle dataset](https://www.kaggle.com/datasets/guozhenjennzhu/csi-bench). Current README says benchmark uses updated Version 12 after data corrections. Pet discrimination research candidate; not a combined human-count/pet dataset. |
| [Home HAR](https://huggingface.co/datasets/gadgadgad/HomeHAR) | ESP32-C6; drink, eat, empty, sleep, smoke, watch, work; three recording sessions | Public Hugging Face files, listed total 2.53 GB; [author code](https://github.com/gadm21/WifiSensingESP32HAR). Fine-grained home activities; loader adaptation needed. Dataset viewer currently reports a CSV parsing error, which does not by itself establish that raw files are unusable. |
| [UT-HAR / original author code](https://github.com/ermongroup/Wifi_Activity_Recognition) | Lie down, fall, walk, pickup, run, sit down, stand up | Raw author data linked on Google Drive (~4 GB according to README). [SenseFi](https://github.com/xyanchen/WiFi-CSI-Sensing-Benchmark) provides processed data and benchmark models; 250 x 90 input. Useful offline activity baseline, different capture platform. |
| [NTU-Fi HAR / SenseFi](https://github.com/xyanchen/WiFi-CSI-Sensing-Benchmark) | Box, circle, clean, fall, run, walk | Processed Google Drive data linked by authors; 3 x 114 x 500 input. Useful activity benchmark, not directly compatible with our CSI window. |
| [ESP32 through-wall HAR](https://zenodo.org/records/8021099) | No activity, walking, walking with arm waving; separate presence/location tasks | Four downloadable ZIPs total 14.8 MB; packaged as spectrogram images, not raw CSI. Useful small offline image-model demo; not a direct replacement for our raw pipeline. Record limits use to non-commercial research. |

## Additional references

[EHUCOUNT](https://www.ehu.eus/en/web/tsr-lab/artificial-intelligence-in-wireless-applications)
is explicitly a people-counting CSI dataset. Its university page links to an
[EHUCOUNT.zip download page](https://ehudoku.ehu.es/share/s/5OYhCalJRyC31jXIhbq3cg)
and describes six MATLAB/OCTAVE files. Payload, count ranges and hardware
were not inspected in this search.

Widar3.0 is a gesture benchmark, with processed data also offered through
SenseFi. It is a lower priority for whole-room activity and counting.
NTU-Fi HumanID identifies enrolled gait subjects; identity is not occupancy count.

## Hardware and evaluation boundaries

The [WiMANS paper](https://www.ecva.net/papers/eccv_2024/papers_ECCV/papers/05826.pdf)
describes 3 x 3 antenna links x 30 subcarriers, with 3,000 time steps per
three-second sample. Count targets can use its annotated number of users;
the activity label Nothing must not be interpreted as zero occupants.

The [CSI-Bench author paper](https://arxiv.org/html/2505.21866v1)
describes motion-source data captured using NXP88W8997 2 x 2 devices and
58 subcarriers at 100 Hz. Non-human recordings are collected when users
are absent. Some other tasks contain ESP32-S3 data; that does not imply an
ESP32 pet dataset. The current Version 12 payload still requires inspection.
Human-only versus pet-only classification does not establish human detection
or counting in mixed human/pet scenes.

Changing tensor dimensions alone does not resolve hardware/room differences.
Do not concatenate these datasets blindly, combine their unrelated labels,
or multiply separate benchmark results into a claim of joint capability.
Hold out whole sessions/subjects/rooms as appropriate; fit preprocessing only
on training data and retain all-window metrics plus abstention coverage.

## Recommendation for the two-day deadline

For an ESP32-oriented activity demo, prioritize existing WISDOM and consider
ESP-Fi HAR as a separate expanded-activity experiment. For a recorded CSI
demo whose primary output is human count plus simultaneous activities,
prioritize WiMANS, subject to download access, resource cost and held-out
evaluation. CSI-Bench motion-source recognition is a separate extension.
Live performance on SafeSense hardware remains unverified without relevant
target-device and target-room testing. No combined dataset covering all
requested outputs was verified in this search.

[collabray/wisense](https://github.com/collabray/wisense) is software rather
than a validated training dataset: its current README states alpha status,
synthetic test validation, no real ESP32 hardware validation, and no shipped
trained model weights. Do not substitute repository feature claims for
measured model capability.
