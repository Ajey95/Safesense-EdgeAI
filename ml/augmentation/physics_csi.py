"""Physics-informed amplitude augmentation for 20 MHz ESP32 Wi-Fi CSI.

This is augmentation, not a replacement for measured CSI.  It synthesizes a
static multipath channel plus a moving reflected path and calibrates the output
RMS to real *training* windows only.
"""
from __future__ import annotations

import numpy as np

SUBCARRIERS = np.asarray(
    [carrier for carrier in range(-26, 27) if carrier and carrier not in {-21, -7, 7, 21}],
    dtype=np.float32,
)
SPEED_OF_LIGHT = 299_792_458.0
CARRIER_HZ = 2.437e9  # WISDOM records use 2.4 GHz channel 6.
SUBCARRIER_SPACING_HZ = 20e6 / 64.0


def _target_rms(windows: np.ndarray, labels: np.ndarray, label: int) -> float:
    selected = windows[labels == label]
    centered = selected - selected.mean(axis=1, keepdims=True)
    return float(np.median(np.sqrt(np.mean(centered * centered, axis=(1, 2)))))


def _path_length(time_s: np.ndarray, label: int, rng: np.random.Generator) -> np.ndarray:
    """A conservative reflected-path trajectory in metres for each SafeSense class."""
    if label == 0:  # vacant: receiver oscillator/noise scale only
        return rng.normal(0.0, 0.001, size=time_s.size)
    if label == 1:  # stationary: breathing/posture micro-motion
        frequency = rng.uniform(0.12, 0.35)
        amplitude = rng.uniform(0.001, 0.012)
    else:  # walking: torso/limb reflection path change, not a literal body path
        frequency = rng.uniform(0.8, 2.2)
        amplitude = rng.uniform(0.03, 0.18)
    phase = rng.uniform(0.0, 2.0 * np.pi)
    return amplitude * np.sin(2.0 * np.pi * frequency * time_s + phase)


def synthesize_from_training(
    windows: np.ndarray,
    labels: np.ndarray,
    ratio: float,
    seed: int = 20260920,
    sample_rate_hz: float = 100.0,
) -> tuple[np.ndarray, np.ndarray]:
    """Create labelled synthetic amplitude windows using only real train windows.

    The complex channel is H_k(t)=H_static,k + beta exp(-j 2pi f_k tau(t)).
    tau(t) is a class-conditioned reflected-path delay.  The final temporal RMS
    is matched to the corresponding real training-class median to avoid
    unrealistic synthetic signal power.
    """
    if windows.ndim != 3 or windows.shape[1:] != (100, 48):
        raise ValueError("expected real training windows shaped (N, 100, 48)")
    if not 0.0 <= ratio <= 2.0:
        raise ValueError("ratio must be between 0 and 2")
    rng = np.random.default_rng(seed)
    count = int(round(len(windows) * ratio))
    if not count:
        return np.empty((0, 100, 48), dtype=np.float32), np.empty((0,), dtype=labels.dtype)
    time_s = np.arange(100, dtype=np.float32) / sample_rate_hz
    frequencies = CARRIER_HZ + SUBCARRIERS * SUBCARRIER_SPACING_HZ
    class_rms = {label: max(_target_rms(windows, labels, label), 1e-4) for label in np.unique(labels)}
    synthetic = np.empty((count, 100, 48), dtype=np.float32)
    synthetic_labels = np.empty((count,), dtype=labels.dtype)
    for output in range(count):
        source_index = int(rng.integers(len(windows)))
        label = int(labels[source_index])
        baseline = np.median(windows[source_index], axis=0)
        # Unknown static-path phases are sampled, while their observed amplitude
        # profile comes from the real source room/device window.
        static = baseline * np.exp(1j * rng.uniform(-np.pi, np.pi, size=48))
        path_m = _path_length(time_s, label, rng)
        delay_s = (rng.uniform(1.0, 8.0) + path_m) / SPEED_OF_LIGHT
        reflection_gain = rng.uniform(0.02, 0.22) * np.median(baseline)
        dynamic = reflection_gain * np.exp(-2j * np.pi * delay_s[:, None] * frequencies[None, :])
        amplitude = np.abs(static[None, :] + dynamic)
        centered = amplitude - amplitude.mean(axis=0, keepdims=True)
        rms = max(float(np.sqrt(np.mean(centered * centered))), 1e-6)
        amplitude = baseline[None, :] + centered * (class_rms[label] / rms)
        amplitude += rng.normal(0.0, class_rms[label] * 0.05, size=amplitude.shape)
        synthetic[output] = np.maximum(amplitude, 0.0)
        synthetic_labels[output] = label
    return synthetic, synthetic_labels
