"""Small durable history of laptop Wi-Fi and Bluetooth handoff transitions."""

from __future__ import annotations

import json
import os
from collections import deque
from datetime import datetime, timezone
from pathlib import Path


HISTORY = Path(__file__).resolve().parents[1] / "data/live/transport_events.jsonl"


def append_event(state: str, **details: object) -> None:
    HISTORY.parent.mkdir(parents=True, exist_ok=True)
    record = {"state": state, "at_utc": datetime.now(timezone.utc).isoformat(), **details}
    payload = (json.dumps(record, separators=(",", ":")) + "\n").encode("utf-8")
    descriptor = os.open(HISTORY, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    try:
        os.write(descriptor, payload)
    finally:
        os.close(descriptor)


def recent_events(limit: int = 20) -> list[dict]:
    try:
        with HISTORY.open(encoding="utf-8") as handle:
            lines = deque(handle, maxlen=max(1, min(limit, 100)))
    except OSError:
        return []
    events = []
    for line in reversed(lines):
        try:
            value = json.loads(line)
        except ValueError:
            continue
        if isinstance(value, dict) and isinstance(value.get("state"), str):
            events.append(value)
    return events
