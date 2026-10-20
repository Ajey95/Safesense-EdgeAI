"""Run a bounded one-board CSI probe window and restore laptop Wi-Fi.

Start the SafeSense API and csi_count_receiver.py before this script. The
receiver owns COM11; this script only manages the laptop Wi-Fi link and sends
UDP probe traffic to the sensor board's access point.
"""

from __future__ import annotations

import argparse
import re
import socket
import subprocess
import time
from urllib.request import urlopen
import json


def netsh(*arguments: str) -> str:
    result = subprocess.run(
        ["netsh", "wlan", *arguments], capture_output=True, text=True,
        errors="replace", check=False,
    )
    output = (result.stdout + result.stderr).strip()
    if result.returncode:
        print(f"netsh {' '.join(arguments)}: {output}", flush=True)
    return output


def connected_ssid() -> str | None:
    output = netsh("show", "interfaces")
    match = re.search(r"^\s*SSID\s*:\s*(.*?)\s*$", output, re.MULTILINE)
    return match.group(1) if match else None


def read_status(api: str) -> dict:
    with urlopen(api.rstrip("/") + "/api/v1/csi-count/status", timeout=15) as response:
        return json.load(response)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seconds", type=int, default=90)
    parser.add_argument("--rate", type=float, default=40.0)
    parser.add_argument("--board-ssid", default="SafeSense-TX-Laptop")
    parser.add_argument("--restore-ssid", default="Amrita")
    parser.add_argument("--api", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    if not 10 <= args.seconds <= 300 or not 1 <= args.rate <= 60:
        parser.error("seconds must be 10–300 and rate must be 1–60")

    # Fail before changing Wi-Fi if the local model/API is unavailable.
    before = read_status(args.api)
    print(f"Initial CSI source={before['source']} packets={before['packet_count']}", flush=True)
    original = connected_ssid()
    if original not in (args.restore_ssid, args.board_ssid):
        parser.error(f"Expected {args.restore_ssid} or {args.board_ssid}; connected to {original!r}")

    sender: socket.socket | None = None
    sent = 0
    last_connection_attempt = -100.0
    last_link_check = -100.0
    last_status_check = -100.0
    link = original
    deadline = time.monotonic() + args.seconds
    next_send = time.monotonic()
    print(f"CSI window {args.seconds}s; Amrita restoration is in finally", flush=True)
    try:
        netsh("set", "profileparameter", f"name={args.restore_ssid}", "connectionmode=manual")
        while time.monotonic() < deadline:
            now = time.monotonic()
            if now - last_link_check >= 2:
                link = connected_ssid()
                last_link_check = now
                if link != args.board_ssid:
                    if sender is not None:
                        sender.close()
                        sender = None
                    if now - last_connection_attempt >= 5:
                        netsh("disconnect", "interface=Wi-Fi")
                        time.sleep(2)
                        netsh("connect", f"name={args.board_ssid}", "interface=Wi-Fi")
                        last_connection_attempt = time.monotonic()
                elif sender is None:
                    sender = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                    print(f"Joined {args.board_ssid}; sending CSI probes", flush=True)
                    next_send = now

            if sender is not None and now >= next_send:
                try:
                    sender.sendto(sent.to_bytes(4, "little") + bytes(28), ("192.168.4.1", 3334))
                    sent += 1
                except OSError as error:
                    print(f"Probe send interrupted: {error}", flush=True)
                    sender.close()
                    sender = None
                    link = None
                next_send = now + 1 / args.rate

            if now - last_status_check >= 5:
                status = read_status(args.api)
                print(
                    f"wifi={link or 'disconnected'} sent={sent} "
                    f"csi={status['packet_count']} frames={status['buffered_frames']} "
                    f"status={status['status']} count={status['predicted_count']} "
                    f"quality={status.get('quality_reason')} age={status['age_seconds']}", flush=True,
                )
                last_status_check = time.monotonic()
            time.sleep(0.01)
    finally:
        if sender is not None:
            sender.close()
        netsh("set", "profileparameter", f"name={args.restore_ssid}", "connectionmode=auto")
        for _ in range(3):
            netsh("connect", f"name={args.restore_ssid}", "interface=Wi-Fi")
            time.sleep(3)
            if connected_ssid() == args.restore_ssid:
                break
        print(f"Restored Wi-Fi: {connected_ssid()}", flush=True)


if __name__ == "__main__":
    main()
