"""USB scenario playback into the dedicated TX firmware demo mode."""

from __future__ import annotations

import time

import numpy as np

from .forecast_scenarios import ROOMS


def parse_demo_result(line: str) -> dict | None:
    if not line.startswith("DEMO_RESULT|"):
        return None
    parts = line.strip().split("|")
    if len(parts) != 8 or not parts[1].startswith("tx-"):
        raise ValueError("invalid TX demo result")
    numbers = [int(part) for part in parts[2:]]
    if any(value not in (0, 1) for value in (numbers[0], numbers[1], numbers[2], numbers[5])):
        raise ValueError("invalid TX receipt state")
    return {"event_id": parts[1], "alert": bool(numbers[0]), "rx_ack": bool(numbers[1]),
            "bt_ack": bool(numbers[2]), "horizon_minutes": numbers[3],
            "channel": numbers[4], "tx_persisted": bool(numbers[5])}


def replay_on_tx(port: str, values: np.ndarray, now: int, room: str, fault: bool) -> dict:
    try:
        import serial
    except ImportError as error:
        raise RuntimeError("Install the demo extra: pip install -e '.[demo]'") from error
    if room not in ROOMS or now < 60 or now >= len(values):
        raise ValueError("invalid scenario replay input")
    with serial.Serial(port, baudrate=115200, timeout=0.2, write_timeout=2) as connection:
        # USB serial open can reset some ESP32 development boards.
        time.sleep(1.2)
        connection.reset_input_buffer()
        deadline = time.monotonic() + 40
        next_reset = 0.0
        while time.monotonic() < deadline:
            if time.monotonic() >= next_reset:
                connection.write(b"RESET\n")
                next_reset = time.monotonic() + 2
            if connection.readline().strip() == b"DEMO_READY":
                break
        else:
            raise TimeoutError("TX did not report DEMO_READY; check demo firmware and COM port")
        room_index = ROOMS.index(room)
        for minute in range(now - 60, now + 1):
            sensor = values[minute]
            line = (f"SIM|{room_index}|{minute}|{sensor[0]:.4f}|{sensor[1]:.4f}|"
                    f"{sensor[2]:.2f}|{sensor[3]:.2f}|{sensor[4]:.0f}|"
                    f"{1 if fault and minute == now else 0}\n")
            connection.write(line.encode("ascii"))
        connection.flush()
        deadline = time.monotonic() + 25
        edge_forecast = None
        while time.monotonic() < deadline:
            raw = connection.readline()
            if not raw:
                continue
            line = raw.decode("ascii", errors="replace").strip()
            if line == "DEMO_INVALID":
                raise ValueError("TX rejected a synthetic sample")
            if line.startswith("DEMO_ERROR|"):
                raise RuntimeError(line)
            if line.startswith("DEMO_FORECAST|"):
                parts = line.split("|")
                if len(parts) == 6:
                    edge_forecast = [float(part) for part in parts[1:]]
                continue
            result = parse_demo_result(line)
            if result:
                result["edge_forecast_30min"] = edge_forecast
                return result
        raise TimeoutError("TX did not return an event result")
