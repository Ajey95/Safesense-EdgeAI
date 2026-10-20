# GitHub Wi-Fi CSI capability review — 2026-10-09

## Scope and method

Searched GitHub repository metadata for `wificsi`, `wifi csi`, `esp32 csi`, and `wifi sensing`, plus targeted task terms. Read the repositories below individually (README and, where relevant, linked technical documentation or dataset pages). This is a representative review of substantive results, not an inventory of every GitHub repository. GitHub stars, a dashboard, or a feature name are not proof of measured performance. No third-party code was executed and no dataset/model was trained in this review. Exclude MIPI-CSI camera repositories from Wi-Fi CSI results.

Evidence labels: **author benchmark** = published author code/data with a defined task; **implemented tool** = capture or runtime code with a bounded stated output; **prototype/claim** = self-described feature without independently checked real-room performance; **infrastructure** = data collection/processing rather than a trained sensor capability.

## Repository-by-repository findings

| Repository | What it actually supports | Evidence and key limit |
| --- | --- | --- |
| [Espressif ESP-CSI](https://github.com/espressif/esp-csi) | ESP32 CSI capture and motion/presence demo; TX/RX or router traffic | Official infrastructure/demo. Capture is not an activity/count model. |
| [ESP32-CSI-Tool](https://github.com/StevenMHernandez/ESP32-CSI-Tool) | Active/passive ESP32 raw CSI collection to serial/SD and basic plots | Infrastructure. Requires a separate labelled pipeline for human outputs. |
| [ESPectre](https://github.com/francescopace/espectre) | Embedded motion detection and movement score, local integrations | Implemented tool with open data/weights and performance reports. Its README explicitly says it does not count, identify people, or prove emptiness. |
| [WISDOM](https://github.com/senselab-iitm/wisdom) | ESP32 human activity recognition scripts, data and on-device model assets | Author research. Dataset/model files are linked externally; our local six-label data was separately audited. No human count or animal label. |
| [ESP-Fi HAR](https://github.com/AutoSmartGroup/ESP-Fi-HAR) | Seven ESP32 activity labels: run, fall, walk, turn, jump, squat, arm wave | Author benchmark; four environments, 1×950×52 amplitudes. No empty/stationary label in this dataset; README says best checkpoint is chosen by training accuracy because no validation partition is available. |
| [WiMANS](https://github.com/huangshk/WiMANS) | Multi-user activity, user identity and location labels; 0–5 users per sample | Author benchmark, 11,286 three-second samples, different capture hardware. Count is available from annotation, but the README's benchmark tasks are identity/location/activity; count needs its own evaluated model. |
| [WiVi32 / PRoFENCH](https://github.com/cvwifi-lab/WiVi32-A_People_Counting_Tool) | ESP32-based 0–7 people-count research with synchronized camera ground truth | Author research. Our supplied archive has 60,044 CSI packets but no independent validation/test directories and one approximately five-minute run per class; see `csi_profench_dataset_audit_2026-10-09.md`. No activity/pet label. |
| [CSI-Bench](https://github.com/guozhen-jenn-zhu/CSI-Bench-Real-WiFi-Sensing-Benchmark) | Fall, breathing, localization, motion source (human/pet/robot/fan), activity, human ID and proximity tasks | Author benchmark with task-specific recordings and cross-device/environment/user splits. Motion-source data do not establish human count in mixed human/pet scenes. Most capture hardware differs from our ESP32 path. Use the corrected version 12 dataset. |
| [SenseFi](https://github.com/xyanchen/WiFi-CSI-Sensing-Benchmark) | HAR, human ID/gait and Widar gesture benchmark; model zoo and weights | Author benchmark across datasets/hardware. UT-HAR includes fall as an action; the task is classification, not clinical fall monitoring. |
| [Exposing the CSI](https://github.com/ansresearch/exposing-the-csi) | Twelve actions including empty, stationary postures and movement, across people/rooms/days | Author dataset with 802.11ax 160 MHz, 4 antennas and multiple receivers. Useful for studying domain shift, not directly the SafeSense 20 MHz ESP32 tensor. |
| [DapFall](https://github.com/zyb-sysu/DapFall) | Wi-Fi CSI fall-event research and data link | Author code/data. Independent live safety performance on SafeSense is unmeasured. |
| [SignFi](https://github.com/yongsen/SignFi) | Fine-grained hand/sign gesture classification, up to 276 sign words in a source dataset | Author dataset and CNN example. Specific participants/settings, access terms, and CSI hardware; not general sign-language understanding on ESP32. |
| [Person-in-WiFi 3D](https://github.com/aiotgroup/Person-in-WiFi-3D-repo) | Multi-person 3D body pose research | Author CVPR code; multi-device spatial capture and GPU model. A single SafeSense link cannot be assumed to reproduce it. |
| [ESPARGOS Channel Charting](https://github.com/Jeija/ESPARGOS-WiFi-ChannelCharting) | Relative/absolute transmitter localization from phase-coherent multi-antenna CSI | Author data/code. This localizes a transmitting device; it is not a direct single-link, device-free person locator. |
| [NeRF2](https://github.com/XPengZhao/NeRF2) | Predicting MIMO CSI/channel characteristics at transmitter positions; synthetic channel data | Author MobiCom code and datasets. A radio-propagation modelling task, not person detection or a room image. |
| [WiFi_CSI_Respiration](https://github.com/JiamuLea/WiFi_CSI_Respiration) | Concept code for human presence plus breathing/heartbeat extraction in static and dynamic conditions | Research/prototype code; no broad clinical validation established by its README. |
| [csi_hr](https://github.com/nickbild/csi_hr) | Experimental ESP32 CSI heart-rate estimation with external pulse-sensor training labels | Prototype. Author explicitly says educational, not medical; own data and retraining required. |
| [Mobile CSI Object Detection](https://github.com/SiamiLab/MobileCSIObjectDetection) | Detecting whether a closed box contains an object from mobile robot CSI | Narrow research dataset/examples. This is not generic object recognition or a SafeSense room feature. |
| [WiSense](https://github.com/collabray/wisense) | Software modules claiming presence, fall, breathing, coarse activity and count | Alpha prototype. README says synthetic tests only, no real ESP32 validation and no shipped trained ONNX weights. Do not treat its feature list as proven capability. |
| [WiFi-3D-Fusion](https://github.com/MaliosDark/wifi-3d-fusion) | Broad 3D pose/visualization research project | Large popularity, research disclaimer and many upstream references. Use original Person-in-WiFi 3D for measured pose evidence; popularity is not validation. |
| [WhōFi](https://github.com/jedarden-org/whofi) | Claims device-free indoor positioning/multi-person tracking | Treat claimed accuracy as unverified in this review; do not substitute its README figures for a held-out, reproducible study. |
| [AntiEave](https://github.com/MoWiNG-Lab/AntiEave-WiFi-Sensing) | Research on protection against adversarial Wi-Fi sensing | Security/privacy research, not a person-detection output. |

## Capabilities found in the inspected sources

1. **Signal collection and quality monitoring:** raw CSI, packet rate, RSSI, channel changes and amplitude/phase trends. Found in Espressif ESP-CSI and ESP32-CSI-Tool. These are measurements, not human labels.
2. **Motion/change detection:** a person or moving object perturbs the channel; strongest practical ESP32 starting point is ESPectre. Motion alone does not prove a human or vacancy.
3. **Presence/absence under a defined setup:** binary occupied/empty experiments, including some stationary-presence and through-wall research. Requires empty-room controls, signal freshness and room testing.
4. **People count/crowd level:** WiVi32 0–7 labels and WiMANS 0–5 people annotations. Counting from CSI alone requires an independently evaluated count model; this is harder than motion.
5. **Human activity/posture:** walking, sitting, standing, running, jumping, cleaning, etc. WISDOM, ESP-Fi, WiMANS, SenseFi and Exposing the CSI use different label sets and radio platforms.
6. **Fall-event classification:** ESP-Fi, DapFall and CSI-Bench show research tasks. A fall class is not a safety-certified fall alarm.
7. **Gesture/sign recognition:** Widar in SenseFi and SignFi show gesture vocabularies, including fine-grained hand/sign movements, under their own capture setups.
8. **Breathing and subtle movement:** CSI-Bench breathing task plus experimental respiration pipelines. Rate measurement, stationary presence and sleep-related applications need their own reference labels and error bounds.
9. **Heart-rate estimation:** experimental work such as `csi_hr`, with an external physiological reference during training; not medical-grade evidence.
10. **Location, proximity and tracking:** CSI-Bench proximity/localization; WiMANS location annotations; ESPARGOS transmitter channel charting. Distinguish device-free person location from transmitter localization.
11. **Human identity/gait:** SenseFi/NTU-HumanID, WiMANS identities, CSI-Bench HumanIdentification; trained identities and conditions are bounded, with privacy implications.
12. **Pose/skeleton estimation:** Person-in-WiFi 3D with multiple Wi-Fi devices and a GPU model; a much more demanding system than one ESP32 link.
13. **Motion-source classification:** CSI-Bench separates human, pet, robot and fan in a dedicated task. It does not prove human-only counting when human and pet coexist.
14. **Specialized object/scene state:** closed-container object presence in Mobile CSI Object Detection. This is narrow task-specific research, not general visual imaging.
15. **Through-wall/non-line-of-sight sensing:** an experimental setting for presence/activity, demonstrated in the [ESP32 through-wall dataset](https://zenodo.org/records/8021099); wall type, distance, links and rooms control transfer. It is not a separate guarantee attached to every capability.
16. **Application outputs:** lighting, occupancy dashboards, intrusion/motion alerts, elder monitoring and occupancy-aware automation are downstream uses of one or more measured signals. Their names do not prove detection accuracy.
17. **Radio channel modelling:** NeRF2 predicts CSI at positions and can generate synthetic channel examples for communications research. This does not itself infer a person's state.

## SafeSense decision

The realistic sequence is raw capture/quality -> motion and freshness -> controlled vacant/stationary/walking activity -> independent 0/1/2 count experiment. Use PRoFENCH/WiMANS as recorded-data count research and WISDOM/ESP-Fi as separate activity research. Do not merge unrelated datasets' labels into a single claimed human-count/activity/pet model. Animal exclusion, mixed human/pet count, 3D pose, heart rate, or medical/fall safety should remain separate research tasks until relevant target-room data and held-out tests exist. Keep CSI `UNKNOWN` when stale or uncertain; environmental alerts stay actionable without a CSI result.
