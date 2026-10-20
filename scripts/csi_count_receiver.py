"""Forward real ESP32 RX WISDOM_CSI serial lines to the local count demo.

Example: python scripts/csi_count_receiver.py --port COM11
"""

import argparse
import csv
import json
import re
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import serial
from safesense.csi_count_api import parse_line
from scripts.direct_laptop_receiver import Receiver


PERSISTED_EVENT = re.compile(
    r"(?:Persisted event=([A-Za-z0-9_.:-]{8,63}) pending=\d+|"
    r"Sensor sample event=([A-Za-z0-9_.:-]{8,63})) JSON=(\{.*\})$")
TX_NVS_PERSISTED = re.compile(
    r"Persisted event=([A-Za-z0-9_.:-]{8,63}) pending=(\d{1,2}) JSON=")


def parse_persisted_sensor_line(raw: bytes) -> dict | None:
    line = raw.decode("utf-8", errors="replace").strip()
    match = PERSISTED_EVENT.search(line)
    if not match:
        return None
    try:
        event = json.loads(match.group(3))
    except json.JSONDecodeError:
        return None
    return event if isinstance(event, dict) and event.get("event_id") == (match.group(1) or match.group(2)) else None


def safe_serial_log(raw: bytes) -> str:
    return raw.decode("ascii", errors="backslashreplace").strip()[:220]


def sync_sensor_loop(receiver: Receiver, stop: threading.Event) -> None:
    while not stop.wait(0.5):
        try:
            receiver.sync_once()
        except (OSError, ValueError) as error:
            print(f"USB sensor backend sync deferred: {error}", flush=True)


def post_batch(api: str, lines: list[str]) -> dict:
    body = json.dumps({"lines": lines}).encode("utf-8")
    request = Request(api.rstrip("/") + "/api/v1/csi-count/packets", data=body,
                      headers={"Content-Type": "application/json"}, method="POST")
    with urlopen(request, timeout=5) as response:
        return json.load(response)


def validated_csi_line(raw: bytes) -> str | None:
    line = raw.decode("ascii", errors="replace").strip()
    if not line.startswith("WISDOM_CSI,"):
        return None
    try:
        parse_line(line)
    except ValueError:
        return None
    return line


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True, help="CSI RX ESP32 serial port, e.g. COM11")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--api", default="http://127.0.0.1:8000")
    parser.add_argument("--capture", type=Path, help="Append accepted raw CSI lines to a local CSV")
    parser.add_argument("--sensor-journal", type=Path,
                        default=Path("data/live/direct_usb.db"),
                        help="Durable local journal for ESP32 sensor JSON seen on the same COM port")
    parser.add_argument("--diagnostic-lines", action="store_true",
                        help="Log brief board status lines while reading the stream")
    args = parser.parse_args()
    lines: list[str] = []
    last_send = time.monotonic()
    print(f"Reading CSI from {args.port} at {args.baud} baud", flush=True)
    capture = None
    writer = None
    if args.capture:
        args.capture.parent.mkdir(parents=True, exist_ok=True)
        empty = not args.capture.exists() or args.capture.stat().st_size == 0
        capture = args.capture.open("a", newline="", encoding="utf-8")
        writer = csv.writer(capture)
        if empty:
            writer.writerow(["accepted_at_utc", "serial_line"])
            capture.flush()
    sensor = Receiver(args.sensor_journal, args.api, ingress="usb-serial-receiver")
    stop = threading.Event()
    threading.Thread(target=sync_sensor_loop, args=(sensor, stop), daemon=True).start()
    with serial.Serial(args.port, args.baud, timeout=0.2) as port:
        print(f"Serial port {args.port} opened", flush=True)
        while True:
            raw = port.readline()
            if raw:
                if args.diagnostic_lines:
                    queue_write = TX_NVS_PERSISTED.search(raw.decode("ascii", errors="replace"))
                    if queue_write:
                        print(f"TX NVS persisted event={queue_write.group(1)} "
                              f"pending={queue_write.group(2)}/16", flush=True)
                if args.diagnostic_lines and b"safesense_tx:" in raw and b"JSON=" not in raw:
                    print(safe_serial_log(raw), flush=True)
                tx = parse_persisted_sensor_line(raw)
                if tx is not None:
                    try:
                        event_id, duplicate = sensor.accept(tx, speak_alert=False)
                        if not duplicate:
                            print(f"USB sensor event journaled: {event_id}", flush=True)
                    except (ValueError, KeyError, TypeError) as error:
                        print(f"Discarded malformed USB sensor event: {error}", flush=True)
                line = validated_csi_line(raw)
                if line is not None:
                    lines.append(line)
                elif raw.startswith(b"WISDOM_CSI,"):
                    print("Discarded malformed CSI serial line", flush=True)
            now = time.monotonic()
            if lines and (len(lines) >= 20 or now - last_send >= 0.5):
                try:
                    result = post_batch(args.api, lines)
                    print(f"Accepted {result['accepted']} CSI packets; total {result['total_packets']}", flush=True)
                    if writer is not None and result["accepted"] == len(lines):
                        accepted_at = datetime.now(timezone.utc).isoformat()
                        writer.writerows((accepted_at, line) for line in lines)
                        capture.flush()
                    lines.clear()
                    last_send = now
                except Exception as error:
                    if isinstance(error, HTTPError) and error.code == 422:
                        try:
                            detail = json.loads(error.read()).get("detail")
                        except (ValueError, OSError):
                            detail = None
                        if isinstance(detail, str):
                            print(f"CSI batch rejected: {detail}", flush=True)
                    print(f"CSI bridge error: {error}; retrying batch", flush=True)
                    time.sleep(1)


if __name__ == "__main__":
    main()
