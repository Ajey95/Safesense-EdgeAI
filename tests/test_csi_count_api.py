import base64
import time

import numpy as np
import pytest
from fastapi.testclient import TestClient

from safesense import csi_count_api
from safesense.csi_count_api import assets, live, parse_line, predict
from safesense.csi_packet_journal import append_packets
from safesense.csi_count_features import PAIR_POSITIONS, selected_amplitudes, serial_amplitudes
from safesense.main import app


@pytest.fixture(autouse=True)
def isolated_packet_journal(tmp_path, monkeypatch):
    monkeypatch.setattr(csi_count_api, "append_packets",
                        lambda source, parsed, capture=None: append_packets(
                            source, parsed, tmp_path / "csi_packets.db", capture=capture))


def test_serial_pairs_match_training_selection():
    original = np.zeros(128, dtype=np.int8)
    original[PAIR_POSITIONS[0] * 2:PAIR_POSITIONS[0] * 2 + 2] = [3, 4]
    exported = original.reshape(64, 2)[PAIR_POSITIONS].flatten().tobytes()
    assert np.array_equal(selected_amplitudes(original.astype(np.float32)), serial_amplitudes(exported))
    line = f"WISDOM_CSI,1,1,1000000,-42,0,0,{base64.b64encode(exported).decode()}"
    assert parse_line(line)[-1][0] == 5


def test_full_raw_packet_keeps_model_pair_selection_and_rejects_wrong_size():
    original = np.arange(128, dtype=np.int8)
    full = f"WISDOM_CSI,2,1,1000000,-42,1,0,{base64.b64encode(original.tobytes()).decode()}"
    parsed = parse_line(full)
    assert parsed[-2] == original.tobytes()
    assert np.array_equal(parsed[-1], selected_amplitudes(original.astype(np.float32)))
    assert parsed[-3].shape == (50, 2)
    partial = f"WISDOM_CSI,2,1,1000000,-42,1,0,{base64.b64encode(bytes(100)).decode()}"
    with pytest.raises(ValueError, match="payload length"):
        parse_line(partial)


def test_heldout_replay_prediction_uses_only_signal():
    model, windows, labels, evaluation = assets()
    assert model is not None and evaluation["test_windows"] == len(windows) == 209
    assert windows.shape == (209, 100, 50)
    assert set(labels.tolist()) == {0, 1, 2}
    with TestClient(app) as client:
        for scenario, count in (("empty_room", 0), ("one_person", 1), ("two_people", 2)):
            response = client.get(f"/api/v1/csi-count/replay?scenario={scenario}&index=0")
            assert response.status_code == 200
            body = response.json()
            assert body["recorded_count"] == count
            assert body["scenario"] == scenario
            assert body["input_shape"] == [100, 50]
            assert body["feature_count"] == 250
            assert len(body["signal_trace"]) == 100
            assert body["predicted_count"] == predict(windows[np.flatnonzero(labels == count)[0]])["predicted_count"]
        assert client.get("/api/v1/csi-count/replay?scenario=made_up").status_code == 404


def test_live_count_is_unknown_without_packets_and_ground_truth_cannot_enter_bridge():
    with live.lock:
        live.frames.clear()
        live.prediction = None
        live.last_packet_monotonic = None
    with TestClient(app) as client:
        state = client.get("/api/v1/csi-count/status").json()
        assert state["status"] == "UNKNOWN"
        assert state["predicted_count"] is None
        rejected = client.post("/api/v1/csi-count/packets", json={"lines": ["example"], "actual_count": 2})
        assert rejected.status_code == 422


def test_local_serial_bridge_needs_100_fresh_frames_and_expires():
    with live.lock:
        live.frames.clear()
        live.packet_count = 0
        live.prediction = None
        live.last_sequence = None
        live.last_received_us = None
        live.last_packet_monotonic = None
    def sample(index):
        amplitude = 18 + (index % 7) - 3
        payload = base64.b64encode(bytes([amplitude, 0] * 50)).decode()
        return f"WISDOM_CSI,1,{index},{1_000_000+index*40_000},-42,0,0,{payload}"
    with TestClient(app) as client:
        first = [sample(i) for i in range(1, 100)]
        assert client.post("/api/v1/csi-count/packets", json={"lines": first}).status_code == 200
        assert client.get("/api/v1/csi-count/status").json()["predicted_count"] is None
        last = sample(100)
        assert client.post("/api/v1/csi-count/packets", json={"lines": [last]}).status_code == 200
        ready = client.get("/api/v1/csi-count/status").json()
        assert ready["status"] == "READY"
        assert ready["predicted_count"] in (0, 1, 2)
        assert ready["last_sequence"] == 100
        assert ready["last_rssi_dbm"] == -42
        assert ready["last_packet"]["sequence"] == 100
        assert ready["last_packet"]["board_time_us"] == 5_000_000
        assert ready["last_packet"]["iq_pairs"][0] == [17, 0]
        assert ready["last_packet"]["invalid_first_word"] is False
        assert ready["last_packet"]["payload_bytes"] == 100
        assert len(ready["latest_pair_amplitudes"]) == 50
        assert ready["latest_pair_amplitudes"][0] == 17
        assert len(ready["pair_positions"]) == 50
        with live.lock:
            live.last_packet_monotonic = time.monotonic() - 4
        stale = client.get("/api/v1/csi-count/status").json()
        assert stale["status"] == "UNKNOWN"
        assert stale["predicted_count"] is None
        assert stale["latest_pair_amplitudes"] == []
        assert stale["last_packet"] is None


def test_live_count_abstains_on_signal_far_outside_recorded_range():
    with live.lock:
        live.frames.clear()
        live.packet_count = 0
        live.prediction = None
        live.last_sequence = None
        live.last_received_us = None
        live.last_packet_monotonic = None
    with TestClient(app) as client:
        lines = []
        for i in range(1, 101):
            amplitude = 0 if i % 2 else 40
            payload = base64.b64encode(bytes([amplitude, 0] * 50)).decode()
            lines.append(f"WISDOM_CSI,1,{i},{1_000_000+i*40_000},-42,0,0,{payload}")
        assert client.post("/api/v1/csi-count/packets", json={"lines": lines}).status_code == 200
        state = client.get("/api/v1/csi-count/status").json()
        assert state["source"] == "LIVE_ESP32_SERIAL"
        assert state["packet_count"] == 100
        assert state["status"] == "UNKNOWN"
        assert state["predicted_count"] is None
        assert state["quality_reason"] == "OUTSIDE_RECORDED_SIGNAL_RANGE"


def test_wireless_csi_source_is_reported_from_real_packet_ingest():
    with live.lock:
        live.frames.clear()
        live.packet_count = 0
        live.prediction = None
        live.last_sequence = None
        live.last_received_us = None
        live.last_packet_monotonic = None
        live.last_source = None
    payload = base64.b64encode(bytes([18, 0] * 50)).decode()
    line = f"WISDOM_CSI,1,1,1000000,-42,0,0,{payload}"
    with TestClient(app) as client:
        assert client.post("/api/v1/csi-count/packets", json={
            "source": "ESP32_BLUETOOTH", "lines": [line]}).status_code == 200
        state = client.get("/api/v1/csi-count/status").json()
    assert state["source"] == "LIVE_ESP32_BLUETOOTH"
    assert state["last_packet"]["sequence"] == 1


def test_first_word_flag_does_not_drop_selected_csi_pairs():
    with live.lock:
        live.frames.clear()
        live.packet_count = 0
        live.prediction = None
        live.last_sequence = None
        live.last_received_us = None
        live.last_packet_monotonic = None
    payload = base64.b64encode(bytes([18, 0] * 50)).decode()
    lines = [f"WISDOM_CSI,1,{i},{1_000_000+i*40_000},-42,1,0,{payload}"
             for i in range(1, 101)]
    with TestClient(app) as client:
        response = client.post("/api/v1/csi-count/packets", json={"lines": lines})
        assert response.status_code == 200
        state = client.get("/api/v1/csi-count/status").json()
        assert state["buffered_frames"] == 100
        assert state["last_packet"]["invalid_first_word"] is True


def test_usb_serial_ingress_is_visible_as_usb_route(tmp_path):
    from scripts.direct_laptop_receiver import convert_tx_event
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from safesense.database import Base, get_session
    isolated_engine = create_engine(f"sqlite:///{tmp_path / 'telemetry.db'}")
    Base.metadata.create_all(isolated_engine)
    make_session = sessionmaker(bind=isolated_engine)
    def isolated_session():
        with make_session() as session:
            yield session
    app.dependency_overrides[get_session] = isolated_session
    tx = {"schema_version": 1, "event_id": "tx-usb-test-12345",
          "tx_device_id": "safesense-tx-01", "sequence": 4,
          "bme680": {"sensor_healthy": True, "temperature_c": 30.4,
                     "humidity_pct": 73.8, "pressure_pa": 97847.5,
                     "gas_resistance_ohm": 3954, "gas_valid": True,
                     "heat_stable": True},
          "mq135": {"adc_raw": 0}, "gas_risk": "UNAVAILABLE"}
    payload, _ = convert_tx_event(tx)
    try:
        with TestClient(app) as client:
            response = client.post("/api/v1/telemetry", content=payload.model_dump_json(),
                                   headers={"Content-Type": "application/json",
                                            "X-SafeSense-Ingress": "usb-serial-receiver"})
            assert response.status_code == 202
            events = client.get("/api/v1/live/direct").json()["events"]
            matched = next(event for event in events if event["event_id"] == tx["event_id"])
            assert matched["route"] == "USB_SERIAL"
            assert matched["environment"]["pressure_pa"] == 97847.5
    finally:
        app.dependency_overrides.pop(get_session, None)
