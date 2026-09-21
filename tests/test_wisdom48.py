from ml.preprocessing.wisdom48 import DATA_CARRIERS, EDGE_POSITIONS, RAW_ORDER, _frame


def test_48_carriers_match_edge_order_and_iq_amplitude():
    values = []
    for index in range(64):
        values.extend((index, index + 1))  # imaginary, real as ESP CSI payload stores them
    metadata = ["STA", "00:00:00:00:00:00"] + ["0"] * 22
    line = "CSI_DATA," + ",".join(metadata + ["[" + " ".join(map(str, values)) + "]"])
    frame = _frame(line)
    assert frame is not None
    assert frame.shape == (48,)
    first = EDGE_POSITIONS[0]
    assert frame[0] == ((first * first + (first + 1) * (first + 1)) ** 0.5)
    assert len(DATA_CARRIERS) == 48
    expected = tuple(
        carrier
        for carrier in RAW_ORDER
        if -26 <= carrier <= 26 and carrier and carrier not in {-21, -7, 7, 21}
    )
    assert DATA_CARRIERS == expected
    assert DATA_CARRIERS[0] == 1
    assert DATA_CARRIERS[23] == 26
    assert DATA_CARRIERS[24] == -26


def test_malformed_or_wrong_length_logs_are_rejected():
    assert _frame("not csi") is None
    assert _frame("CSI_DATA," + ",".join(["0"] * 25)) is None
