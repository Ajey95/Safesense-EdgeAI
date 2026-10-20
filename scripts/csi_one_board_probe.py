"""Send laptop Wi-Fi frames to a SafeSense CSI receiver running as an AP.

Connect the laptop to the receiver's SafeSense-RX-V1 network first. These UDP
datagrams give the ESP32 a steady incoming Wi-Fi signal to measure as CSI.
"""

import argparse
import socket
import time


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="192.168.4.1", help="Receiver AP address")
    parser.add_argument("--port", type=int, default=3333, help="Receiver UDP probe port")
    parser.add_argument("--rate", type=float, default=40.0, help="Packets per second")
    args = parser.parse_args()
    if not 1 <= args.rate <= 60:
        parser.error("--rate must be between 1 and 60 packets per second")

    interval = 1.0 / args.rate
    count = 0
    next_send = time.monotonic()
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as connection:
        print(f"Sending Wi-Fi probes to {args.host}:{args.port} at {args.rate:g}/s", flush=True)
        try:
            while True:
                connection.sendto(count.to_bytes(4, "little") + bytes(28), (args.host, args.port))
                count += 1
                next_send += interval
                time.sleep(max(0.0, next_send - time.monotonic()))
        except KeyboardInterrupt:
            print(f"Stopped after {count} probes", flush=True)


if __name__ == "__main__":
    main()
