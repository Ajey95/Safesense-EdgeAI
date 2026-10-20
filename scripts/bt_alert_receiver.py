"""Receive a paired classic-ESP32 SPP alert on a Windows Bluetooth COM port.

Receipt is sent only after the event is durably appended to a local journal.
Speech is a separate best-effort local action. This does not call SOS services.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from scripts.direct_laptop_receiver import Receiver
from scripts.transport_handoff import REQUEST, read_record, record_frame
from scripts.wireless_csi_receiver import WirelessCsiForwarder
from scripts.wifi_demo_session import RESTORE, current_ssid


ROOMS = ("cold storage", "laboratory", "classroom", "bakery", "server room")
CHANNELS = ("temperature", "humidity", "pressure", "BME680 gas response", "MQ-135 raw response")
EVENT_ID = re.compile(r"^[A-Za-z0-9_-]{8,63}$")
IDLE_RECONNECT_SECONDS = 30
LOCK = Path("data/live/bt_alert_receiver.lock")


def acquire_receiver_lock():
    """Keep a button-triggered replacement from competing for the same COM port."""
    LOCK.parent.mkdir(parents=True, exist_ok=True)
    handle = LOCK.open("a+b")
    try:
        if sys.platform == "win32":
            import msvcrt
            if LOCK.stat().st_size == 0:
                handle.write(b"\0")
                handle.flush()
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except (OSError, IOError):
        handle.close()
        return None
    return handle


def idle_reconnect_due(last_frame_at: float, now: float, ssid: str | None) -> bool:
    return ssid == RESTORE and now - last_frame_at >= IDLE_RECONNECT_SECONDS


def network_for_idle_check() -> str | None:
    try:
        return current_ssid()
    except (OSError, subprocess.TimeoutExpired):
        # A stuck netsh call must not terminate the SPP listener.
        return RESTORE


def parse_alert(line: bytes) -> dict:
    try:
        text = line.decode("ascii").rstrip("\r\n")
        parts = text.split("|")
        if len(parts) == 5:
            verb, event_id, room, minutes, channel = parts
            mode = "U"  # Older frames did not identify synthetic replay.
        elif len(parts) == 6:
            verb, event_id, room, minutes, channel, mode = parts
        else:
            raise ValueError("invalid alert field count")
        if verb != "ALERT" or not EVENT_ID.fullmatch(event_id):
            raise ValueError("invalid alert header")
        if mode not in {"R", "S", "U"}:
            raise ValueError("invalid alert origin")
        room_index, minute_count, channel_index = int(room), int(minutes), int(channel)
        if not (0 <= room_index < len(ROOMS) and 5 <= minute_count <= 30
                and minute_count % 5 == 0 and 0 <= channel_index < len(CHANNELS)):
            raise ValueError("invalid alert fields")
    except (UnicodeDecodeError, ValueError) as error:
        raise ValueError("invalid Bluetooth alert frame") from error
    return {"event_id": event_id, "room": ROOMS[room_index],
            "horizon_minutes": minute_count, "channel": CHANNELS[channel_index],
            "transport": "Bluetooth SPP", "receiver": "nearby laptop",
            "simulated": {"R": False, "S": True, "U": None}[mode],
            "stored_at_utc": datetime.now(timezone.utc).isoformat()}


def append_receipt(journal: Path, alert: dict) -> None:
    journal.parent.mkdir(parents=True, exist_ok=True)
    with journal.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(alert, separators=(",", ":")) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def stored_ids(journal: Path) -> set[str]:
    if not journal.exists():
        return set()
    ids = set()
    for line in journal.read_text(encoding="utf-8").splitlines():
        try:
            ids.add(json.loads(line)["event_id"])
        except (json.JSONDecodeError, KeyError, TypeError):
            continue
    return ids


def speak(alert: dict) -> None:
    if sys.platform != "win32":
        print("Voice playback requires Windows System.Speech on this receiver", flush=True)
        return
    message = (f"SafeSense demonstration alert. {alert['room']}. "
               f"{alert['channel']} may cross the configured range in about "
               f"{alert['horizon_minutes']} minutes. Check the area.")
    env = os.environ.copy()
    env["SAFESENSE_ALERT_TEXT"] = message
    command = ("Add-Type -AssemblyName System.Speech; "
               "$voice = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
               "$voice.Speak($env:SAFESENSE_ALERT_TEXT)")
    subprocess.Popen(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
                     env=env, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


def handle_frame(serial_port, frame: bytes, journal: Path, seen: set[str], voice: bool) -> dict | None:
    try:
        alert = parse_alert(frame)
    except ValueError:
        return None
    event_id = alert["event_id"]
    new_event = event_id not in seen
    if new_event:
        append_receipt(journal, alert)
        seen.add(event_id)
    serial_port.write(f"ACK|{event_id}\n".encode("ascii"))
    serial_port.flush()
    if voice and new_event:
        speak(alert)
    return alert


def report_to_backend(api_base: str, alert: dict) -> bool:
    """Copy a durable laptop receipt to the dashboard; never gate the SPP ACK."""
    payload = {"event_id": alert["event_id"], "kind": "BLUETOOTH_STORED",
               "room": alert["room"], "channel": alert["channel"],
               "horizon_minutes": alert["horizon_minutes"],
               "stored_at_utc": alert["stored_at_utc"],
               "simulated": alert.get("simulated")}
    request = Request(f"{api_base.rstrip('/')}/api/v1/live/receipts",
                      data=json.dumps(payload).encode("utf-8"),
                      headers={"Content-Type": "application/json",
                               "X-SafeSense-Ingress": "bt-alert-receiver"})
    try:
        with urlopen(request, timeout=3) as response:
            result = json.load(response)
        return (response.status == 202 and result.get("accepted") is True
                and result.get("event_id") == alert["event_id"])
    except (HTTPError, URLError, TimeoutError, ValueError, OSError):
        return False


def sync_journal(journal: Path, api_base: str, reported: set[str]) -> None:
    if not journal.exists():
        return
    attempts = 0
    for line in journal.read_text(encoding="utf-8").splitlines():
        if attempts >= 5:
            break
        try:
            alert = json.loads(line)
            event_id = alert["event_id"]
            if (event_id in reported or not EVENT_ID.fullmatch(event_id)
                    or alert.get("transport") != "Bluetooth SPP"):
                continue
            attempts += 1
            if report_to_backend(api_base, alert):
                reported.add(event_id)
            else:
                break
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            continue


def report_listener_heartbeat(api_base: str) -> None:
    request = Request(f"{api_base.rstrip('/')}/api/v1/live/heartbeat",
                      data=b'{"name":"bt_alert_receiver","status":"listening"}',
                      headers={"Content-Type": "application/json",
                               "X-SafeSense-Ingress": "bt-alert-receiver"})
    try:
        with urlopen(request, timeout=3) as response:
            response.read(1024)
    except (HTTPError, URLError, TimeoutError, OSError):
        pass


def main() -> None:
    parser = argparse.ArgumentParser(description="SafeSense nearby laptop Bluetooth SPP alert receiver")
    parser.add_argument("--port", required=True, help="Paired outgoing Bluetooth COM port, e.g. COM16")
    parser.add_argument("--journal", type=Path, default=Path("data/bt_alert_receipts.jsonl"))
    parser.add_argument("--api", default="http://127.0.0.1:8000",
                        help="Local dashboard API used to sync durable laptop receipts")
    parser.add_argument("--no-voice", action="store_true")
    parser.add_argument("--sos-voice", action="store_true",
                        help="Opt in to Telegram voice messages for real alerts only")
    parser.add_argument("--sos-database", type=Path, default=Path("data/live/sos_voice.db"))
    parser.add_argument("--send-test", action="store_true",
                        help="Request one labelled ESP32 transport test alert after SPP connects")
    args = parser.parse_args()
    if args.sos_voice:
        from scripts.sos_voice import VoiceConfig
        VoiceConfig.from_environment()
    try:
        import serial
    except ImportError as error:
        raise SystemExit("Install the demo extra: pip install -e '.[demo]'") from error
    receiver_lock = acquire_receiver_lock()
    if receiver_lock is None:
        print("Bluetooth receiver already running; leaving COM port to existing listener", flush=True)
        return
    seen = stored_ids(args.journal)
    reported: set[str] = set()
    samples = Receiver(Path("data/live/direct_bt.db"), args.api,
                       ingress="bt-sensor-receiver", sos_voice=args.sos_voice,
                       sos_database=args.sos_database)
    csi = WirelessCsiForwarder(args.api, "ESP32_BLUETOOTH")
    test_sent = False
    last_request_id = read_record(REQUEST).get("request_id")
    while True:
        try:
            with serial.Serial(args.port, baudrate=115200, timeout=1, write_timeout=2) as connection:
                print(f"Listening for paired SPP alerts on {args.port}; journal={args.journal}", flush=True)
                if args.send_test and not test_sent:
                    time.sleep(0.5)  # Let Windows finish the SPP connection handshake.
                    connection.write(b"TEST\n")
                    connection.flush()
                    test_sent = True
                    print("Requested one labelled ESP32 Bluetooth transport test", flush=True)
                next_sync = 0.0
                last_frame_at = time.monotonic()
                while True:
                    requested_id = read_record(REQUEST).get("request_id")
                    if requested_id and requested_id != last_request_id and network_for_idle_check() == RESTORE:
                        last_request_id = requested_id
                        raise serial.SerialException("Dashboard requested Bluetooth COM reconnect")
                    if time.monotonic() >= next_sync:
                        sync_journal(args.journal, args.api, reported)
                        samples.sync_once()
                        samples.sync_status_once()
                        try:
                            samples.dispatch_sos_once()
                        except (OSError, ValueError, sqlite3.Error) as error:
                            print(f"SOS voice worker deferred: {type(error).__name__}", flush=True)
                        report_listener_heartbeat(args.api)
                        next_sync = time.monotonic() + 5
                    frame = connection.readline(1024)
                    if not frame:
                        if time.monotonic() - last_frame_at >= IDLE_RECONNECT_SECONDS:
                            ssid = network_for_idle_check()
                            if idle_reconnect_due(last_frame_at, time.monotonic(), ssid):
                                raise serial.SerialException(
                                    f"No Bluetooth frames for {IDLE_RECONNECT_SECONDS}s on {RESTORE}")
                            if ssid != RESTORE:
                                last_frame_at = time.monotonic()
                        continue
                    if frame.startswith(b"CSI|"):
                        try:
                            csi.submit(frame[4:].decode("ascii").strip())
                        except UnicodeDecodeError:
                            pass
                        continue
                    last_frame_at = time.monotonic()
                    if frame.startswith(b"STATUS|"):
                        try:
                            status_id = samples.accept_status(json.loads(frame[7:]))
                            samples.sync_status_once()
                            print(f"Bluetooth board queue status stored id={status_id}", flush=True)
                        except (ValueError, TypeError, sqlite3.Error, UnicodeDecodeError) as error:
                            print(f"Rejected Bluetooth board status: {error}", flush=True)
                        continue
                    if frame.startswith(b"DATA|"):
                        try:
                            tx = json.loads(frame[5:])
                            event_id, duplicate = samples.accept(tx, speak_alert=False)
                        except (ValueError, KeyError, TypeError, sqlite3.Error) as error:
                            print(f"Rejected Bluetooth sensor frame: {error}", flush=True)
                            continue
                        connection.write(f"ACK|{event_id}\n".encode("ascii"))
                        connection.flush()
                        try:
                            record_frame(event_id)
                        except OSError as error:
                            print(f"Bluetooth frame marker unavailable: {error}", flush=True)
                        print(f"Bluetooth sensor stored event={event_id} duplicate={duplicate}", flush=True)
                        samples.sync_once()
                        continue
                    alert = handle_frame(connection, frame, args.journal, seen, not args.no_voice)
                    if alert:
                        print(f"Laptop stored event={alert['event_id']} room={alert['room']} "
                              f"forecast=+{alert['horizon_minutes']}m", flush=True)
                        if report_to_backend(args.api, alert):
                            reported.add(alert["event_id"])
                        if args.sos_voice and alert["simulated"] is False:
                            from scripts.sos_voice import dispatch
                            try:
                                result = dispatch(alert, args.sos_database)
                                print(f"SOS voice event={alert['event_id']} state={result['state']} "
                                      f"sent={result['messages_sent']}", flush=True)
                            except (OSError, ValueError, sqlite3.Error) as error:
                                print(f"SOS voice event={alert['event_id']} deferred: "
                                      f"{type(error).__name__}", flush=True)
        except (serial.SerialException, OSError) as error:
            print(f"Bluetooth serial disconnected: {error}; retrying in 2 seconds", flush=True)
            time.sleep(2)


if __name__ == "__main__":
    main()
