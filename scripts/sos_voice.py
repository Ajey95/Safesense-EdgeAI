"""Opt-in Telegram voice messages for real laptop-received forecast alerts.

Telegram acceptance proves posting to a chat, not that a contact listened.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import secrets
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from uuid import uuid4
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

if __package__:
    from scripts.sos_token_store import load_token
else:
    from sos_token_store import load_token


EVENT_ID = re.compile(r"^[A-Za-z0-9_.:-]{8,100}$")
BOT_TOKEN = re.compile(r"^[0-9]+:[A-Za-z0-9_-]{20,}$")
CHAT_ID = re.compile(r"^-?[0-9]{4,20}$")
CONTACT_FILE = Path("data/live/sos_voice_contacts.json")


@dataclass(frozen=True)
class VoiceConfig:
    bot_token: str
    chat_ids: tuple[str, ...]

    @classmethod
    def from_environment(cls) -> "VoiceConfig":
        token = load_token()
        raw_chats = os.getenv("SAFESENSE_SOS_CHAT_IDS", "")
        if raw_chats:
            chats = tuple(dict.fromkeys(x.strip() for x in raw_chats.split(",") if x.strip()))
        elif CONTACT_FILE.exists():
            saved = json.loads(CONTACT_FILE.read_text(encoding="utf-8"))
            chats = tuple(dict.fromkeys(saved["chat_ids"]))
        else:
            chats = ()
        if not (BOT_TOKEN.fullmatch(token) and 1 <= len(chats) <= 5
                and all(CHAT_ID.fullmatch(chat) for chat in chats)):
            raise ValueError("SOS voice needs a Telegram bot token and 1-5 numeric contact chat IDs")
        if sys.platform != "win32" or shutil.which("ffmpeg") is None:
            raise ValueError("SOS voice needs Windows System.Speech and ffmpeg")
        return cls(token, chats)


def _message(alert: dict) -> str:
    if alert.get("test_only") is True:
        return ("SafeSense voice delivery test. No incident has occurred. "
                f"Test event {alert['event_id']}.")
    channel = str(alert["channel"])
    action = alert.get("response") or {
        "cold storage": "Check refrigeration, door seals, and the condition of stored goods.",
        "laboratory": "Check local ventilation and follow the laboratory safety procedure.",
        "classroom": "Check ventilation and move people if conditions are uncomfortable.",
        "bakery": "Check the heat source, ventilation, and worker conditions.",
        "server room": "Inspect cooling and airflow before equipment temperatures rise.",
    }.get(str(alert["room"]).lower(), "Check the area and follow your site procedure.")
    direction = alert.get("direction")
    movement = f"may move {direction} the configured range" if direction in {"above", "below"} else "may cross the configured range"
    return (f"SafeSense early forecast for {alert['room']}. "
            f"{channel} {movement} in about {alert['horizon_minutes']} minutes. "
            "Please verify the current sensor reading and inspect the area. "
            f"{action} Event {alert['event_id']}.")


def _render_voice_mp3(alert: dict) -> bytes:
    with tempfile.TemporaryDirectory(prefix="safesense-voice-") as temp:
        wav = Path(temp) / "alert.wav"
        mp3 = Path(temp) / "alert.mp3"
        env = os.environ.copy()
        env.pop("SAFESENSE_TELEGRAM_BOT_TOKEN", None)
        env.pop("SAFESENSE_SOS_CHAT_IDS", None)
        env["SAFESENSE_ALERT_TEXT"] = _message(alert)
        env["SAFESENSE_ALERT_WAV"] = str(wav)
        command = ("Add-Type -AssemblyName System.Speech; "
                   "$voice = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
                   "$voice.SetOutputToWaveFile($env:SAFESENSE_ALERT_WAV); "
                   "$voice.Speak($env:SAFESENSE_ALERT_TEXT); $voice.Dispose()")
        subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
                       env=env, check=True, capture_output=True, timeout=30,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                        "-i", str(wav), "-codec:a", "libmp3lame", "-b:a", "64k", str(mp3)],
                       env=env, check=True, capture_output=True, timeout=30,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return mp3.read_bytes()


def _send_voice(config: VoiceConfig, chat: str, audio: bytes, alert: dict) -> int:
    boundary = "safesense" + secrets.token_hex(12)
    body = bytearray()
    caption = ("SafeSense forecast scenario" if alert.get("scenario_voice") else "SafeSense early alert")
    for name, value in {"chat_id": chat, "caption": f"{caption}: {alert['event_id']}"}.items():
        body.extend(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n{value}\r\n".encode())
    body.extend(f"--{boundary}\r\nContent-Disposition: form-data; name=\"voice\"; filename=\"alert.mp3\"\r\nContent-Type: audio/mpeg\r\n\r\n".encode())
    body.extend(audio)
    body.extend(f"\r\n--{boundary}--\r\n".encode())
    request = Request(f"https://api.telegram.org/bot{config.bot_token}/sendVoice",
                      data=bytes(body),
                      headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
                      method="POST")
    with urlopen(request, timeout=15) as response:
        result = json.load(response)
    mid = (result.get("result") or {}).get("message_id")
    if result.get("ok") is not True or not isinstance(mid, int):
        raise ValueError("Telegram did not accept the voice message")
    return mid


def _database(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=10)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA synchronous=FULL")
    db.execute("""CREATE TABLE IF NOT EXISTS voice_messages (
        event_id TEXT NOT NULL, chat_hash TEXT NOT NULL, chat_last4 TEXT NOT NULL,
        state TEXT NOT NULL, message_id INTEGER, updated_at_utc TEXT NOT NULL,
        PRIMARY KEY (event_id, chat_hash))""")
    db.commit()
    return db


def _internet_reachable() -> bool:
    try:
        with urlopen(Request("https://api.telegram.org", method="GET"), timeout=3):
            return True
    except HTTPError:
        return True
    except (URLError, TimeoutError, OSError):
        return False


def dispatch(alert: dict, database: Path, config: VoiceConfig | None = None) -> dict:
    """Reserve event/chat pairs before send; ambiguous outcomes need manual review."""
    if alert.get("simulated") is not False:
        return {"state": "SKIPPED_UNVERIFIED_ORIGIN", "messages_sent": 0}
    return _dispatch_voice(alert, database, config)


def dispatch_scenario_voice(alert: dict, database: Path, config: VoiceConfig | None = None) -> dict:
    """Send an explicitly sourced forecast scenario to configured demo contacts."""
    if alert.get("simulated") is not True or alert.get("scenario_voice") is not True:
        raise ValueError("scenario voice requires synthetic scenario provenance")
    return _dispatch_voice(alert, database, config)


def _dispatch_voice(alert: dict, database: Path, config: VoiceConfig | None = None) -> dict:
    if not EVENT_ID.fullmatch(str(alert.get("event_id", ""))):
        raise ValueError("invalid SOS event ID")
    if not isinstance(alert.get("horizon_minutes"), int) or not 5 <= alert["horizon_minutes"] <= 30:
        raise ValueError("invalid SOS alert horizon")
    config = config or VoiceConfig.from_environment()
    if not _internet_reachable():
        return {"state": "DEFERRED_OFFLINE", "messages_sent": 0}
    with closing(_database(database)) as db:
        reserved = []
        for chat in config.chat_ids:
            digest = hashlib.sha256(chat.encode()).hexdigest()
            try:
                db.execute("INSERT INTO voice_messages VALUES (?,?,?,?,?,?)",
                           (alert["event_id"], digest, chat[-4:], "PREPARING", None,
                            datetime.now(timezone.utc).isoformat()))
                db.commit()
                reserved.append((chat, digest))
            except sqlite3.IntegrityError:
                continue
        if not reserved:
            return {"state": "DUPLICATE", "messages_sent": 0}
        try:
            audio = _render_voice_mp3(alert)
        except (OSError, subprocess.SubprocessError, ValueError):
            for _, digest in reserved:
                db.execute("UPDATE voice_messages SET state=?, updated_at_utc=? WHERE event_id=? AND chat_hash=?",
                           ("AUDIO_FAILED", datetime.now(timezone.utc).isoformat(), alert["event_id"], digest))
            db.commit()
            return {"state": "AUDIO_FAILED", "messages_sent": 0}
        sent = 0
        for chat, digest in reserved:
            db.execute("UPDATE voice_messages SET state=?, updated_at_utc=? WHERE event_id=? AND chat_hash=?",
                       ("SUBMITTING", datetime.now(timezone.utc).isoformat(), alert["event_id"], digest))
            db.commit()
            try:
                mid = _send_voice(config, chat, audio, alert)
            except (HTTPError, URLError, TimeoutError, OSError, ValueError):
                state, mid = "OUTCOME_UNKNOWN", None
            else:
                state = "ACCEPTED_BY_TELEGRAM"
                sent += 1
            db.execute("UPDATE voice_messages SET state=?, message_id=?, updated_at_utc=? WHERE event_id=? AND chat_hash=?",
                       (state, mid, datetime.now(timezone.utc).isoformat(), alert["event_id"], digest))
            db.commit()
    return {"state": "PROCESSED", "messages_sent": sent}


def status(database: Path, event_id: str) -> list[dict]:
    if not database.exists():
        return []
    with closing(_database(database)) as db:
        rows = db.execute("SELECT chat_last4,state,message_id,updated_at_utc FROM voice_messages WHERE event_id=?",
                          (event_id,)).fetchall()
    return [{"chat_last4": last4, "state": state, "message_id": mid, "updated_at_utc": when}
            for last4, state, mid, when in rows]


def list_contact_chats() -> list[dict]:
    token = load_token()
    request = Request(f"https://api.telegram.org/bot{token}/getUpdates", method="POST")
    with urlopen(request, timeout=10) as response:
        payload = json.load(response)
    if payload.get("ok") is not True:
        raise ValueError("Telegram could not list bot updates")
    chats = {}
    for update in payload.get("result", []):
        message = update.get("message") or {}
        chat = message.get("chat") or {}
        if isinstance(chat.get("id"), int) and chat.get("type") == "private":
            chats[str(chat["id"])] = {"chat_id": str(chat["id"]), "type": "private"}
    return list(chats.values())


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect SafeSense SOS Telegram setup and delivery state")
    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument("--list-chats", action="store_true", help="List private chats that messaged the bot")
    actions.add_argument("--status", metavar="EVENT_ID", help="Read stored voice delivery status")
    actions.add_argument("--send-test", action="store_true",
                         help="Send an explicitly labelled test voice message to configured contacts")
    parser.add_argument("--database", type=Path, default=Path("data/live/sos_voice.db"))
    args = parser.parse_args()
    try:
        if args.list_chats:
            result = list_contact_chats()
        elif args.send_test:
            test_id = f"test-{uuid4()}"
            result = {"event_id": test_id, **dispatch({"event_id": test_id, "room": "test",
                       "channel": "test", "horizon_minutes": 5, "simulated": False,
                       "test_only": True}, args.database)}
        else:
            result = status(args.database, args.status)
    except (HTTPError, URLError, TimeoutError, OSError, ValueError) as error:
        raise SystemExit(f"SOS voice inspection failed: {type(error).__name__}") from None
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
