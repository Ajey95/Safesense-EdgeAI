import numpy as np
import pytest

from ml.training.train_profench_count import (
    PAIR_POSITIONS,
    make_windows,
    partition_bounds,
    selected_amplitudes,
)


def test_chronological_partitions_have_no_shared_packets_or_windows():
    packets = 1000
    amplitude = np.ones((packets, 50), dtype=np.float32)
    timestamps = np.arange(packets, dtype=np.float64) * 0.04
    bounds = partition_bounds(packets)

    train_x, _, train_spans = make_windows(amplitude, timestamps, bounds["train"])
    test_x, _, test_spans = make_windows(amplitude, timestamps, bounds["test"])

    assert train_x.shape[1] == test_x.shape[1] == 250
    assert train_spans[-1][1] <= bounds["embargo"][0]
    assert test_spans[0][0] >= bounds["embargo"][1]
    assert train_spans[-1][1] < test_spans[0][0]


def test_live_pair_selection_skips_header_and_rejects_fractional_samples():
    iq = np.zeros(128, dtype=np.float32)
    iq[0:4] = [91, 48, 5, 0]  # CSV header bytes are outside exported carrier positions.
    iq[PAIR_POSITIONS[0] * 2 : PAIR_POSITIONS[0] * 2 + 2] = [3, 4]
    amplitudes = selected_amplitudes(iq)
    assert len(amplitudes) == 50
    assert amplitudes[0] == 5

    iq[PAIR_POSITIONS[0] * 2] = 3.5
    with pytest.raises(ValueError, match="fractional_iq"):
        selected_amplitudes(iq)


def test_timing_gap_rejects_windows_instead_of_splicing_distant_packets():
    amplitude = np.ones((100, 50), dtype=np.float32)
    times = np.arange(100, dtype=np.float64) * 0.04
    times[50:] += 2.0
    with pytest.raises(ValueError, match="No contiguous CSI windows"):
        make_windows(amplitude, times, (0, 100))
