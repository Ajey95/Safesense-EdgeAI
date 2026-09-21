import numpy as np

from ml.training.train_wisdom_int8 import balanced_representative_indices


def test_representative_indices_cover_each_class_evenly():
    labels = np.asarray([0] * 500 + [1] * 20 + [2] * 200)
    selected = balanced_representative_indices(labels, limit=60)
    assert dict(zip(*np.unique(labels[selected], return_counts=True))) == {0: 20, 1: 20, 2: 20}
    assert len(np.unique(selected)) == len(selected)
