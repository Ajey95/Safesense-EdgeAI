"""Small atomic control files shared by the dashboard and Bluetooth listener."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
REQUEST = ROOT / "data/live/bt_reconnect_request.json"
FRAME = ROOT / "data/live/bt_latest_frame.json"


def read_record(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def write_record(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.{os.getpid()}.{uuid4().hex}.tmp")
    try:
        temporary.write_text(json.dumps(record), encoding="utf-8")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def request_reconnect() -> dict:
    record = {"request_id": uuid4().hex,
              "requested_at_utc": datetime.now(timezone.utc).isoformat()}
    write_record(REQUEST, record)
    return record


def record_frame(event_id: str) -> None:
    write_record(FRAME, {"event_id": event_id,
                         "received_at_utc": datetime.now(timezone.utc).isoformat()})
