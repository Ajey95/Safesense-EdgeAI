"""Deterministic ESP32 20 MHz CSI preprocessing for SafeSense replay/training."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from math import hypot, sqrt
from statistics import mean

ESP32_LLTF_ORDER = tuple(range(0, 32)) + tuple(range(-32, 0))
PILOT_SUBCARRIERS = frozenset({-21, -7, 7, 21})
DATA_SUBCARRIERS_20MHZ = tuple(index for index in range(-26, 27) if index and index not in PILOT_SUBCARRIERS)


class CsiValidationError(ValueError):
    pass


@dataclass(frozen=True)
class CsiFrame:
    """Raw ESP32 LLTF data: each pair is signed imaginary then signed real."""

    iq: tuple[int, ...]
    first_word_invalid: bool
    rssi_dbm: int


@dataclass(frozen=True)
class CsiWindow:
    samples: tuple[tuple[float, ...], ...]
    subcarriers: tuple[int, ...] = DATA_SUBCARRIERS_20MHZ

    @property
    def frame_count(self) -> int:
        return len(self.samples)


def amplitude_frame(frame: CsiFrame) -> tuple[float, ...]:
    """Validate a 64-complex-value LLTF and retain only 48 usable data carriers."""
    if frame.first_word_invalid:
        raise CsiValidationError("ESP32 reported first CSI word invalid")
    if len(frame.iq) != 128:
        raise CsiValidationError("expected one 20 MHz LLTF frame with 128 I/Q bytes")
    if any(value < -128 or value > 127 for value in frame.iq):
        raise CsiValidationError("I/Q values must be signed 8-bit integers")
    amplitudes: dict[int, float] = {}
    for position, subcarrier in enumerate(ESP32_LLTF_ORDER):
        imaginary, real = frame.iq[position * 2 : position * 2 + 2]
        amplitudes[subcarrier] = hypot(real, imaginary)
    return tuple(amplitudes[index] for index in DATA_SUBCARRIERS_20MHZ)


def normalize_window(window: CsiWindow, training_mean: tuple[float, ...], training_std: tuple[float, ...]) -> CsiWindow:
    """Apply frozen training statistics. Never calculate new statistics at inference time."""
    if len(training_mean) != 48 or len(training_std) != 48:
        raise CsiValidationError("normalization vectors must contain 48 values")
    if any(value <= 0 for value in training_std):
        raise CsiValidationError("normalization standard deviations must be positive")
    return CsiWindow(tuple(tuple((value - training_mean[index]) / training_std[index] for index, value in enumerate(sample)) for sample in window.samples), window.subcarriers)


class CsiWindowAssembler:
    """Bounded sliding-window builder; malformed frames never enter model input."""

    def __init__(self, frames_per_window: int = 100, stride: int = 20) -> None:
        if frames_per_window <= 0 or stride <= 0 or stride > frames_per_window:
            raise ValueError("invalid window configuration")
        self.frames_per_window = frames_per_window
        self.stride = stride
        self._frames: deque[tuple[float, ...]] = deque(maxlen=frames_per_window)
        self._new_frames = 0

    def push(self, frame: CsiFrame) -> CsiWindow | None:
        processed = amplitude_frame(frame)
        self._frames.append(processed)
        self._new_frames += 1
        if len(self._frames) < self.frames_per_window:
            return None
        if self._new_frames < self.stride:
            return None
        self._new_frames = 0
        return CsiWindow(tuple(self._frames))


def amplitude_summary(window: CsiWindow) -> tuple[float, ...]:
    if not window.samples:
        return tuple()
    return tuple(round(mean(sample[index] for sample in window.samples), 3) for index in range(48))


def rms_motion(window: CsiWindow) -> float:
    """A transparent replay metric only; not the final trained activity model."""
    if len(window.samples) < 2:
        return 0.0
    deltas = [current[index] - previous[index] for previous, current in zip(window.samples, window.samples[1:]) for index in range(48)]
    return sqrt(sum(delta * delta for delta in deltas) / len(deltas))
