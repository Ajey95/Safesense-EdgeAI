"""Train a small dense model on synthetic episodes; test on held-out families.

Usage: python ml/training/train_synthetic_forecast.py
No hidden simulator parameters, hazard labels, or future sensor samples enter X.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
import hashlib

import numpy as np
from sklearn.neural_network import MLPRegressor
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from safesense.forecast_model import HORIZONS, SENSOR_SCALE, features, persistence, recent_trend, targets  # noqa: E402
from safesense.forecast_scenarios import SCENARIOS, first_breach, generate_episode  # noqa: E402


def examples(split: str, episodes: int, seed_start: int = 0, time_points=(65, 75, 85, 95)):
    x, y, source = [], [], []
    for scenario in SCENARIOS:
        if scenario.split != split:
            continue
        for episode in range(seed_start, seed_start + episodes):
            seed = (10_000 if split == "train" else 90_000) + SCENARIOS.index(scenario) * 1000 + episode
            values = generate_episode(scenario, seed)
            for now in time_points:
                x.append(features(values, now, scenario.room))
                y.append(targets(values, now))
                source.append((scenario, values, now, seed))
    return np.asarray(x), np.asarray(y), source


def evaluate(model, x_scaler, y_scaler, split: str, episodes: int, seed_start: int = 0,
             time_points=(65, 75, 85, 95)):
    x, y, source = examples(split, episodes, seed_start, time_points)
    output = y_scaler.inverse_transform(model.predict(x_scaler.transform(x)))
    pred = np.array([v[n] + output[i].reshape(6, 5) * SENSOR_SCALE for i, (_, v, n, _) in enumerate(source)])
    truth = np.array([v[[n + h for h in HORIZONS]] for _, v, n, _ in source])
    persisted = np.array([persistence(v, n) for _, v, n, _ in source])
    trended = np.array([recent_trend(v, n) for _, v, n, _ in source])
    def mae(estimate):
        return np.mean(np.abs(estimate[:, -1] - truth[:, -1]), axis=0).round(3).tolist()
    def breach_scores(estimate):
        tp = fp = fn = tn = 0
        for i, (scenario, values, now, _) in enumerate(source):
            predicted_path = np.vstack((values[now], estimate[i]))
            actual_path = np.vstack((values[now], truth[i]))
            forecast_hit = first_breach(predicted_path, scenario.room, 0, 6)[0] is not None
            real_hit = first_breach(actual_path, scenario.room, 0, 6)[0] is not None
            tp += forecast_hit and real_hit
            fp += forecast_hit and not real_hit
            fn += not forecast_hit and real_hit
            tn += not forecast_hit and not real_hit
        return {"tp": int(tp), "fp": int(fp), "fn": int(fn), "tn": int(tn),
                "precision": round(tp / (tp + fp), 3) if tp + fp else None,
                "recall": round(tp / (tp + fn), 3) if tp + fn else None}
    return {"episodes": len(set((s.key, seed) for s, _, _, seed in source)), "windows": len(source),
            "mae_30min_by_channel": dict(zip(("temperature_c", "humidity_pct", "pressure_pa", "gas_resistance_ohm", "mq135_adc_raw"), mae(pred))),
            "persistence_mae_30min": mae(persisted), "trend_mae_30min": mae(trended),
            "forecast_breach": breach_scores(pred), "persistence_breach": breach_scores(persisted),
            "trend_breach": breach_scores(trended)}


def main():
    x_train, y_train, _ = examples("train", 60)
    x_scaler = StandardScaler().fit(x_train)
    y_scaler = StandardScaler().fit(y_train)
    model = MLPRegressor(hidden_layer_sizes=(48, 24), activation="relu", solver="adam",
                         max_iter=320, early_stopping=False, random_state=3407)
    model.fit(x_scaler.transform(x_train), y_scaler.transform(y_train))
    artifact = {"schema_version": 1, "model_type": "dense_relu_48_24", "model_location": "TX ESP32 C export",
                "channels": ["temperature_c", "humidity_pct", "pressure_pa", "gas_resistance_ohm", "mq135_adc_raw"],
                "history_minutes": 60, "horizons_minutes": HORIZONS,
                "train_families": sorted({s.family for s in SCENARIOS if s.split == "train"}),
                "heldout_families": sorted({s.family for s in SCENARIOS if s.split == "test"}),
                "x_mean": x_scaler.mean_.tolist(), "x_scale": x_scaler.scale_.tolist(),
                "y_mean": y_scaler.mean_.tolist(), "y_scale": y_scaler.scale_.tolist(),
                "weights": [w.tolist() for w in model.coefs_],
                "biases": [b.tolist() for b in model.intercepts_]}
    out = ROOT / "ml" / "forecast_release" / "synthetic_v1"
    out.mkdir(parents=True, exist_ok=True)
    (out / "model.json").write_text(json.dumps(artifact, separators=(",", ":")), encoding="utf-8")
    model_bytes = (out / "model.json").read_bytes()
    artifact["sha256"] = hashlib.sha256(model_bytes).hexdigest()
    def c_array(name, data):
        flat = np.asarray(data, dtype=np.float32).reshape(-1)
        def literal(value):
            number = f"{float(value):.9g}"
            if "." not in number and "e" not in number:
                number += ".0"
            return number + "f"
        body = ",".join(literal(x) for x in flat)
        return f"static const float {name}[{len(flat)}] = {{{body}}};\n"
    header = "/* Generated by train_synthetic_forecast.py. Synthetic demonstration model. */\n#pragma once\n"
    header += f'#define SAFESENSE_FORECAST_MODEL_SHA256 "{artifact["sha256"]}"\n'
    for name in ("x_mean", "x_scale", "y_mean", "y_scale"):
        header += c_array("forecast_" + name, artifact[name])
    for layer, weight in enumerate(artifact["weights"]):
        header += c_array(f"forecast_w{layer}", weight)
        header += c_array(f"forecast_b{layer}", artifact["biases"][layer])
    release_header = ROOT / "firmware" / "components" / "forecast" / "forecast_model_data.h"
    release_header.parent.mkdir(parents=True, exist_ok=True)
    release_header.write_text(header, encoding="utf-8")
    metrics = {"same_family_new_episodes": evaluate(model, x_scaler, y_scaler, "train", 10, 70),
               "heldout_families": evaluate(model, x_scaler, y_scaler, "test", 20),
               "heldout_one_decision_per_episode": evaluate(model, x_scaler, y_scaler, "test", 20,
                                                              time_points=(75,)),
               "note": "Synthetic simulator only; no real-world hazard or device performance claim."}
    (out / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
