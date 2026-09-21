import numpy as np

from ml.augmentation.physics_csi import synthesize_from_training


def test_synthetic_csi_is_deterministic_shaped_and_nonnegative():
    windows = np.ones((9, 100, 48), dtype=np.float32)
    windows[3:6] += np.linspace(0, 0.1, 100, dtype=np.float32)[:, None]
    windows[6:] += np.sin(np.linspace(0, 4 * np.pi, 100, dtype=np.float32))[:, None]
    labels = np.repeat(np.arange(3), 3)
    first, first_labels = synthesize_from_training(windows, labels, ratio=1.0, seed=7)
    second, second_labels = synthesize_from_training(windows, labels, ratio=1.0, seed=7)
    assert first.shape == (9, 100, 48)
    assert np.all(first >= 0)
    assert np.array_equal(first, second)
    assert np.array_equal(first_labels, second_labels)
