"""Forward ESP32 CSI lines received over Wi-Fi UDP or Bluetooth SPP."""

from __future__ import annotations

import json
import queue
import socket
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from safesense.csi_count_api import parse_line

CSI_UDP_PORT = 3335


class WirelessCsiForwarder:
    def __init__(self, api: str, source: str):
        if source not in {"ESP32_WIFI", "ESP32_BLUETOOTH"}:
            raise ValueError("wireless CSI source required")
        self.api = api.rstrip("/")
        self.source = source
        self.pending: queue.Queue[str] = queue.Queue(maxsize=500)
        self.dropped = 0
        threading.Thread(target=self._run, name=f"csi-{source.lower()}", daemon=True).start()

    def submit(self, line: str) -> bool:
        try:
            parse_line(line)
            self.pending.put_nowait(line)
            return True
        except (ValueError, queue.Full):
            self.dropped += 1
            return False

    def _run(self) -> None:
        while True:
            first = self.pending.get()
            lines = [first]
            deadline = time.monotonic() + 0.25
            while len(lines) < 30:
                try:
                    lines.append(self.pending.get(timeout=max(0, deadline - time.monotonic())))
                except queue.Empty:
                    break
            request = Request(f"{self.api}/api/v1/csi-count/packets",
                              data=json.dumps({"source": self.source, "lines": lines}).encode("utf-8"),
                              headers={"Content-Type": "application/json"})
            try:
                with urlopen(request, timeout=3) as response:
                    result = json.load(response)
                if result.get("accepted") != len(lines):
                    raise ValueError("partial CSI batch acceptance")
            except (HTTPError, URLError, TimeoutError, OSError, ValueError) as error:
                self.dropped += len(lines)
                print(f"{self.source} CSI batch dropped ({len(lines)}): {type(error).__name__}", flush=True)


def wifi_csi_loop(api: str) -> None:
    forwarder = WirelessCsiForwarder(api, "ESP32_WIFI")
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as receiver:
        receiver.bind(("0.0.0.0", CSI_UDP_PORT))
        print(f"ESP32 CSI Wi-Fi UDP receiver listening on {CSI_UDP_PORT}", flush=True)
        while True:
            data, address = receiver.recvfrom(256)
            if address[0] != "192.168.4.1":
                continue
            try:
                line = data.decode("ascii").strip()
            except UnicodeDecodeError:
                continue
            forwarder.submit(line)
