# WiVi32 / PRoFENCH CSI recordings with reconstructed dates

These eight CSV files are derived from the WiVi32 / PRoFENCH count recordings
described by the [dataset authors](https://github.com/cvwifi-lab/WiVi32-A_People_Counting_Tool).
The SafeSense project owner reports written permission to republish these CSVs.
Credit and access conditions for the original dataset remain with its authors.

**The dates in these files are reconstructed, not exact capture dates.** The
project owner supplied the range September 25 through October 18, 2026, and
asked for the eight recordings to be placed approximately evenly across it.
Within each file, the original time of day, subsecond values, and packet
intervals were preserved. The source CSV did not specify a timezone, so none
was inferred. Do not use these assigned calendar dates as ground truth for
session timing, independent-day validation, or model features.

| File | Assigned date | Packet rows |
| --- | --- | ---: |
| `train/csi/csi_7.csv` | 2026-09-25 | 7,400 |
| `train/csi/csi_6.csv` | 2026-09-28 | 7,625 |
| `train/csi/csi_5.csv` | 2026-10-02 | 7,500 |
| `train/csi/csi_4.csv` | 2026-10-05 | 7,625 |
| `train/csi/csi_3.csv` | 2026-10-08 | 7,225 |
| `train/csi/csi_2.csv` | 2026-10-11 | 7,525 |
| `train/csi/csi_1.csv` | 2026-10-15 | 7,519 |
| `train/csi/csi_0.csv` | 2026-10-18 | 7,625 |

`CSI_TIMESTAMP_RECONSTRUCTION.json` records the original and reconstructed
first/last timestamps and SHA-256 hashes for each CSV. Only the `timestamp`
field was changed; the radio metadata, raw I/Q arrays, and labels were copied
from the supplied recordings. Known source issues remain, including a missing
label column in `csi_4.csv` and one malformed I/Q row in `csi_1.csv`.

These are research recordings, not live SafeSense room captures. They support
an exploratory people-counting baseline; they do not establish live-room count
accuracy or safety detection performance.
