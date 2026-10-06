"""Compact six-horizon forecast model and episode-safe feature extraction."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from .forecast_scenarios import ROOMS


HISTORY_MINUTES = 60
HORIZONS = (5, 10, 15, 20, 25, 30)
SENSOR_SCALE = np.array((10.0, 20.0, 1000.0, 100000.0, 1000.0), dtype=np.float32)


def features(values: np.ndarray, now: int, room: str) -> np.ndarray:
    """Only sensor history through `now` and declared room enter the model."""
    if room not in ROOMS or now < HISTORY_MINUTES or now >= len(values):
        raise ValueError("need a valid room and at least 60 observed minutes")
    if values.shape[1] != 5 or not np.isfinite(values[now - HISTORY_MINUTES:now + 1]).all():
        raise ValueError("five finite sensor channels are required")
    history = values[now - HISTORY_MINUTES:now + 1:5].astype(np.float32)
    scaled = history / SENSOR_SCALE
    room_bits = np.zeros(len(ROOMS), dtype=np.float32)
    room_bits[ROOMS.index(room)] = 1
    return np.concatenate((scaled.reshape(-1), room_bits))


def targets(values: np.ndarray, now: int) -> np.ndarray:
    if now + max(HORIZONS) >= len(values):
        raise ValueError("future is unavailable for training target")
    # Predict future deltas from the current value; this conditions on each room.
    return ((values[[now + h for h in HORIZONS]] - values[now]) / SENSOR_SCALE).reshape(-1)


class ForecastModel:
    def __init__(self, artifact: dict):
        self.artifact = artifact
        self.x_mean = np.array(artifact["x_mean"], dtype=np.float32)
        self.x_scale = np.array(artifact["x_scale"], dtype=np.float32)
        self.y_mean = np.array(artifact["y_mean"], dtype=np.float32)
        self.y_scale = np.array(artifact["y_scale"], dtype=np.float32)
        self.weights = [np.array(w, dtype=np.float32) for w in artifact["weights"]]
        self.biases = [np.array(b, dtype=np.float32) for b in artifact["biases"]]
        if self.weights[0].shape[0] != 70 or self.weights[-1].shape[1] != 30:
            raise ValueError("unexpected forecast model dimensions")

    @classmethod
    def load(cls, path: str | Path) -> "ForecastModel":
        with open(path, encoding="utf-8") as handle:
            return cls(json.load(handle))

    def predict(self, values: np.ndarray, now: int, room: str) -> np.ndarray:
        x = (features(values, now, room) - self.x_mean) / self.x_scale
        for weight, bias in zip(self.weights[:-1], self.biases[:-1]):
            x = np.maximum(0, x @ weight + bias)
        y = (x @ self.weights[-1] + self.biases[-1]) * self.y_scale + self.y_mean
        return values[now] + y.reshape(len(HORIZONS), 5) * SENSOR_SCALE


def persistence(values: np.ndarray, now: int) -> np.ndarray:
    return np.repeat(values[now][None, :], len(HORIZONS), axis=0)


def recent_trend(values: np.ndarray, now: int) -> np.ndarray:
    slope = (values[now] - values[now - 10]) / 10.0
    return np.array([values[now] + h * slope for h in HORIZONS])
