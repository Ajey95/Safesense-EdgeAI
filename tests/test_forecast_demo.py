from __future__ import annotations

import ctypes
import shutil
import subprocess
from pathlib import Path

import pytest

np = pytest.importorskip("numpy")

from safesense.forecast_model import ForecastModel, features
from safesense.forecast_scenarios import SCENARIOS, first_breach, generate_episode
from safesense.forecast_hardware import parse_demo_result, replay_on_tx
from scripts.bt_alert_receiver import handle_frame, parse_alert, stored_ids


ROOT = Path(__file__).resolve().parents[1]
MODEL = ROOT / "ml/forecast_release/synthetic_v1/model.json"


def test_revealed_breach_reports_already_outside_at_current_minute():
    values = np.array([[-10.0, 50.0, 101325.0, 90000.0, 500.0],
                       [-18.0, 50.0, 101325.0, 90000.0, 500.0]])
    assert first_breach(values, "Cold storage", 0, 1) == (0, "temperature_c")


def test_heldout_families_are_disjoint_and_future_is_not_a_feature():
    training = {s.family for s in SCENARIOS if s.split == "train"}
    heldout = {s.family for s in SCENARIOS if s.split == "test"}
    assert len(heldout) == 8 and training.isdisjoint(heldout)
    scenario = next(s for s in SCENARIOS if s.split == "test")
    values = generate_episode(scenario, 123)
    before = features(values, 75, scenario.room)
    values[76:] = 999
    assert np.array_equal(before, features(values, 75, scenario.room))


def test_exported_c_forecast_matches_dashboard_model(tmp_path):
    compiler = shutil.which("gcc")
    if not compiler:
        pytest.skip("host C compiler unavailable")
    source = ROOT / "firmware/components/forecast/forecast.c"
    library_path = tmp_path / "forecast.dll"
    subprocess.run([compiler, "-shared", "-O2", "-I", str(source.parent / "include"),
                    str(source), "-lm", "-o", str(library_path)], check=True, capture_output=True)
    library = ctypes.CDLL(str(library_path))
    row = ctypes.c_float * 5
    history_type = row * 61
    prediction_type = row * 6
    library.forecast_predict.argtypes = [ctypes.POINTER(row), ctypes.c_uint8, ctypes.POINTER(row)]
    library.forecast_predict.restype = ctypes.c_bool
    model = ForecastModel.load(MODEL)
    scenario = next(s for s in SCENARIOS if s.split == "test")
    values = generate_episode(scenario, 90017)
    history = history_type(*(row(*map(float, v)) for v in values[15:76]))
    output = prediction_type()
    assert library.forecast_predict(history, 0, output)
    predicted_c = np.array([[float(x) for x in row_out] for row_out in output])
    predicted_python = model.predict(values, 75, scenario.room)
    assert np.allclose(predicted_c, predicted_python, rtol=0.0003, atol=1.0)


def test_laptop_receipt_exact_id_and_durable_dedup(tmp_path):
    class Port:
        def __init__(self):
            self.writes = []
        def write(self, data):
            self.writes.append(data)
        def flush(self):
            pass
    port = Port()
    journal = tmp_path / "alerts.jsonl"
    seen = set()
    frame = b"ALERT|tx-abc123456|1|15|3\n"
    assert handle_frame(port, frame, journal, seen, False)["event_id"] == "tx-abc123456"
    assert handle_frame(port, frame, journal, seen, False)
    assert port.writes == [b"ACK|tx-abc123456\n", b"ACK|tx-abc123456\n"]
    assert len(journal.read_text().splitlines()) == 1
    assert stored_ids(journal) == {"tx-abc123456"}
    assert handle_frame(port, b"ALERT|bad|99|15|0\n", journal, seen, False) is None


def test_bluetooth_frames_identify_real_and_synthetic_origin():
    assert parse_alert(b"ALERT|tx-abc123456|1|15|3|R\n")["simulated"] is False
    assert parse_alert(b"ALERT|tx-abc123456|1|15|3|S\n")["simulated"] is True
    assert parse_alert(b"ALERT|tx-abc123456|1|15|3\n")["simulated"] is None


def test_tx_route_result_keeps_receipts_separate():
    result = parse_demo_result("DEMO_RESULT|tx-abc123456|1|0|1|15|3|1")
    assert result["alert"] and result["tx_persisted"] and result["bt_ack"]
    assert not result["rx_ack"]


def test_hardware_replay_sends_history_and_fault_only_on_current_minute(monkeypatch):
    import serial
    import safesense.forecast_hardware as hardware

    class Port:
        def __init__(self):
            self.writes = []
            self.responses = [b"DEMO_READY\n", b"DEMO_FORECAST|-11.5|50|101325|88000|512\n",
                              b"DEMO_RESULT|tx-abc123456|1|0|1|25|0|1\n"]
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def reset_input_buffer(self):
            pass
        def write(self, data):
            self.writes.append(data)
        def flush(self):
            pass
        def readline(self):
            return self.responses.pop(0) if self.responses else b""
    port = Port()
    monkeypatch.setattr(serial, "Serial", lambda *args, **kwargs: port)
    monkeypatch.setattr(hardware.time, "sleep", lambda _: None)
    scenario = next(s for s in SCENARIOS if s.key == "freezer_rebound")
    values = generate_episode(scenario, 90117)
    result = replay_on_tx("COM11", values, 82, scenario.room, True)
    assert result["bt_ack"] and not result["rx_ack"]
    assert len(port.writes) == 62 and port.writes[0] == b"RESET\n"
    assert all(line.rstrip().endswith(b"|0") for line in port.writes[1:-1])
    assert port.writes[-1].rstrip().endswith(b"|1")
