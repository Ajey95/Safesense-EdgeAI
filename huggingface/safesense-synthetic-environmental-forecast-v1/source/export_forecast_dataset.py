"""Export the versioned synthetic trajectories used by Forecast Lab.

The CSV is evidence of the simulation inputs, not evidence of real incidents.
Held-out scenario families are explicitly marked and never used for fitting.
"""

from __future__ import annotations

import csv
import gzip
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from safesense.forecast_scenarios import CHANNELS, SCENARIOS, generate_episode, safe_limits  # noqa: E402


def main():
    out = ROOT / "data" / "forecast_synthetic_v1.csv.gz"
    out.parent.mkdir(exist_ok=True)
    episodes = {"train": 60, "test": 20}
    with gzip.open(out, "wt", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(("episode_id", "split", "scenario_family", "scenario_key", "room", "minute", *CHANNELS))
        for scenario in SCENARIOS:
            for episode in range(episodes[scenario.split]):
                seed = (10_000 if scenario.split == "train" else 90_000) + SCENARIOS.index(scenario) * 1000 + episode
                episode_id = f"{scenario.key}-{episode:03d}"
                for minute, row in enumerate(generate_episode(scenario, seed)):
                    writer.writerow((episode_id, scenario.split, scenario.family, scenario.key,
                                     scenario.room, minute, *[f"{float(v):.4f}" for v in row]))
    manifest = {"version": "synthetic_v1", "sampling": "one synthetic minute per row",
                "history_minutes": 60, "forecast_minutes": 30,
                "training_examples": "complete episodes, no window-level random train/test split",
                "sensor_semantics": {"gas_resistance_ohm": "non-specific BME680 gas response",
                                     "mq135_adc_raw": "uncalibrated raw ADC; not ppm or chemical identity"},
                "room_demo_ranges": {s.room: safe_limits(s.room) for s in SCENARIOS},
                "scenarios": [{"key": s.key, "title": s.title, "room": s.room,
                               "family": s.family, "split": s.split, "story": s.story,
                               "episodes": episodes[s.split]} for s in SCENARIOS],
                "limitations": "Entirely synthetic and not calibrated or validated for real safety decisions."}
    (ROOT / "ml/forecast_release/synthetic_v1/dataset_manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8")
    print(out)


if __name__ == "__main__":
    main()
