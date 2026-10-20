# PRoFENCH CSI-only count baseline — 2026-10-11

## Verdict

Two Random Forest baselines were trained on the user-supplied PRoFENCH/WiVi32
CSI archive. The 0/1/2 model scored **85.65%** exact accuracy and **0.1435**
count MAE on a blocked temporal holdout. The 0–7 model scored **66.30%** exact
accuracy and **0.4291** count MAE. These are **within-recording** results, not
independent-session, new-room, or live SafeSense ESP32 accuracy. Neither model is
approved for an unqualified live people-count display. Even on this limited
0/1/2 holdout, count-2 recall is **54/70 = 0.771**, below the project's proposed
0.80 per-count recall gate.

## Data and split

- Input: eight count-labelled CSVs inside
  `C:\Users\AJEYA\Downloads\PRoFENCH-Dataset-20261008T082054Z-1-001.zip`.
  No camera images or YOLO annotations entered training or inference.
- For each count separately, the first 70% of valid chronological packets went
  to training, the next 10% were unused as an embargo, and the last 20% went
  to testing. Packet partitions were made **before** constructing 100-packet,
  20-packet-stride windows. Windows with a packet gap greater than 0.5 seconds
  were discarded. The actual unused gap between the last training window and
  first test window was 701–756 valid packets across the eight recordings.
- Features are mean, standard deviation, mean absolute packet-to-packet
  difference, 10th percentile and 90th percentile of CSI amplitude for each of
  50 I/Q pair positions. Pair positions match the present RX serial export.
  `sample_ID`, timestamps, filenames, RSSI, radio metadata, images, and labels
  were excluded from model features. Training used 300 trees, leaf size 3,
  `random_state=42`, and no normalization learned from test data.
- The archive contains fractional I/Q rows that cannot be reproduced by the
  receiver's signed-byte serial format. They were excluded: 342 / 0 / 125 /
  223 / 218 / 240 / 230 / 336 rows for counts 0–7. One count-1 row with 133
  values was also excluded. The class-4 CSV omits a label column; its 7,407
  accepted rows were assigned the target **4** from the file name, never used
  as an input feature. Per-file hashes and rejection reasons are in the saved
  `evaluation.json` files.

## Held-out results

| Count scope | Train windows | Test windows | Exact accuracy | Balanced accuracy | Macro-F1 | Count MAE | Majority accuracy |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 0/1/2 | 764 | 209 | 0.8565 | 0.8581 | 0.8581 | 0.1435 | 0.3397 |
| 0–7 | 1,982 | 543 | 0.6630 | 0.6657 | 0.6541 | 0.4291 | 0.1308 |

The 0/1/2 confusion matrix has actual counts in rows and predicted counts in
columns:

| Actual \ Predicted | 0 | 1 | 2 |
| --- | ---: | ---: | ---: |
| 0 | 68 | 0 | 0 |
| 1 | 0 | 57 | 14 |
| 2 | 0 | 16 | 54 |

The complete 0–7 confusion matrix and per-class precision/recall are in
`ml/models/profench_count_0to7_blocked/evaluation.json`.

## Leakage boundary and next gate

No source packet or window crosses the temporal partition, and count labels
and capture metadata do not enter the features. However, the ZIP supplies
**only one contiguous recording for each count**. Every test class therefore
shares its room, radio link, equipment and capture session with its training
class. Count is confounded with recording identity. An embargo cannot remove
that confounding; a truly independent, leakage-resistant generalization test
is impossible with this archive alone.

The next acceptance test must use new, complete 0/1/2 recordings from the
actual SafeSense TX/RX pair in the demonstration room. Freeze the model and
preprocessing first, then compare its predictions with manually recorded
ground truth. If the new-room or new-session performance fails, display
`UNKNOWN` and keep this model labelled as recorded-data research only.

## Reproduction and artifacts

Training code: `ml/training/train_profench_count.py`. The generated local
artifacts (ignored by Git) are:

- `ml/models/profench_count_012_blocked/model.joblib`, `evaluation.json`, and
  `replay_windows.npz` (all 209 held-out 100 × 50 amplitude windows)
- `ml/models/profench_count_0to7_blocked/model.joblib` and `evaluation.json`

Run from the repository root:

```powershell
.\.venv\Scripts\python.exe ml\training\train_profench_count.py --counts 0 1 2 --output ml\models\profench_count_012_blocked
.\.venv\Scripts\python.exe ml\training\train_profench_count.py --counts 0 1 2 3 4 5 6 7 --output ml\models\profench_count_0to7_blocked
.\.venv\Scripts\python.exe -m pytest -q tests\test_profench_count.py
```

The command without `--inner-zip` temporarily unpacks the nested ZIP to the
system temp directory and removes that copy automatically. The held-out
0/1/2 features were independently regenerated from the ZIP after training;
reloaded `model.joblib` reproduced the stored 209-window accuracy exactly.
