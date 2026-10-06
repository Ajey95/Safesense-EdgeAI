"""Package the existing SafeSense synthetic CSV for a Hugging Face dataset repo."""

from __future__ import annotations

import gzip
import shutil
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data" / "forecast_synthetic_v1.csv.gz"
RELEASE = ROOT / "huggingface" / "safesense-synthetic-environmental-forecast-v1"
EXPECTED_COLUMNS = (
    "episode_id", "split", "scenario_family", "scenario_key", "room", "minute",
    "temperature_c", "humidity_pct", "pressure_pa", "gas_resistance_ohm", "mq135_adc_raw",
)


def main() -> None:
    if not SOURCE.is_file():
        raise FileNotFoundError(SOURCE)
    with gzip.open(SOURCE, "rt", encoding="utf-8", newline="") as handle:
        frame = pd.read_csv(handle)
    if tuple(frame.columns) != EXPECTED_COLUMNS or frame.isna().any().any():
        raise ValueError("source CSV has unexpected columns or missing values")
    if frame.duplicated(("episode_id", "minute")).any():
        raise ValueError("duplicate episode-minute rows")
    expected = {"train": (90600, 600, 10), "test": (24160, 160, 8)}
    families: dict[str, set[str]] = {}
    for split, (rows, episodes, family_count) in expected.items():
        part = frame.loc[frame["split"] == split]
        if len(part) != rows or part["episode_id"].nunique() != episodes:
            raise ValueError(f"unexpected {split} size")
        if part.groupby("episode_id")["minute"].agg(["count", "min", "max"]).ne(
            [151, 0, 150]
        ).any().any():
            raise ValueError(f"incomplete {split} episode")
        families[split] = set(part["scenario_family"])
        if len(families[split]) != family_count:
            raise ValueError(f"unexpected {split} family count")
        destination = RELEASE / "data" / f"{split}.parquet"
        destination.parent.mkdir(parents=True, exist_ok=True)
        part.to_parquet(destination, index=False, compression="zstd")
    if families["train"] & families["test"]:
        raise ValueError("test scenario families overlap training")
    if sum(rows for rows, _, _ in expected.values()) != len(frame):
        raise ValueError("unexpected split value")
    source_dir = RELEASE / "source"
    source_dir.mkdir(parents=True, exist_ok=True)
    for source, name in (
        (SOURCE, SOURCE.name),
        (ROOT / "ml/forecast_release/synthetic_v1/dataset_manifest.json", "dataset_manifest.json"),
        (ROOT / "src/safesense/forecast_scenarios.py", "forecast_scenarios.py"),
        (ROOT / "scripts/export_forecast_dataset.py", "export_forecast_dataset.py"),
    ):
        shutil.copyfile(source, source_dir / name)
    print(f"Prepared {len(frame):,} synthetic rows in {RELEASE}")


if __name__ == "__main__":
    main()
