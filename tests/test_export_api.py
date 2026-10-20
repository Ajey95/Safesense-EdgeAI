"""CSV downloads preserve source evidence and the actual captured values."""

import base64
import csv
import io
import json
import sqlite3
import zipfile
from datetime import datetime, timedelta, timezone

import numpy as np
from fastapi.testclient import TestClient

from safesense import csi_count_api, export_api
from safesense.csi_count_api import parse_line
from safesense.csi_packet_journal import append_packets
from safesense.main import app
from safesense.room_capture import RoomCaptureStore


def _rows(response):
    assert response.status_code == 200
    return list(csv.DictReader(io.StringIO(response.content.decode("utf-8-sig"))))


def test_packet_export_keeps_all_transmitted_iq_and_wireless_source(tmp_path, monkeypatch):
    path = tmp_path / "packets.db"
    monkeypatch.setattr(export_api, "PACKET_DB", path)
    payload = bytes(range(100))
    line = f"WISDOM_CSI,1,7,70000,-48,1,2,{base64.b64encode(payload).decode()}"
    append_packets("ESP32_BLUETOOTH", [parse_line(line)], path)
    with TestClient(app) as client:
        rows = _rows(client.get("/api/v1/exports/csi-packets.csv"))
    assert len(rows) == 1
    assert rows[0]["source"] == "ESP32_BLUETOOTH"
    assert rows[0]["sequence"] == "7"
    assert rows[0]["rssi_dbm"] == "-48"
    assert json.loads(rows[0]["selected_iq_data"]) == list(range(100))
    assert rows[0]["full_128_iq_available"] == "False"
    assert rows[0]["data"] == ""
    assert rows[0]["label"] == ""


def test_full_iq_packet_export_preserves_operator_label_and_selected_pairs(tmp_path, monkeypatch):
    path = tmp_path / "packets.db"
    monkeypatch.setattr(export_api, "PACKET_DB", path)
    monkeypatch.setattr(export_api, "_sqlite_sources", lambda: [("csi_packets", path)])
    full_iq = np.arange(128, dtype=np.int8).tobytes()
    line = f"WISDOM_CSI,2,8,80000,-48,1,2,{base64.b64encode(full_iq).decode()}"
    capture = {"active": True, "session_id": "session-1", "room": "Lab",
               "label_count": 1, "label_source": "OPERATOR"}
    append_packets("ESP32_WIFI", [parse_line(line)], path, capture=capture)
    with TestClient(app) as client:
        rows = _rows(client.get("/api/v1/exports/csi-packets.csv"))
        zipped = client.get("/api/v1/exports/sqlite-tables.zip")
    assert len(rows) == 1
    assert rows[0]["source"] == "ESP32_WIFI"
    assert rows[0]["session_id"] == "session-1"
    assert rows[0]["label"] == "1"
    assert json.loads(rows[0]["data"]) == list(range(128))
    assert len(json.loads(rows[0]["selected_iq_data"])) == 100
    assert rows[0]["full_128_iq_available"] == "True"
    assert rows[0]["source_format"] == "FULL_128_RAW_IQ"
    with zipfile.ZipFile(io.BytesIO(zipped.content)) as archive:
        packet_rows = list(csv.DictReader(io.StringIO(
            archive.read("csi_packets/packets.csv").decode("utf-8-sig"))))
        raw_rows = list(csv.DictReader(io.StringIO(
            archive.read("csi_packets/packets_raw_blob.csv").decode("utf-8-sig"))))
    assert packet_rows[0]["data"] == rows[0]["data"]
    assert "raw_iq" not in packet_rows[0]
    assert raw_rows[0]["raw_iq"]


def test_packet_journal_migrates_earlier_selected_only_rows(tmp_path):
    path = tmp_path / "earlier_packets.db"
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE packets (id INTEGER PRIMARY KEY AUTOINCREMENT, "
                   "received_at_utc TEXT NOT NULL, source TEXT NOT NULL, "
                   "sequence INTEGER NOT NULL, board_time_us INTEGER NOT NULL, "
                   "rssi_dbm INTEGER NOT NULL, invalid_first_word INTEGER NOT NULL, "
                   "queue_drops INTEGER NOT NULL, selected_iq BLOB NOT NULL)")
        db.execute("INSERT INTO packets (received_at_utc,source,sequence,board_time_us,"
                   "rssi_dbm,invalid_first_word,queue_drops,selected_iq) "
                   "VALUES (?,?,?,?,?,?,?,?)",
                   ("2026-10-20T00:00:00Z", "ESP32_BLUETOOTH", 1, 1000,
                    -50, 0, 0, bytes(100)))
    raw = bytes(range(128))
    line = f"WISDOM_CSI,2,2,2000,-48,0,0,{base64.b64encode(raw).decode()}"
    append_packets("ESP32_WIFI", [parse_line(line)], path)
    with sqlite3.connect(path) as db:
        rows = db.execute("SELECT sequence,length(selected_iq),length(raw_iq) "
                          "FROM packets ORDER BY id").fetchall()
    assert rows == [(1, 100, None), (2, 100, 128)]


def test_live_packet_uses_only_active_operator_label(tmp_path, monkeypatch):
    packet_path = tmp_path / "packets.db"
    room_store = RoomCaptureStore(tmp_path / "room.db")
    room_store.start("Lab", 5, 2)
    monkeypatch.setattr(csi_count_api, "room_store", room_store)
    monkeypatch.setattr(csi_count_api, "append_packets",
                        lambda source, parsed, capture=None: append_packets(
                            source, parsed, packet_path, capture=capture))
    monkeypatch.setattr(export_api, "PACKET_DB", packet_path)
    payload = base64.b64encode(bytes(range(128))).decode()
    line = f"WISDOM_CSI,2,9,90000,-42,0,0,{payload}"
    with TestClient(app) as client:
        assert client.post("/api/v1/csi-count/packets",
                           json={"source": "ESP32_BLUETOOTH", "lines": [line]}).status_code == 200
        rows = _rows(client.get("/api/v1/exports/csi-packets.csv"))
    assert rows[0]["label"] == "2"
    assert rows[0]["label_source"] == "OPERATOR"
    assert rows[0]["room"] == "Lab"
    assert rows[0]["full_128_iq_available"] == "True"


def test_room_export_keeps_operator_label_separate_from_model(tmp_path, monkeypatch):
    path = tmp_path / "room.db"
    monkeypatch.setattr(export_api, "ROOM_DB", path)
    store = RoomCaptureStore(path)
    at = datetime(2026, 10, 20, tzinfo=timezone.utc)
    session = store.start("Lab", 5, 1, at=at)["session_id"]
    window = np.full((100, 50), 2.5, dtype=np.float32)
    store.maybe_capture(window, 100, -42, {"predicted_count": 2, "model_score": 0.8},
                        at=at + timedelta(seconds=6), source="ESP32_WIFI")
    with TestClient(app) as client:
        rows = _rows(client.get(f"/api/v1/exports/room-windows.csv?session_id={session}"))
    assert len(rows) == 100
    assert rows[0]["operator_count"] == "1"
    assert rows[0]["model_prediction"] == "2"
    assert rows[0]["transport_source"] == "ESP32_WIFI"
    assert rows[0]["amplitude_pair_6"] == "2.5"


def test_sqlite_zip_exposes_readable_windows_and_keeps_raw_blob(tmp_path, monkeypatch):
    path = tmp_path / "room.db"
    monkeypatch.setattr(export_api, "_sqlite_sources", lambda: [("room_csi", path)])
    store = RoomCaptureStore(path)
    at = datetime(2026, 10, 20, tzinfo=timezone.utc)
    session = store.start("Lab", 5, 1, at=at)["session_id"]
    store.maybe_capture(np.full((100, 50), 2.5, dtype=np.float32), 100, -42,
                        {"predicted_count": None, "quality_reason": "OUTSIDE_RECORDED_SIGNAL_RANGE"},
                        at=at + timedelta(seconds=6), source="ESP32_WIFI")
    with TestClient(app) as client:
        response = client.get("/api/v1/exports/sqlite-tables.zip")
    assert response.status_code == 200
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        assert "Untransmitted PRoFENCH radio fields" in archive.read("README.txt").decode()
        summary = list(csv.DictReader(io.StringIO(archive.read("room_csi/windows.csv").decode("utf-8-sig"))))
        frames = list(csv.DictReader(io.StringIO(archive.read("room_csi/windows_frames.csv").decode("utf-8-sig"))))
        raw = list(csv.DictReader(io.StringIO(archive.read("room_csi/windows_raw_blob.csv").decode("utf-8-sig"))))
    assert len(summary) == len(raw) == 1 and len(frames) == 100
    assert "amplitudes_f32_zlib" not in summary[0]
    assert raw[0]["amplitudes_f32_zlib"]
    assert summary[0]["amplitude_pairs"] == "50"
    assert frames[0]["operator_count"] == "1"
    assert frames[0]["transport_source"] == "ESP32_WIFI"
    assert frames[0]["amplitude_pair_6"] == "2.5"


def test_nvs_sensor_and_database_exports_preserve_route_receipts(tmp_path, monkeypatch):
    path = tmp_path / "backend.db"
    monkeypatch.setattr(export_api, "_backend_path", lambda: path)
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE board_queue_status (status_id TEXT,device_id TEXT,route TEXT,laptop_stored_at TEXT,received_at TEXT,payload TEXT)")
        db.execute("CREATE TABLE delivery_receipts (id INTEGER,event_id TEXT,kind TEXT,reported_at TEXT,details TEXT)")
        db.execute("CREATE TABLE telemetry_events (event_id TEXT,device_id TEXT,received_at TEXT,observed_at TEXT,payload TEXT,fusion_state TEXT)")
        db.execute("INSERT INTO board_queue_status VALUES (?,?,?,?,?,?)",
                   ("st-1234567890abcdef", "tx-1", "WIFI", "2026-10-20T10:00:00Z", "2026-10-20T10:00:01Z",
                    json.dumps({"sequence": 1, "uptime_ms": 100, "queue_depth": 1,
                                "pending_event_ids": ["event-12345678"], "last_enqueued_id": "event-12345678",
                                "last_acked_id": "", "last_ack_route": "NONE"})))
        db.execute("INSERT INTO delivery_receipts VALUES (?,?,?,?,?)",
                   (1, "event-12345678", "LAPTOP_BT_SENSOR_STORED", "2026-10-20T10:00:02Z",
                    json.dumps({"reporter": "bt-sensor-receiver", "captured_at_utc": "2026-10-20T10:00:00Z"})))
        db.execute("INSERT INTO telemetry_events VALUES (?,?,?,?,?,?)",
                   ("event-12345678", "tx-1", "2026-10-20T10:00:03Z", "2026-10-20T10:00:00Z",
                    json.dumps({"environment": {"temperature_c": 24.5, "pressure_pa": 97382},
                                "firmware_version": "direct-wifi-bme680-mq135"}), "OK"))
    with TestClient(app) as client:
        queue = _rows(client.get("/api/v1/exports/nvs-queue.csv"))
        sensors = _rows(client.get("/api/v1/exports/wireless-sensors.csv"))
        response = client.get("/api/v1/exports/sqlite-tables.zip")
    assert queue[0]["pending_event_ids"] == '["event-12345678"]'
    assert queue[0]["evidence_type"] == "ESP32_WIRELESS_QUEUE_REPORT_AND_OPTIONAL_RECEIVER_COPY"
    assert queue[0]["event_id"] == "event-12345678"
    assert queue[0]["queue_event_state"] == "PENDING_ON_BOARD"
    assert sensors[0]["route"] == "BLUETOOTH"
    assert sensors[0]["receipt_reporter"] == "bt-sensor-receiver"
    assert sensors[0]["temperature_c"] == "24.5"
    assert sensors[0]["backend_stored_at_utc"] == "2026-10-20T10:00:03Z"
    assert response.status_code == 200
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        assert "safesense/telemetry_events.csv" in archive.namelist()
        assert "manifest.csv" in archive.namelist()
