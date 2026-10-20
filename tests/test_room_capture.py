from datetime import datetime, timedelta, timezone

import numpy as np
from fastapi.testclient import TestClient

from safesense.main import app
from safesense.room_capture import RoomCaptureStore


def test_room_capture_persists_interval_windows_and_label_provenance(tmp_path):
    path = tmp_path / "room.db"
    store = RoomCaptureStore(path)
    start = datetime(2026, 10, 20, 12, 0, tzinfo=timezone.utc)
    session = store.start("Lab A", interval_seconds=10, label_count=0, at=start)
    window = np.ones((100, 50), dtype=np.float32)
    assert store.maybe_capture(window, 100, -42, {"predicted_count": 2,
                                "model_score": 0.75, "quality_reason": None},
                               at=start + timedelta(seconds=9)) is None
    first = store.maybe_capture(window, 101, -42, {"predicted_count": 2,
                               "model_score": 0.75, "quality_reason": None},
                              at=start + timedelta(seconds=10))
    assert first["label_count"] == 0
    assert first["label_source"] == "OPERATOR"
    assert first["predicted_count"] == 2  # The prediction is never the label.
    assert store.maybe_capture(window, 102, -42, {},
                               at=start + timedelta(seconds=11)) is None
    store.set_label(1, at=start + timedelta(seconds=12))
    second = store.maybe_capture(window, 103, -41, {},
                                 at=start + timedelta(seconds=22))
    assert second["label_count"] == 1
    assert RoomCaptureStore(path).status()["saved_windows"] == 2
    assert RoomCaptureStore(path).status()["label_counts"] == {
        "0": 1, "1": 1, "2": 0, "unlabelled": 0}
    assert RoomCaptureStore(path).status()["room"] == "Lab A"
    exported = store.export(session["session_id"], tmp_path / "room.npz")
    with np.load(exported["path"]) as archive:
        assert archive["amplitudes"].shape == (2, 100, 50)
        assert archive["operator_labels"].tolist() == [0, 1]
        assert archive["model_predictions"].tolist() == [2, -1]
    assert exported["verified_labels"] == 2
    store.stop(at=start + timedelta(seconds=23))
    assert RoomCaptureStore(path).status()["active"] is False
    assert session["session_id"]


def test_unlabelled_capture_does_not_copy_model_prediction(tmp_path):
    store = RoomCaptureStore(tmp_path / "room.db")
    start = datetime(2026, 10, 20, 12, 0, tzinfo=timezone.utc)
    store.start("Room 2", interval_seconds=5, label_count=None, at=start)
    captured = store.maybe_capture(np.ones((100, 50)), 100, -50,
                                   {"predicted_count": 1}, at=start + timedelta(seconds=5))
    assert captured["label_count"] is None
    assert captured["label_source"] == "UNLABELLED"
    assert store.status()["label_counts"]["unlabelled"] == 1
    exported = store.export(store.status()["session_id"], tmp_path / "unlabelled.npz")
    with np.load(exported["path"]) as archive:
        assert archive["operator_labels"].tolist() == [-1]
        assert archive["model_predictions"].tolist() == [1]


def test_room_capture_controls_are_local_and_require_operator_label(monkeypatch, tmp_path):
    from safesense import csi_count_api
    monkeypatch.setattr(csi_count_api, "room_store", RoomCaptureStore(tmp_path / "room.db"))
    with TestClient(app) as client:
        assert client.post("/api/v1/csi-count/room-capture", json={
            "room": "Lab A", "interval_seconds": 10, "label_count": 0}).status_code == 403
        response = client.post("/api/v1/csi-count/room-capture", json={
            "room": "Lab A", "interval_seconds": 10, "label_count": 0},
            headers={"X-SafeSense-Control": "dashboard"})
        assert response.status_code == 200
        assert response.json()["active"] is True
        assert response.json()["label_source"] == "OPERATOR"
        response = client.post("/api/v1/csi-count/room-capture/label", json={
            "label_count": 1}, headers={"X-SafeSense-Control": "dashboard"})
        assert response.status_code == 200
        assert response.json()["label_count"] == 1
        assert client.get("/api/v1/csi-count/room-capture").json()["room"] == "Lab A"
