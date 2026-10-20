"""CSI-only feature contract shared by dataset training and ESP32 inference."""

import numpy as np

PAIR_POSITIONS = np.asarray(tuple(range(6, 31)) + tuple(range(33, 58)))
WINDOW_FRAMES = 100
WINDOW_STRIDE = 20
FEATURE_NAMES = tuple(
    f"{stat}_pair_{pair}"
    for stat in ("mean", "std", "mean_abs_delta", "p10", "p90")
    for pair in PAIR_POSITIONS
)


def selected_amplitudes(iq: np.ndarray) -> np.ndarray:
    """Select the 50 pairs exported by the SafeSense RX serial firmware."""
    if iq.shape != (128,):
        raise ValueError("wrong_iq_length")
    if not np.all(np.isfinite(iq)) or np.any(iq < -128) or np.any(iq > 127):
        raise ValueError("out_of_range_iq")
    if np.any(iq != np.rint(iq)):
        raise ValueError("fractional_iq")
    pairs = iq.reshape(64, 2)[PAIR_POSITIONS].astype(np.float32)
    return np.hypot(pairs[:, 0], pairs[:, 1]).astype(np.float32)


def serial_amplitudes(iq_bytes: bytes) -> np.ndarray:
    if len(iq_bytes) != 100:
        raise ValueError("wrong_serial_iq_length")
    pairs = np.frombuffer(iq_bytes, dtype=np.int8).reshape(50, 2).astype(np.float32)
    return np.hypot(pairs[:, 0], pairs[:, 1]).astype(np.float32)


def window_features(amplitudes: np.ndarray) -> np.ndarray:
    """Labels, timestamps, IDs, RSSI and filenames are excluded."""
    if amplitudes.shape != (WINDOW_FRAMES, len(PAIR_POSITIONS)):
        raise ValueError("Expected a 100 x 50 CSI amplitude window")
    return np.concatenate((
        amplitudes.mean(axis=0),
        amplitudes.std(axis=0),
        np.abs(np.diff(amplitudes, axis=0)).mean(axis=0),
        np.percentile(amplitudes, 10, axis=0),
        np.percentile(amplitudes, 90, axis=0),
    )).astype(np.float32)
