"""Capture simultaneous V1 TX/RX UART evidence without changing flash."""

import argparse
import time

import serial


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tx", default="COM11")
    parser.add_argument("--rx", default="COM12")
    parser.add_argument("--seconds", type=float, default=45)
    args = parser.parse_args()
    with serial.Serial(args.tx, 115200, timeout=0.05) as tx, serial.Serial(
        args.rx, 115200, timeout=0.05
    ) as rx:
        end = time.monotonic() + args.seconds
        while time.monotonic() < end:
            for name, port in (("TX", tx), ("RX", rx)):
                line = port.readline().decode(errors="replace").rstrip()
                if line and (
                    "safesense_" in line or "Guru" in line or "Backtrace" in line
                    or "Cache" in line or "wifi:station" in line
                    or "sta ip:" in line or "rst:" in line or "abort" in line
                ):
                    print(f"{name}: {line}", flush=True)


if __name__ == "__main__":
    main()
