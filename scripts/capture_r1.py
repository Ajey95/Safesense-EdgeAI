"""Print selected TX/RX UART fields for the R1 live presentation."""

from __future__ import annotations

import argparse
import re
import time

import serial


READING = re.compile(r"BME680 T=[-\d.]+ C RH=[-\d.]+ % P=[-\d.]+ Pa")
EVIDENCE = (
    "Custom BME680 initialized",
    "Restored ",
    "Persisted event=",
    "RX accepted event=",
    "HTTP TX accepted event=",
    "CSI window ready",
    "Host forward ACK",
)


def selected_line(board: str, line: str) -> str | None:
    reading = READING.search(line)
    if reading:
        return f"{board}: {reading.group()}"
    if "safesense_" in line and any(marker in line for marker in EVIDENCE):
        return f"{board}: {line}"
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Display selected real UART fields")
    parser.add_argument("--tx", default="COM11")
    parser.add_argument("--rx", default="COM13")
    parser.add_argument("--seconds", type=float, default=300)
    args = parser.parse_args()

    print("Selected UART fields from TX and RX; original firmware output is unchanged.", flush=True)
    with serial.Serial(args.tx, 115200, timeout=0.05) as tx, serial.Serial(
        args.rx, 115200, timeout=0.05
    ) as rx:
        end = time.monotonic() + args.seconds
        while time.monotonic() < end:
            for board, port in (("TX", tx), ("RX", rx)):
                line = port.readline().decode(errors="replace").rstrip()
                result = selected_line(board, line)
                if result:
                    print(result, flush=True)


if __name__ == "__main__":
    main()
