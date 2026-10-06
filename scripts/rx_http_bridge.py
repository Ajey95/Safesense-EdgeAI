"""Poll the V1 RX board and forward persisted TX JSON to local FastAPI."""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from safesense.schemas import TelemetryIn


def convert_rx_event(pending: dict[str, Any]) -> dict[str, Any]:
    """Translate the RX receipt without inventing gas or activity results."""
    tx = pending["tx"]
    rx = pending["rx"]
    if (pending["event_id"] != tx["event_id"] or tx["schema_version"] != 1
            or rx["transport"] != "HTTP POST" or rx["queue_persisted"] is not True):
        raise ValueError("RX receipt does not match a persisted V1 HTTP event")
    bme = tx["bme680"]
    mq = tx["mq135"]
    csi_fresh = (rx["csi_frames"] > 0 and rx["seen_age_ms"] is not None
                 and rx["seen_age_ms"] <= 20_000)
    window_ready = csi_fresh and rx.get("csi_windows", 0) > 0
    return {
        "event_id": tx["event_id"],
        "device_id": tx["tx_device_id"],
        "firmware_version": "synthetic-forecast-demo" if tx.get("simulated") is True else None,
        "observed_at": tx["observed_at"],
        "environment": {
            "temperature_c": bme["temperature_c"],
            "humidity_pct": bme["humidity_pct"],
            "pressure_pa": bme["pressure_pa"],
            "gas_resistance_ohm": bme["gas_resistance_ohm"],
            "gas_valid": bme["gas_valid"] and bme.get("heat_stable") is True,
            "heat_stable": bme.get("heat_stable") is True,
            "gas_adc_raw": mq["adc_raw"],
            "gas_risk": tx["gas_risk"],
            "sensor_healthy": bme["sensor_healthy"],
        },
        "csi": {
            "activity": "UNKNOWN",
            "confidence": 0,
            "quality": "UNAVAILABLE",
            "tx_node": "ONLINE",
            "rx_node": "ONLINE",
            "packet_rate_hz": rx["csi_packet_rate_hz"] if csi_fresh else 0,
            "rssi_dbm": rx["csi_rssi_dbm"] if csi_fresh else -127,
            "is_fresh": csi_fresh,
            "window_ready": window_ready,
            "window_frames": 100 if window_ready else None,
            "selected_subcarriers": rx.get("csi_min_measured_subcarriers") if window_ready else None,
        },
        "system": {"local_storage": "OK", "esp32_status": "ONLINE"},
        "communication": {
            "tx_rx_transport": rx["transport"],
            "rx_device_id": rx["device_id"],
            "rx_received_uptime_ms": rx["received_uptime_ms"],
            "rx_queue_persisted": rx["queue_persisted"],
            "tx_sequence": tx.get("sequence"),
        },
    }


def _request_json(url: str, payload: dict[str, Any] | None = None,
                  headers: dict[str, str] | None = None) -> dict[str, Any] | None:
    body = None if payload is None else json.dumps(payload, separators=(",", ":")).encode()
    request_headers = {"Content-Type": "application/json"} if body else {}
    request_headers.update(headers or {})
    request = Request(url, data=body, headers=request_headers)
    with urlopen(request, timeout=5) as response:
        if response.status == 204:
            return None
        if response.status not in (200, 202):
            raise ValueError(f"unexpected HTTP status {response.status}")
        content = response.read(4097)
        if len(content) > 4096:
            raise ValueError("HTTP JSON response too large")
        result = json.loads(content)
        if not isinstance(result, dict):
            raise ValueError("HTTP response must be a JSON object")
        return result


def forward_once(rx_base: str, api_base: str, on_forwarded=None) -> str:
    """Return empty, forwarded, or deferred; never ACK RX on backend failure."""
    try:
        pending = _request_json(f"{rx_base.rstrip('/')}/api/v1/pending")
        if pending is None:
            return "empty"
        converted = TelemetryIn.model_validate(convert_rx_event(pending)).model_dump(mode="json")
        event_id = converted["event_id"]
        accepted = _request_json(f"{api_base.rstrip('/')}/api/v1/telemetry", converted,
                                 {"X-SafeSense-Ingress": "rx-http-bridge"})
        if accepted is None or accepted.get("accepted") is not True or accepted.get("event_id") != event_id:
            return "deferred"
        acknowledged = _request_json(f"{rx_base.rstrip('/')}/api/v1/forward-ack", {"event_id": event_id})
        if acknowledged is None or acknowledged.get("event_id") != event_id or acknowledged.get("status") != "ACKED":
            return "deferred"
        if on_forwarded is not None:
            try:
                on_forwarded(event_id)
            except (HTTPError, URLError, TimeoutError, ValueError, OSError) as error:
                print(f"forwarded event={event_id}; live receipt sync deferred: {error}", flush=True)
        print(f"forwarded event={event_id} backend=HTTP POST RX=ACKED", flush=True)
        return "forwarded"
    except (HTTPError, URLError, TimeoutError, ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
        print(f"deferred RX forwarding: {error}", flush=True)
        return "deferred"


def append_forward_receipt(journal: Path, event_id: str) -> None:
    journal.parent.mkdir(parents=True, exist_ok=True)
    with journal.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"event_id": event_id, "kind": "RX_FORWARD_ACKED"}) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def sync_forward_receipts(journal: Path, api_base: str, reported: set[str]) -> None:
    if not journal.exists():
        return
    attempts = 0
    for line in journal.read_text(encoding="utf-8").splitlines():
        if attempts >= 5:
            break
        try:
            item = json.loads(line)
            event_id = item["event_id"]
            if (item.get("kind") != "RX_FORWARD_ACKED" or event_id in reported
                    or not isinstance(event_id, str) or not event_id.startswith("tx-")):
                continue
            attempts += 1
            result = _request_json(f"{api_base.rstrip('/')}/api/v1/live/receipts", item,
                                   {"X-SafeSense-Ingress": "rx-http-bridge"})
            if result and result.get("accepted") is True and result.get("event_id") == event_id:
                reported.add(event_id)
        except (ValueError, KeyError, TypeError, json.JSONDecodeError):
            continue
        except (HTTPError, URLError, TimeoutError, OSError):
            break


def main() -> None:
    parser = argparse.ArgumentParser(description="Bridge persisted RX HTTP telemetry to local SafeSense API")
    parser.add_argument("--rx", default="http://192.168.4.1")
    parser.add_argument("--api", default="http://127.0.0.1:8000")
    parser.add_argument("--interval", type=float, default=2.0)
    parser.add_argument("--journal", type=Path, default=Path("data/rx_forward_receipts.jsonl"))
    args = parser.parse_args()
    if args.interval <= 0:
        parser.error("--interval must be positive")
    reported: set[str] = set()
    while True:
        status = forward_once(args.rx, args.api,
                              on_forwarded=lambda event_id: append_forward_receipt(args.journal, event_id))
        sync_forward_receipts(args.journal, args.api, reported)
        try:
            _request_json(f"{args.api.rstrip('/')}/api/v1/live/heartbeat",
                          {"name": "rx_http_bridge", "status": status},
                          {"X-SafeSense-Ingress": "rx-http-bridge"})
        except (HTTPError, URLError, TimeoutError, ValueError, OSError) as error:
            print(f"RX bridge heartbeat deferred: {error}", flush=True)
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
