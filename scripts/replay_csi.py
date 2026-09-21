"""Generate ESP32-shaped CSI windows for dashboard and API integration testing.

This is a labelled simulator, not evidence of real HAR accuracy. Replace its frame
source with recorded ESP32 CSI after hardware collection.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from itertools import cycle
import json
from math import sin
from random import Random
from time import sleep
from urllib.request import Request, urlopen
from uuid import uuid4

from safesense.csi import CsiFrame, CsiWindowAssembler, amplitude_summary, rms_motion


def raw_frame(step: int, motion: float, random: Random) -> CsiFrame:
    values: list[int] = []
    for carrier in range(64):
        phase = step * (0.06 + motion * 0.02) + carrier * 0.13
        real = int(36 * sin(phase) + random.uniform(-2, 2))
        imaginary = int(32 * sin(phase + 0.8) + random.uniform(-2, 2))
        values.extend((imaginary, real))  # ESP32 ordering: imaginary then real.
    return CsiFrame(tuple(values), first_word_invalid=False, rssi_dbm=-48)


def post(url: str, body: dict) -> None:
    request = Request(url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}, method="POST")
    with urlopen(request, timeout=3) as response:
        print(response.read().decode())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8000/api/v1/telemetry")
    parser.add_argument("--interval", type=float, default=1.5)
    parser.add_argument("--iterations", type=int, default=None, help="Stop after this many CSI windows; useful for smoke tests.")
    args = parser.parse_args()
    rng, assembler = Random(20260919), CsiWindowAssembler()
    scenes = cycle((("VACANT", 0.10, 0.93), ("WALKING", 1.00, 0.89), ("STATIONARY", 0.28, 0.83), ("UNKNOWN", 0.00, 0.0)))
    step = 0
    sent = 0
    while args.iterations is None or sent < args.iterations:
        activity, motion, confidence = next(scenes)
        window = None
        for _ in range(100):
            step += 1
            window = assembler.push(raw_frame(step, motion, rng)) or window
        assert window is not None
        body = {
            "event_id": str(uuid4()), "device_id": "safesense-csi-replay-01", "observed_at": datetime.now(timezone.utc).isoformat(), "firmware_version": "replay-0.1",
            "environment": {"temperature_c": 28.4, "humidity_pct": 61.0, "gas_risk": "NORMAL", "sensor_healthy": True},
            "csi": {"activity": activity, "confidence": confidence, "quality": "GOOD" if activity != "UNKNOWN" else "UNAVAILABLE", "tx_node": "ONLINE" if activity != "UNKNOWN" else "UNKNOWN", "rx_node": "ONLINE", "packet_rate_hz": 82.0 if activity != "UNKNOWN" else 0.0, "rssi_dbm": -48, "is_fresh": activity != "UNKNOWN", "window_frames": window.frame_count, "selected_subcarriers": 48, "model_version": "replay-baseline", "amplitude_summary": amplitude_summary(window), "motion_rms": round(rms_motion(window), 3)},
            "system": {"mqtt": "CONNECTED", "local_storage": "OK", "esp32_status": "ONLINE"},
        }
        try:
            post(args.url, body)
        except OSError as error:
            print(f"Delivery deferred: {error}")
        sent += 1
        sleep(args.interval)


if __name__ == "__main__":
    main()
