"""Local, provenance-preserving CSV evidence exports."""

from __future__ import annotations

import base64
import csv
import io
import json
import sqlite3
import zlib
import zipfile
from contextlib import closing
from pathlib import Path
from typing import Iterable

import numpy as np
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import Response, StreamingResponse

from .config import DATA_DIR
from .csi_count_features import PAIR_POSITIONS
from .csi_packet_journal import PACKET_DB
from .database import engine

router = APIRouter(prefix="/api/v1/exports", tags=["CSV exports"])
ROOM_DB = DATA_DIR / "live" / "room_csi.db"
LOCAL_CLIENTS = {"127.0.0.1", "::1", "testclient"}


def _local(request: Request) -> None:
    if request.client is None or request.client.host not in LOCAL_CLIENTS:
        raise HTTPException(status_code=403, detail="Local dashboard access required")


def _db(path: Path):
    # StreamingResponse may resume a generator on a different worker thread.
    db = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True,
                         timeout=10, check_same_thread=False)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA busy_timeout=10000")
    return db


def _cell(value):
    if value is None:
        return ""
    if isinstance(value, bytes):
        return base64.b64encode(value).decode("ascii")
    if isinstance(value, (dict, list)):
        return json.dumps(value, separators=(",", ":"))
    # A local CSV may be opened in a spreadsheet. Keep untrusted text inert.
    if isinstance(value, str) and value[:1] in {"=", "+", "-", "@"}:
        return "'" + value
    return value


def _csv_chunks(headers: list[str], rows: Iterable[Iterable]):
    stream = io.StringIO(newline="")
    writer = csv.writer(stream)
    yield "\ufeff"
    writer.writerow(headers)
    yield stream.getvalue()
    stream.seek(0)
    stream.truncate(0)
    for row in rows:
        writer.writerow([_cell(value) for value in row])
        yield stream.getvalue()
        stream.seek(0)
        stream.truncate(0)


def _download(name: str, headers: list[str], rows: Iterable[Iterable]):
    return StreamingResponse(
        _csv_chunks(headers, rows), media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{name}"',
                 "Cache-Control": "no-store"},
    )


def _query(path: Path, sql: str, parameters: tuple = ()):
    if not path.is_file():
        return
    with closing(_db(path)) as db:
        cursor = db.execute(sql, parameters)
        while batch := cursor.fetchmany(250):
            yield from batch


@router.get("/room-windows.csv")
def room_windows_csv(request: Request, session_id: str | None = Query(default=None)):
    """One row per measured frame, with 50 amplitudes and separate operator label."""
    _local(request)
    if session_id is not None and (len(session_id) > 80 or not session_id.isascii()):
        raise HTTPException(status_code=422, detail="Invalid session ID")
    headers = ["session_id", "room", "window_id", "frame_index", "captured_at_utc",
               "end_sequence", "rssi_dbm", "operator_count", "label_source",
               "model_prediction", "model_score", "quality_reason", "transport_source",
               "source_format"] + [
                   f"amplitude_pair_{position}" for position in PAIR_POSITIONS]

    def rows():
        sql = ("SELECT s.room,w.* FROM windows w JOIN sessions s ON s.session_id=w.session_id "
               + ("WHERE w.session_id=? " if session_id else "") + "ORDER BY w.id")
        for row in _query(ROOM_DB, sql, (session_id,) if session_id else ()):
            values = np.frombuffer(zlib.decompress(row["amplitudes_f32_zlib"]),
                                   dtype="<f4").reshape(100, 50)
            for index, frame in enumerate(values):
                yield (row["session_id"], row["room"], row["id"], index,
                       row["captured_at_utc"], row["end_sequence"], row["rssi_dbm"],
                       row["label_count"] if row["label_source"] == "OPERATOR" else None,
                       row["label_source"], row["predicted_count"], row["model_score"],
                       row["quality_reason"], row["source"],
                       "SELECTED_50_PAIR_AMPLITUDES", *frame.tolist())

    return _download("safesense_room_csi_windows.csv", headers, rows())


@router.get("/nvs-queue.csv")
def nvs_queue_csv(request: Request):
    """Board queue observations with exact-ID receiver payloads when available."""
    _local(request)
    headers = ["status_id", "device_id", "board_sequence", "board_uptime_ms",
               "route", "laptop_stored_at_utc", "backend_stored_at_utc",
               "queue_depth", "pending_event_ids", "last_enqueued_id", "last_acked_id",
               "last_ack_route", "event_id", "queue_event_state", "payload_source",
               "receiver_payload_json", "evidence_type"]

    def rows():
        path = _backend_path()
        if path is None:
            return
        receiver_payloads = {}
        for source, receiver_path in (("WIFI_RECEIVER_SQLITE", DATA_DIR / "live" / "direct_laptop.db"),
                                      ("BLUETOOTH_RECEIVER_SQLITE", DATA_DIR / "live" / "direct_bt.db")):
            for event in _query(receiver_path, "SELECT event_id,payload FROM events"):
                receiver_payloads[event["event_id"]] = (source, event["payload"])
        for row in _query(path, "SELECT * FROM board_queue_status ORDER BY received_at,status_id"):
            payload = json.loads(row["payload"])
            pending = payload.get("pending_event_ids", [])
            events = [(event_id, "PENDING_ON_BOARD") for event_id in pending]
            acked = payload.get("last_acked_id")
            if acked and acked not in pending:
                events.append((acked, "LAST_ACKED_BY_BOARD"))
            if not events:
                events.append((None, "NO_EVENT_IN_REPORT"))
            for event_id, state in events:
                receiver_source, receiver_payload = receiver_payloads.get(event_id, (None, None))
                yield (row["status_id"], row["device_id"], payload.get("sequence"),
                       payload.get("uptime_ms"), row["route"], row["laptop_stored_at"],
                       row["received_at"], payload.get("queue_depth"), pending,
                       payload.get("last_enqueued_id"), acked, payload.get("last_ack_route"),
                       event_id, state, receiver_source, receiver_payload,
                       "ESP32_WIRELESS_QUEUE_REPORT_AND_OPTIONAL_RECEIVER_COPY")

    return _download("safesense_nvs_queue_observations.csv", headers, rows())


PACKET_HEADERS = ["sample_ID", "timestamp", "source", "session_id", "room", "label",
                  "label_source", "sequence", "board_time_us", "rssi_dbm",
                  "first_word_invalid", "queue_drops", "data", "raw_iq_count",
                  "selected_pair_positions", "selected_iq_data", "selected_pair_count",
                  "full_128_iq_available", "source_format"]


def _readable_packet_row(row: sqlite3.Row):
    iq = np.frombuffer(row["selected_iq"], dtype=np.int8).tolist()
    columns = row.keys()
    raw = row["raw_iq"] if "raw_iq" in columns else None
    full = raw is not None and len(raw) == 128
    label_source = row["label_source"] if "label_source" in columns else None
    label = row["operator_count"] if label_source == "OPERATOR" else None
    return (row["id"], row["received_at_utc"], row["source"],
            row["session_id"] if "session_id" in columns else None,
            row["room"] if "room" in columns else None,
            label, label_source, row["sequence"], row["board_time_us"],
            row["rssi_dbm"], row["invalid_first_word"], row["queue_drops"],
            np.frombuffer(raw, dtype=np.int8).tolist() if full else None,
            len(raw) if raw is not None else None,
            PAIR_POSITIONS.tolist(), iq, 50, full,
            "FULL_128_RAW_IQ" if full else "SELECTED_50_IQ_ONLY")


@router.get("/csi-packets.csv")
def csi_packets_csv(request: Request):
    """One received CSI packet per row, with full I/Q only when transmitted."""
    _local(request)

    def rows():
        for row in _query(PACKET_DB, "SELECT * FROM packets ORDER BY id"):
            yield _readable_packet_row(row)

    return _download("safesense_csi_packets.csv", PACKET_HEADERS, rows())


@router.get("/wireless-sensors.csv")
def wireless_sensors_csv(request: Request):
    """A row per Wi-Fi/Bluetooth receipt, joined to the exact backend event ID."""
    _local(request)
    headers = ["event_id", "device_id", "route", "receipt_kind", "receipt_reporter",
               "receiver_stored_at_utc", "backend_stored_at_utc", "sensor_observed_at_utc",
               "capture_age_ms", "temperature_c", "humidity_pct", "pressure_pa",
               "bme680_gas_resistance_ohm", "bme680_gas_valid", "bme680_heat_stable",
               "mq135_adc_raw", "gas_risk", "sensor_healthy", "simulated",
               "backend_fusion_state"]

    def rows():
        path = _backend_path()
        if path is None:
            return
        sql = ("SELECT d.event_id,d.kind,d.reported_at,d.details,t.device_id,"
               "t.received_at,t.observed_at,t.payload,t.fusion_state "
               "FROM delivery_receipts d LEFT JOIN telemetry_events t ON t.event_id=d.event_id "
               "WHERE d.kind IN ('LAPTOP_WIFI_STORED','LAPTOP_BT_SENSOR_STORED') "
               "ORDER BY d.reported_at,d.id")
        for row in _query(path, sql):
            details = json.loads(row["details"] or "{}")
            payload = json.loads(row["payload"] or "{}")
            env = payload.get("environment") or {}
            route = "WIFI" if row["kind"] == "LAPTOP_WIFI_STORED" else "BLUETOOTH"
            yield (row["event_id"], row["device_id"], route, row["kind"],
                   details.get("reporter") or details.get("source"), row["reported_at"],
                   row["received_at"], details.get("captured_at_utc") or row["observed_at"],
                   details.get("capture_age_ms"), env.get("temperature_c"),
                   env.get("humidity_pct"), env.get("pressure_pa"),
                   env.get("gas_resistance_ohm"), env.get("gas_valid"),
                   env.get("heat_stable"), env.get("gas_adc_raw"), env.get("gas_risk"),
                   env.get("sensor_healthy"),
                   payload.get("firmware_version") == "synthetic-forecast-demo" if payload else None,
                   row["fusion_state"])

    return _download("safesense_wireless_sensor_deliveries.csv", headers, rows())


def _backend_path() -> Path | None:
    if engine.url.get_backend_name() != "sqlite" or not engine.url.database:
        return None
    return Path(engine.url.database)


def _sqlite_sources():
    backend = _backend_path()
    return [("safesense", backend), ("room_csi", ROOM_DB),
            ("csi_packets", PACKET_DB),
            ("direct_laptop", DATA_DIR / "live" / "direct_laptop.db"),
            ("direct_bt", DATA_DIR / "live" / "direct_bt.db"),
            ("direct_usb", DATA_DIR / "live" / "direct_usb.db"),
            ("sos_voice", DATA_DIR / "live" / "sos_voice.db")]


def _write_zip_rows(archive: zipfile.ZipFile, filename: str, headers, rows) -> None:
    with archive.open(filename, "w") as raw:
        with io.TextIOWrapper(raw, encoding="utf-8-sig", newline="") as output:
            writer = csv.writer(output)
            writer.writerow(headers)
            for row in rows:
                writer.writerow([_cell(value) for value in row])


def _write_readable_room_windows(archive: zipfile.ZipFile, db: sqlite3.Connection) -> None:
    """Expose measured amplitudes without presenting a BLOB as CSV sensor data."""
    columns = [row[1] for row in db.execute("PRAGMA table_info(windows)")]
    visible = [column for column in columns if column != "amplitudes_f32_zlib"]
    pair_headers = [f"amplitude_pair_{position}" for position in PAIR_POSITIONS]
    def measured_windows():
        for row in db.execute("SELECT w.*,s.room FROM windows w "
                              "JOIN sessions s ON s.session_id=w.session_id ORDER BY w.id"):
            values = np.frombuffer(zlib.decompress(row["amplitudes_f32_zlib"]),
                                   dtype="<f4").reshape(100, 50)
            yield row, values

    def summaries():
        for row, values in measured_windows():
            yield [row[column] for column in visible] + [
                100, 50, float(values.min()), float(values.mean()),
                float(values.max()), "room_csi/windows_frames.csv"]

    def frames():
        for row, values in measured_windows():
            for frame_index, frame in enumerate(values):
                yield (row["id"], row["session_id"], row["room"], frame_index,
                       row["captured_at_utc"], row["end_sequence"], row["rssi_dbm"],
                       row["label_count"] if row["label_source"] == "OPERATOR" else None,
                       row["label_source"], row["predicted_count"], row["model_score"],
                       row["quality_reason"], row["source"],
                       "SELECTED_50_PAIR_AMPLITUDES", *frame.tolist())
    _write_zip_rows(archive, "room_csi/windows.csv",
                    visible + ["window_frames", "amplitude_pairs", "amplitude_min",
                               "amplitude_mean", "amplitude_max", "amplitudes_location"],
                    summaries())
    _write_zip_rows(archive, "room_csi/windows_frames.csv",
                    ["window_id", "session_id", "room", "frame_index", "captured_at_utc",
                     "end_sequence", "rssi_dbm", "operator_count", "label_source",
                     "model_prediction", "model_score", "quality_reason", "transport_source",
                     "source_format"] + pair_headers, frames())
    _write_zip_rows(archive, "room_csi/windows_raw_blob.csv", columns,
                    ([row[column] for column in columns]
                     for row in db.execute("SELECT * FROM windows ORDER BY id")))


@router.get("/sqlite-tables.zip")
def sqlite_tables_zip(request: Request):
    """Every application table from the known local SQLite stores as a CSV file."""
    _local(request)
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED,
                         compresslevel=6) as archive:
        archive.writestr("README.txt", """SafeSense SQLite CSV export

room_csi/windows.csv: one readable summary per saved 100 x 50 amplitude window.
room_csi/windows_frames.csv: 100 frame rows per window, with 50 amplitude columns.
room_csi/windows_raw_blob.csv: exact SQLite BLOB values in base64 for backup.
csi_packets/packets.csv: one received packet per row. 'data' has 128 signed
I/Q values only when full_128_iq_available is True; earlier packets have only
selected_iq_data (100 values, 50 pairs). packets_raw_blob.csv is the backup.
Labels appear only when an operator supplied a room count during collection.
Blank labels and source fields in historical rows are unknown, not zero.
Packet timestamps are laptop receipt times; board_time_us is board monotonic
time. Untransmitted PRoFENCH radio fields cannot be reconstructed.
""")
        manifest = io.StringIO(newline="")
        manifest_writer = csv.writer(manifest)
        manifest_writer.writerow(["database", "table", "csv_file", "status"])
        for name, path in _sqlite_sources():
            if path is None or not path.is_file():
                manifest_writer.writerow([name, "", "", "NOT_AVAILABLE"])
                continue
            with closing(_db(path)) as db:
                tables = [row[0] for row in db.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
                for table in tables:
                    filename = f"{name}/{table}.csv"
                    if name == "room_csi" and table == "windows":
                        _write_readable_room_windows(archive, db)
                        manifest_writer.writerow([name, table, filename, "READABLE_WINDOW_SUMMARY"])
                        manifest_writer.writerow([name, "windows frames", "room_csi/windows_frames.csv",
                                                  "DECODED_SELECTED_AMPLITUDES"])
                        manifest_writer.writerow([name, "windows raw blob", "room_csi/windows_raw_blob.csv",
                                                  "EXACT_SQLITE_BLOB_BACKUP"])
                        continue
                    if name == "csi_packets" and table == "packets":
                        _write_zip_rows(archive, filename, PACKET_HEADERS,
                                        (_readable_packet_row(row) for row in db.execute(
                                            "SELECT * FROM packets ORDER BY id")))
                        manifest_writer.writerow([name, table, filename, "READABLE_PACKET_VIEW"])
                        cursor = db.execute("SELECT * FROM packets ORDER BY id")
                        _write_zip_rows(archive, "csi_packets/packets_raw_blob.csv",
                                        [field[0] for field in cursor.description], cursor)
                        manifest_writer.writerow([name, "packets raw blob", "csi_packets/packets_raw_blob.csv",
                                                  "EXACT_SQLITE_BLOB_BACKUP"])
                        continue
                    escaped = table.replace('"', '""')
                    cursor = db.execute(f'SELECT * FROM "{escaped}"')
                    _write_zip_rows(archive, filename, [field[0] for field in cursor.description], cursor)
                    manifest_writer.writerow([name, table, filename, "EXPORTED"])
        archive.writestr("manifest.csv", "\ufeff" + manifest.getvalue())
    return Response(stream.getvalue(), media_type="application/zip",
                    headers={"Content-Disposition": 'attachment; filename="safesense_sqlite_csv_tables.zip"',
                             "Cache-Control": "no-store"})
