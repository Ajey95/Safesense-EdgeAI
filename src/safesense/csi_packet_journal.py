"""Durable copy of CSI packets accepted by the local count API."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .config import DATA_DIR

PACKET_DB = DATA_DIR / "live" / "csi_packets.db"


def append_packets(source: str, parsed: list[tuple], path: Path | None = None,
                   capture: dict | None = None) -> None:
    """Commit raw I/Q and operator provenance before acknowledging a packet batch."""
    target = path or PACKET_DB
    target.parent.mkdir(parents=True, exist_ok=True)
    received_at = datetime.now(timezone.utc).isoformat()
    with sqlite3.connect(target, timeout=10) as db:
        db.execute("PRAGMA busy_timeout=10000")
        db.execute("""CREATE TABLE IF NOT EXISTS packets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            received_at_utc TEXT NOT NULL, source TEXT NOT NULL,
            sequence INTEGER NOT NULL, board_time_us INTEGER NOT NULL,
            rssi_dbm INTEGER NOT NULL, invalid_first_word INTEGER NOT NULL,
            queue_drops INTEGER NOT NULL, selected_iq BLOB NOT NULL,
            raw_iq BLOB, session_id TEXT, room TEXT,
            operator_count INTEGER, label_source TEXT
        )""")
        existing = {row[1] for row in db.execute("PRAGMA table_info(packets)")}
        for column, kind in (("raw_iq", "BLOB"), ("session_id", "TEXT"),
                             ("room", "TEXT"), ("operator_count", "INTEGER"),
                             ("label_source", "TEXT")):
            if column not in existing:
                db.execute(f"ALTER TABLE packets ADD COLUMN {column} {kind}")
        active = capture if capture and capture.get("active") else None
        label = (active.get("label_count") if active and
                 active.get("label_source") == "OPERATOR" else None)
        db.executemany(
            "INSERT INTO packets (received_at_utc,source,sequence,board_time_us,"
            "rssi_dbm,invalid_first_word,queue_drops,selected_iq,raw_iq,"
            "session_id,room,operator_count,label_source) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [(received_at, source, sequence, board_time_us, rssi, invalid, drops,
              iq_pairs.astype("int8", copy=False).tobytes(), raw_iq,
              active.get("session_id") if active else None,
              active.get("room") if active else None, label,
              active.get("label_source") if active else None)
             for sequence, board_time_us, rssi, drops, invalid, iq_pairs, raw_iq, _ in parsed],
        )
