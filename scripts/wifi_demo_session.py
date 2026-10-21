"""Bounded SafeSense AP visit with an independent return to Amrita Wi-Fi."""

from __future__ import annotations

import argparse
import json
import os
import re
import socket
import subprocess
import time
from uuid import uuid4
from datetime import datetime, timedelta, timezone
from pathlib import Path

from scripts.transport_events import append_event

ROOT = Path(__file__).resolve().parents[1]
STATUS = ROOT / "data/live/wifi_demo_session.json"
CANCEL = ROOT / "data/live/wifi_demo_cancel.txt"
TARGET = "SafeSense-TX-Laptop"
RESTORE = "Amrita"


def current_ssid() -> str | None:
    result = subprocess.run(["netsh", "wlan", "show", "interfaces"],
                            capture_output=True, text=True, errors="replace", timeout=10)
    for line in result.stdout.splitlines():
        match = re.match(r"^\s*SSID\s*:\s*(.*?)\s*$", line)
        if match:
            return match.group(1)
    return None


def write_status(state: str, **details: object) -> None:
    STATUS.parent.mkdir(parents=True, exist_ok=True)
    record = {"state": state, "updated_at_utc": datetime.now(timezone.utc).isoformat(), **details}
    temporary = STATUS.with_suffix(f".{os.getpid()}.tmp")
    temporary.write_text(json.dumps(record), encoding="utf-8")
    os.replace(temporary, STATUS)
    try:
        append_event(state, **details)
    except OSError:
        # A history write must never prevent the timed return to normal Wi-Fi.
        pass


def cancel_requested(session_id: str) -> bool:
    try:
        return CANCEL.read_text(encoding="ascii").strip() == session_id
    except OSError:
        return False


def request_cancel(session_id: str) -> None:
    CANCEL.parent.mkdir(parents=True, exist_ok=True)
    temporary = CANCEL.with_suffix(f".{os.getpid()}.tmp")
    temporary.write_text(session_id, encoding="ascii")
    os.replace(temporary, CANCEL)


def connect(profile: str, timeout: float | None = None,
            session_id: str | None = None) -> tuple[bool, str | None]:
    timeout = timeout if timeout is not None else (15 if profile == TARGET else 18)
    if profile == TARGET:
        for attempt in range(3):
            if session_id and cancel_requested(session_id):
                return False, "Manual return requested"
            try:
                scan = subprocess.run(["netsh", "wlan", "show", "networks", "mode=bssid"],
                                      capture_output=True, text=True, errors="replace", timeout=6)
                visible = {match.group(1).strip() for line in scan.stdout.splitlines()
                           if (match := re.match(r"^\s*SSID\s+\d+\s*:\s*(.*?)\s*$", line))}
            except (OSError, subprocess.TimeoutExpired):
                visible = set()
            if profile in visible:
                break
            if attempt == 2:
                return False, "ESP32 AP not visible after three Windows scans"
            time.sleep(0.5)
    result = subprocess.run(["netsh", "wlan", "connect", f"name={profile}", "interface=Wi-Fi"],
                            capture_output=True, text=True, errors="replace", timeout=10)
    if result.returncode != 0:
        return False, "Windows rejected the saved Wi-Fi profile"
    started = time.monotonic()
    deadline = started + timeout
    retry_at = started + timeout / 2
    retried = False
    while time.monotonic() < deadline:
        if session_id and cancel_requested(session_id):
            return False, "Manual return requested"
        if current_ssid() == profile:
            return True, None
        if profile == TARGET and not retried and time.monotonic() >= retry_at:
            retried = True
            subprocess.run(["netsh", "wlan", "connect", f"name={profile}", "interface=Wi-Fi"],
                           capture_output=True, text=True, errors="replace", timeout=10)
        time.sleep(0.25)
    return False, f"{profile} did not become the connected SSID within {timeout:.0f} seconds"


def prepare_ap_scan() -> tuple[bool, str | None]:
    manual = subprocess.run(["netsh", "wlan", "set", "profileparameter",
                             f"name={RESTORE}", "connectionmode=manual"],
                            capture_output=True, text=True, errors="replace", timeout=6)
    if manual.returncode != 0:
        return False, "Could not suspend Amrita auto-reconnect for the bounded ESP32 visit"
    disconnected = subprocess.run(["netsh", "wlan", "disconnect", "interface=Wi-Fi"],
                                  capture_output=True, text=True, errors="replace", timeout=6)
    if disconnected.returncode != 0:
        return False, "Windows could not release the Wi-Fi adapter for the ESP32 scan"
    time.sleep(1)
    return True, None


def restore_auto() -> None:
    subprocess.run(["netsh", "wlan", "set", "profileparameter",
                    f"name={RESTORE}", "connectionmode=auto"],
                   capture_output=True, text=True, errors="replace", timeout=6)


def run_probe_loop(duration: float, session_id: str) -> tuple[int, int, str | None]:
    sent = 0
    errors = 0
    reason = None
    end = time.monotonic() + duration
    next_probe = time.monotonic()
    next_link_check = next_probe
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sender:
        while time.monotonic() < end:
            now = time.monotonic()
            if cancel_requested(session_id):
                reason = "Manual return requested"
                break
            if now >= next_link_check:
                if current_ssid() != TARGET:
                    reason = "ESP32 Wi-Fi link ended before the timed visit completed"
                    break
                next_link_check = now + 2
            if now >= next_probe:
                try:
                    sender.sendto(sent.to_bytes(4, "little") + bytes(28),
                                  ("192.168.4.1", 3334))
                    sent += 1
                    next_probe = now + 0.025
                except OSError:
                    # The route may be briefly unavailable before DHCP finishes.
                    errors += 1
                    next_probe = now + 0.1
            time.sleep(0.005)
    if sent == 0 and errors and reason is None:
        reason = "ESP32 AP stayed connected, but no CSI probe was delivered"
    return sent, errors, reason


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--duration", type=int, default=120)
    parser.add_argument("--restore-only", action="store_true")
    parser.add_argument("--session-id")
    args = parser.parse_args()
    if args.restore_only:
        write_status("RESTORING", target=RESTORE)
        try:
            ok, reason = connect(RESTORE)
        finally:
            restore_auto()
        write_status("RESTORED" if ok else "RESTORE_FAILED", target=RESTORE,
                     current_ssid=current_ssid(), reason=reason)
        return
    if not 20 <= args.duration <= 180:
        raise SystemExit("Duration must be 20-180 seconds")
    until = datetime.now(timezone.utc) + timedelta(seconds=args.duration + 20)
    ap_connected = False
    failure = None
    probes_sent = 0
    probe_errors = 0
    session_id = args.session_id or uuid4().hex
    try:
        write_status("CONNECTING", target=TARGET, restore=RESTORE,
                     session_id=session_id, duration_seconds=args.duration,
                     return_by_utc=until.isoformat())
        if cancel_requested(session_id):
            failure = "Manual return requested"
            return
        prepared, failure = prepare_ap_scan()
        if prepared and not cancel_requested(session_id):
            ap_connected, failure = connect(TARGET, session_id=session_id)
        if cancel_requested(session_id):
            failure = "Manual return requested"
            return
        if not ap_connected:
            write_status("AP_CONNECTION_FAILED", target=TARGET, current_ssid=current_ssid(), reason=failure)
            return
        until = datetime.now(timezone.utc) + timedelta(seconds=args.duration)
        write_status("ON_SAFESENSE_AP", target=TARGET, restore=RESTORE,
                     session_id=session_id, duration_seconds=args.duration,
                     return_by_utc=until.isoformat())
        probes_sent, probe_errors, failure = run_probe_loop(args.duration, session_id)

    finally:
        write_status("RESTORING", target=RESTORE)
        try:
            ok, reason = connect(RESTORE)
        finally:
            restore_auto()
        write_status("RESTORED" if ok else "RESTORE_FAILED", target=RESTORE,
                     current_ssid=current_ssid(), ap_connected=ap_connected,
                     csi_probes_sent=probes_sent, csi_probe_errors=probe_errors,
                     reason=failure or reason)
        if not cancel_requested(session_id):
            from scripts.transport_handoff import request_reconnect
            request_reconnect()


if __name__ == "__main__":
    main()
