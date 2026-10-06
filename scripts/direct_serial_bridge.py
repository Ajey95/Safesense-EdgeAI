"""Forward the connected sensor ESP32's JSON lines directly over USB to SafeSense."""

from __future__ import annotations

import argparse
import json
import math
import re
import time
from uuid import uuid4
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import serial

from safesense.schemas import TelemetryIn


FIRMWARE_TAG = "direct-serial-bme680-mq135"
DEFAULT_DEVICE = "safesense-tx-usb-8c94df901fec"


def _number(sample: dict, key: str) -> float:
    value = sample[key]
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{key} must be a finite number")
    return float(value)


def make_telemetry(sample: dict, session_id: str, device_id: str) -> TelemetryIn:
    if not isinstance(sample, dict) or sample.get("sensor_status") != "OK":
        raise ValueError("sensor firmware did not report OK")
    sample_id = sample.get("sample_id")
    if isinstance(sample_id, bool) or not isinstance(sample_id, int) or sample_id < 0:
        raise ValueError("sample_id must be a nonnegative integer")
    adc = sample.get("mq135_adc_raw")
    if isinstance(adc, bool) or not isinstance(adc, int):
        raise ValueError("mq135_adc_raw must be an integer")
    gas = _number(sample, "bme_gas_resistance_ohm")
    return TelemetryIn.model_validate({
        "event_id": f"usb-{session_id}-{sample_id}",
        "device_id": device_id,
        "observed_at": None,
        "firmware_version": FIRMWARE_TAG,
        "environment": {
            "temperature_c": _number(sample, "bme_temperature_c"),
            "humidity_pct": _number(sample, "bme_humidity_pct"),
            "pressure_pa": _number(sample, "bme_pressure_hpa") * 100.0,
            "gas_resistance_ohm": gas,
            "gas_valid": gas > 0,
            "heat_stable": False,
            "gas_adc_raw": adc,
            "gas_risk": "UNAVAILABLE",
            "sensor_healthy": True,
        },
        "csi": {
            "activity": "UNKNOWN", "confidence": 0, "quality": "UNAVAILABLE",
            "tx_node": "ONLINE", "rx_node": "UNKNOWN", "packet_rate_hz": 0,
            "rssi_dbm": -127, "is_fresh": False,
        },
        "system": {"local_storage": "UNKNOWN", "esp32_status": "ONLINE"},
    })


def post_sample(api: str, telemetry: TelemetryIn) -> None:
    data = telemetry.model_dump_json().encode("utf-8")
    request = Request(f"{api.rstrip('/')}/api/v1/telemetry", data=data,
                      headers={"Content-Type": "application/json"})
    with urlopen(request, timeout=5) as response:
        result = json.load(response)
    if result.get("accepted") is not True or result.get("event_id") != telemetry.event_id:
        raise ValueError("backend did not confirm the exact sample ID")


def run(port: str, api: str, interval: float, device_id: str) -> None:
    session_id = uuid4().hex[:12]
    last_posted = -1
    next_due = 0.0
    while True:
        try:
            connection = serial.Serial(port=None, baudrate=115200, timeout=1)
            connection.dtr = False
            connection.rts = False
            connection.port = port
            connection.open()
            print(f"USB sensor bridge listening on {port}; session={session_id}", flush=True)
            with connection:
                while True:
                    raw_line = connection.read_until(b"\n", 2048)
                    if not raw_line or not raw_line.endswith(b"\n"):
                        continue
                    if time.monotonic() < next_due:
                        continue
                    try:
                        sample = json.loads(raw_line)
                        telemetry = make_telemetry(sample, session_id, device_id)
                        if sample["sample_id"] == last_posted:
                            continue
                        post_sample(api, telemetry)
                    except (ValueError, KeyError, TypeError, json.JSONDecodeError,
                            HTTPError, URLError, TimeoutError, OSError) as error:
                        print(f"USB sample deferred: {error}", flush=True)
                        next_due = time.monotonic() + interval
                        continue
                    last_posted = sample["sample_id"]
                    next_due = time.monotonic() + interval
                    print(f"stored {telemetry.event_id} T={telemetry.environment.temperature_c:.2f}C "
                          f"RH={telemetry.environment.humidity_pct:.2f}% "
                          f"MQ135={telemetry.environment.gas_adc_raw} raw", flush=True)
        except serial.SerialException as error:
            print(f"USB port unavailable: {error}; retrying", flush=True)
            time.sleep(3)


def main() -> None:
    parser = argparse.ArgumentParser(description="Show physical BME680/MQ-135 readings in SafeSense over USB")
    parser.add_argument("--port", default="COM12")
    parser.add_argument("--api", default="http://127.0.0.1:8000")
    parser.add_argument("--interval", type=float, default=2.0)
    parser.add_argument("--device-id", default=DEFAULT_DEVICE)
    args = parser.parse_args()
    if not re.fullmatch(r"COM\d{1,3}", args.port.upper()) or args.interval < 0.5:
        parser.error("use a COM port and an interval of at least 0.5 seconds")
    run(args.port.upper(), args.api, args.interval, args.device_id)


if __name__ == "__main__":
    main()
