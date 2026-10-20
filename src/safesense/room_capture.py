"""Durable, operator-labelled CSI windows for room commissioning."""

from __future__ import annotations

import sqlite3
import threading
import uuid
import zlib
import json
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

from .config import DATA_DIR


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class RoomCaptureStore:
    def __init__(self, path: Path = DATA_DIR / "live" / "room_csi.db"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        with self._connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY, room TEXT NOT NULL,
                    interval_seconds INTEGER NOT NULL, label_count INTEGER,
                    label_source TEXT NOT NULL, started_at_utc TEXT NOT NULL,
                    ended_at_utc TEXT, next_due_at_utc TEXT NOT NULL,
                    last_capture_at_utc TEXT, last_sequence INTEGER
                );
                CREATE TABLE IF NOT EXISTS windows (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL REFERENCES sessions(session_id),
                    captured_at_utc TEXT NOT NULL, end_sequence INTEGER NOT NULL,
                    rssi_dbm INTEGER, label_count INTEGER, label_source TEXT NOT NULL,
                    predicted_count INTEGER, model_score REAL, quality_reason TEXT,
                    amplitudes_f32_zlib BLOB NOT NULL,
                    source TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_room_windows_session
                    ON windows(session_id, id);
            """)
            if "source" not in {row[1] for row in db.execute("PRAGMA table_info(windows)")}:
                db.execute("ALTER TABLE windows ADD COLUMN source TEXT")

    @contextmanager
    def _connect(self):
        db = sqlite3.connect(self.path, timeout=5)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    @staticmethod
    def _active(db: sqlite3.Connection) -> sqlite3.Row | None:
        return db.execute("SELECT * FROM sessions WHERE ended_at_utc IS NULL "
                          "ORDER BY started_at_utc DESC LIMIT 1").fetchone()

    def status(self) -> dict:
        with self.lock, self._connect() as db:
            row = self._active(db) or db.execute(
                "SELECT * FROM sessions ORDER BY started_at_utc DESC LIMIT 1").fetchone()
            if row is None:
                return {"active": False, "session_id": None, "room": None,
                        "label_count": None, "label_source": "UNLABELLED",
                        "saved_windows": 0, "label_counts": {"0": 0, "1": 0, "2": 0, "unlabelled": 0},
                        "interval_seconds": None,
                        "next_due_at_utc": None, "last_capture_at_utc": None}
            count = db.execute("SELECT COUNT(*) FROM windows WHERE session_id=?",
                               (row["session_id"],)).fetchone()[0]
            label_counts = {"0": 0, "1": 0, "2": 0, "unlabelled": 0}
            for count_row in db.execute("SELECT label_count, label_source, COUNT(*) AS n "
                                        "FROM windows WHERE session_id=? GROUP BY label_count, label_source",
                                        (row["session_id"],)):
                key = str(count_row["label_count"]) if count_row["label_source"] == "OPERATOR" else "unlabelled"
                label_counts[key] += count_row["n"]
            return {"active": row["ended_at_utc"] is None,
                    "session_id": row["session_id"], "room": row["room"],
                    "label_count": row["label_count"],
                    "label_source": row["label_source"],
                    "saved_windows": count, "label_counts": label_counts,
                    "interval_seconds": row["interval_seconds"],
                    "started_at_utc": row["started_at_utc"],
                    "ended_at_utc": row["ended_at_utc"],
                    "next_due_at_utc": row["next_due_at_utc"] if row["ended_at_utc"] is None else None,
                    "last_capture_at_utc": row["last_capture_at_utc"]}

    def start(self, room: str, interval_seconds: int = 10,
              label_count: int | None = None, at: datetime | None = None) -> dict:
        if not room.strip() or len(room) > 80 or not 5 <= interval_seconds <= 60:
            raise ValueError("room or capture interval outside range")
        if label_count is not None and (type(label_count) is not int or not 0 <= label_count <= 2):
            raise ValueError("operator count must be 0, 1, 2, or unlabelled")
        at = at or utc_now()
        with self.lock, self._connect() as db:
            if self._active(db):
                raise ValueError("a room capture is already active")
            db.execute("INSERT INTO sessions VALUES (?,?,?,?,?,?,?,?,?,?)",
                       (str(uuid.uuid4()), room.strip(), interval_seconds, label_count,
                        "OPERATOR" if label_count is not None else "UNLABELLED",
                        at.isoformat(), None,
                        (at + timedelta(seconds=interval_seconds)).isoformat(), None, None))
        return self.status()

    def set_label(self, label_count: int | None,
                  at: datetime | None = None) -> dict:
        if label_count is not None and (type(label_count) is not int or not 0 <= label_count <= 2):
            raise ValueError("operator count must be 0, 1, 2, or unlabelled")
        at = at or utc_now()
        with self.lock, self._connect() as db:
            row = self._active(db)
            if row is None:
                raise ValueError("no active room capture")
            db.execute("UPDATE sessions SET label_count=?, label_source=?, "
                       "next_due_at_utc=? WHERE session_id=?",
                       (label_count, "OPERATOR" if label_count is not None else "UNLABELLED",
                        (at + timedelta(seconds=row["interval_seconds"])).isoformat(),
                        row["session_id"]))
        return self.status()

    def stop(self, at: datetime | None = None) -> dict:
        at = at or utc_now()
        with self.lock, self._connect() as db:
            row = self._active(db)
            if row is None:
                raise ValueError("no active room capture")
            db.execute("UPDATE sessions SET ended_at_utc=? WHERE session_id=?",
                       (at.isoformat(), row["session_id"]))
        return self.status()

    def maybe_capture(self, window: np.ndarray, end_sequence: int,
                      rssi_dbm: int | None, prediction: dict,
                      at: datetime | None = None, source: str | None = None) -> dict | None:
        if window.shape != (100, 50) or not np.isfinite(window).all():
            raise ValueError("capture requires a finite 100-by-50 CSI window")
        at = at or utc_now()
        with self.lock, self._connect() as db:
            row = self._active(db)
            if (row is None or at.isoformat() < row["next_due_at_utc"]
                    or (row["last_sequence"] is not None and end_sequence <= row["last_sequence"])):
                return None
            values = np.asarray(window, dtype="<f4", order="C")
            db.execute("INSERT INTO windows (session_id,captured_at_utc,end_sequence,"
                       "rssi_dbm,label_count,label_source,predicted_count,model_score,"
                       "quality_reason,amplitudes_f32_zlib,source) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                       (row["session_id"], at.isoformat(), end_sequence, rssi_dbm,
                        row["label_count"], row["label_source"],
                        prediction.get("predicted_count"), prediction.get("model_score"),
                        prediction.get("quality_reason"), zlib.compress(values.tobytes()), source))
            db.execute("UPDATE sessions SET next_due_at_utc=?, last_capture_at_utc=?, "
                       "last_sequence=? WHERE session_id=?",
                       ((at + timedelta(seconds=row["interval_seconds"])).isoformat(),
                        at.isoformat(), end_sequence, row["session_id"]))
            return {"session_id": row["session_id"], "captured_at_utc": at.isoformat(),
                    "end_sequence": end_sequence, "label_count": row["label_count"],
                    "label_source": row["label_source"],
                    "predicted_count": prediction.get("predicted_count")}

    def windows(self, session_id: str) -> list[dict]:
        with self.lock, self._connect() as db:
            rows = db.execute("SELECT * FROM windows WHERE session_id=? ORDER BY id",
                              (session_id,)).fetchall()
            return [{**dict(row), "window": np.frombuffer(
                zlib.decompress(row["amplitudes_f32_zlib"]), dtype="<f4").reshape(100, 50).copy()}
                    for row in rows]

    def export(self, session_id: str, path: Path) -> dict:
        """Write model-ready arrays with separate verified labels and predictions."""
        with self.lock, self._connect() as db:
            session = db.execute("SELECT * FROM sessions WHERE session_id=?", (session_id,)).fetchone()
            if session is None:
                raise ValueError("unknown room capture session")
        rows = self.windows(session_id)
        features = np.stack([row["window"] for row in rows]).astype("<f4") if rows else np.empty((0, 100, 50), dtype="<f4")
        labels = np.asarray([row["label_count"] if row["label_source"] == "OPERATOR" else -1
                             for row in rows], dtype=np.int8)
        predictions = np.asarray([row["predicted_count"] if row["predicted_count"] is not None else -1
                                  for row in rows], dtype=np.int8)
        metadata = [{key: row[key] for key in ("captured_at_utc", "end_sequence", "rssi_dbm",
                     "label_source", "quality_reason", "source")} for row in rows]
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(path, amplitudes=features, operator_labels=labels,
                            model_predictions=predictions,
                            session_json=json.dumps(dict(session)),
                            windows_json=json.dumps(metadata))
        return {"path": str(path), "session_id": session_id, "windows": len(rows),
                "verified_labels": int(np.count_nonzero(labels >= 0)),
                "unlabelled": int(np.count_nonzero(labels < 0))}
