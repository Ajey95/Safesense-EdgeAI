# TinyML Training and Release

`train_wisdom_int8.py` uses the official WISDOM raw ESP32 logs but deliberately implements SafeSense's 48-data-subcarrier extraction rather than WISDOM's helper selection of 50 carriers. This keeps the training shape identical to the firmware: `100 x 48 x 1`.

The default six-class research split is by whole location/trace before windowing: lab+corridor train, parking validation, yard test. The SafeSense product experiment instead uses corridor-only training and lab-only testing so the reported test set is indoor and no recording crosses partitions. A releasable run still needs a separate indoor validation location; the current public dataset cannot provide train, validation, and test locations that are all indoor.

```powershell
$env:PYTHONPATH = "."
python ml\training\cache_wisdom48.py --data data\public\wisdom_har
python ml\training\train_wisdom_int8.py --data data\public\wisdom_har --cache data\cache\wisdom48_windows.npz
python ml\release\verify_partitions.py ml\models\wisdom48_int8\release_manifest.json
python ml\release\verify_release.py --model-dir ml\models\wisdom48_int8
python ml\quantization\tflite_to_c.py ml\models\wisdom48_int8\wisdom48_int8.tflite --normalization ml\models\wisdom48_int8\normalization.npz --out firmware\components\csi\model\wisdom48_model_data.h
```

Release only when `release_manifest.json` exists, reports `int8` input/output, and contains the tested accuracy, macro-F1, split groups, raw-trace hashes, normalization artifact, and SHA-256 hash. The verifier enforces a macro-F1 gate of 0.80 by default; adjust it only through an explicit reviewed decision. WISDOM evidence alone does not establish performance for the final SafeSense room/hardware placement.

The ESP-IDF component defaults to the `UNKNOWN`-returning stub. Enable `SafeSense CSI -> Enable released WISDOM48 INT8 TFLite Micro model` only after the two generated headers are present and the manifest is accepted. The runtime quantizes using the exported training normalization and TFLite input scale; it maps only `empty`, stationary poses, and walking into SafeSense states. `jumping`, low-confidence output, model initialization failures, and unknown labels remain `UNKNOWN`.

`--physics-synthetic-ratio 1.0` adds one physics-informed synthetic training window per real training window. It models static multipath plus a moving reflected path over the 48 OFDM carriers, with class-conditioned path movement and temporal RMS calibrated from real training windows. It never synthesizes, calibrates from, or evaluates on validation/test windows.

The corrected 2026-09-20 real-plus-synthetic candidate is at `ml/models/safesense3_fixed_real_plus_synth/`. It is a fully INT8 6,464-byte artifact, but it is **rejected**, not a release: its untouched real-lab macro-F1 is 0.326 versus the 0.80 gate, and no separate indoor validation location exists in WISDOM. Keep firmware on the fail-closed model stub until a target-room dataset passes `verify_release.py`.
