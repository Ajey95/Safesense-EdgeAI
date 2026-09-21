import pytest

from safesense.csi import CsiFrame, CsiValidationError, CsiWindowAssembler, DATA_SUBCARRIERS_20MHZ, amplitude_frame, normalize_window


def raw_frame(*, invalid=False):
    return CsiFrame(tuple([3, 4] * 64), invalid, -50)


def test_retains_exactly_48_usable_subcarriers():
    amplitude = amplitude_frame(raw_frame())
    assert len(amplitude) == 48
    assert len(DATA_SUBCARRIERS_20MHZ) == 48
    assert amplitude[0] == 5.0


def test_rejects_invalid_first_word_instead_of_shifting_features():
    with pytest.raises(CsiValidationError, match="first CSI word"):
        amplitude_frame(raw_frame(invalid=True))


def test_window_is_bounded_and_only_emits_on_stride():
    assembler = CsiWindowAssembler(frames_per_window=3, stride=2)
    assert assembler.push(raw_frame()) is None
    assert assembler.push(raw_frame()) is None
    first = assembler.push(raw_frame())
    assert first and first.frame_count == 3
    assert assembler.push(raw_frame()) is None
    assert assembler.push(raw_frame()).frame_count == 3


def test_normalization_refuses_non_frozen_invalid_statistics():
    assembler = CsiWindowAssembler(frames_per_window=1, stride=1)
    window = assembler.push(raw_frame())
    with pytest.raises(CsiValidationError, match="positive"):
        normalize_window(window, tuple([0.0] * 48), tuple([0.0] * 48))
