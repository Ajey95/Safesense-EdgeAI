# PRoFENCH / WiVi32-Count fit for SafeSense CSI — 2026-10-09

## Decision

Use the supplied archive for a **CSI-only people-counting research baseline** (especially 0/1/2 people) and preprocessing experiments. It does not provide activity, fall, or pet labels, and it cannot establish reliable counting in the SafeSense room or on the current live board without separately recorded target-room evaluation. No training or model accuracy was measured in this audit.

## Evidence inspected

Source archive: `C:\Users\AJEYA\Downloads\PRoFENCH-Dataset-20261008T082054Z-1-001.zip`. Its only entry is a nested `wivi32-dataset.zip` (1,992,302,013 bytes). The nested archive contains eight CSI CSV files, 60,175 JPEG frames, and 60,175 YOLO-style text files, all under `csi-cv-combined-1/dataset_final/train/`. It has no bundled README, session manifest, validation directory, or test directory.

The eight CSI files have 60,044 packet rows across class IDs 0–7: 7,625 / 7,519 / 7,525 / 7,225 / 7,625 / 7,500 / 7,625 / 7,400. The rows contain timestamps, RSSI, radio metadata, a raw I/Q `data` array, and usually a `label` field. 60,043 rows have 128 I/Q values; row `1_0039` has 133 and needs rejection or repair with provenance. `csi_4.csv` has no `label` column; its class is inferable from the file name, but a loader must document and verify that assumption.

The CSI for each class is one approximately five-minute contiguous run on 2025-08-22 or 2025-08-23, at about 24–25 packets/s; no independent repeat of any class is identified in this archive. All rows inspected use the same MAC and Wi-Fi channel 1. The images/labels are not perfectly joined to CSI by ID: most classes have an image `*_0000` without a CSI row and a last CSI ID without an image; class 1 has 131 extra image IDs. Class 1 also has 1,764 empty image annotation files although its CSI rows have count label 1. Those are annotation/visibility mismatches, not proof that the room was empty.

The [author repository](https://github.com/cvwifi-lab/WiVi32-A_People_Counting_Tool) describes an ESP32 transmitter/receiver, synchronized camera ground truth, and count classes 0–7. It describes a 70/10/20 train/validation/test split, but those directories are absent from this supplied archive. The [PRoFENCH paper](https://www.sciencedirect.com/science/article/pii/S1570870526002544) studies people counting and multimodal fusion; its reported error is not SafeSense CSI-only or live-room performance. The repository requests academic/noncommercial access, so check dataset-use permission before redistribution.

## SafeSense use and limits

- SafeSense's current firmware extracts 48 amplitudes from 128 raw I/Q bytes and uses 100-packet windows with stride 20. A dataset adapter must verify the I/Q order, first-word validity, carrier selection, packet gaps, and feature parity before training. A 100-packet window here spans roughly four seconds, subject to real timestamp gaps.
- Use `label`/file class as the count target only, never `sample_ID`, timestamp, file name, image/YOLO information, or count-specific capture metadata as model features. For a camera-free claim, keep images out of inference; they can help audit labels.
- Treat random packet/window splits as contaminated because neighboring packets and windows share each contiguous recording. The supplied archive alone cannot support a convincing independent 0–7-class held-out test; each class appears to have only one run. Ask the authors for session-level partitions/additional independent takes, or collect fresh 0/1/2 recordings in the target room and hold out complete later takes/days.
- Count evaluation should include exact accuracy, mean absolute error, per-class recall, confusion matrix, and abstention coverage. Show 0, stationary 1, and stationary/moving 2 separately. Keep unsupported/stale output `UNKNOWN`/unavailable, not 0 or vacant.
- No activity/posture, falls, pets, mixed human/pet, or deployment reliability can be learned or claimed from the count labels alone. Keep those tasks separate.

## Suggested next experiment

Build a small CSI-only loader for classes 0/1/2, reject malformed rows, and version the carrier extraction. Train a simple baseline as an exploratory comparison. Reserve new SafeSense room sessions for final testing, including empty, seated/still one person, walking one person, and still/moving two people. Report public-data and target-room results separately. Enable a live count display only if the target-room held-out gate in `docs/csi_two_day_decision.md` passes.
