"""Receive a classic ESP32's Wi-Fi events on the laptop, then sync to SafeSense.

The HTTP ACK means the exact event ID and payload were committed to local
SQLite. Backend ingestion and speech are separate outcomes.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import json
import re
import socket
import sqlite3
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from safesense.schemas import TelemetryIn


DISCOVERY = b"SAFESENSE_LAPTOP_V1"
EVENT_ID = re.compile(r"^[A-Za-z0-9_.:-]{8,63}$")
ROOMS = ("cold storage", "laboratory", "classroom", "bakery", "server room")
CHANNELS = ("temperature", "humidity", "pressure", "BME680 gas response", "MQ-135 raw response")


def convert_tx_event(tx: dict) -> tuple[TelemetryIn, dict | None]:
    if (tx.get("schema_version") != 1 or
            not EVENT_ID.fullmatch(str(tx.get("event_id", "")))):
        raise ValueError("invalid TX event header")
    bme, mq = tx["bme680"], tx["mq135"]
    simulated = tx.get("simulated") is True
    alert = tx.get("forecast_alert")
    if alert is not None:
        room = alert["room"]
        horizon = alert["horizon_minutes"]
        channel = alert["channel"]
        if (not isinstance(room, int) or isinstance(room, bool) or not 0 <= room < 5
                or not isinstance(horizon, int) or isinstance(horizon, bool)
                or horizon not in (5, 10, 15, 20, 25, 30)
                or not isinstance(channel, int) or isinstance(channel, bool)
                or not 0 <= channel < 5):
            raise ValueError("invalid forecast alert metadata")
    telemetry = TelemetryIn.model_validate({
        "event_id": tx["event_id"], "device_id": tx["tx_device_id"],
        "observed_at": tx.get("observed_at"),
        "firmware_version": "synthetic-forecast-demo" if simulated else "direct-wifi-bme680-mq135",
        "environment": {
            "temperature_c": bme["temperature_c"], "humidity_pct": bme["humidity_pct"],
            "pressure_pa": bme["pressure_pa"],
            "gas_resistance_ohm": bme["gas_resistance_ohm"],
            "gas_valid": bme["gas_valid"] and bme["heat_stable"],
            "heat_stable": bme["heat_stable"],
            "gas_adc_raw": mq["adc_raw"], "gas_risk": tx["gas_risk"],
            "sensor_healthy": bme["sensor_healthy"],
        },
        "csi": {"activity": "UNKNOWN", "confidence": 0, "quality": "UNAVAILABLE",
                "tx_node": "ONLINE", "rx_node": "UNKNOWN", "packet_rate_hz": 0,
                "rssi_dbm": -127, "is_fresh": False},
        "system": {"local_storage": "OK", "esp32_status": "ONLINE"},
    })
    return telemetry, alert


class Receiver:
    def __init__(self, database: Path, api: str,
                 ingress: str = "direct-laptop-receiver"):
        database.parent.mkdir(parents=True, exist_ok=True)
        self.database = database
        self.api = api.rstrip("/")
        self.ingress = ingress
        self.lock = threading.Lock()
        self.wifi_fault = False
        with self._connection() as db:
            db.execute("CREATE TABLE IF NOT EXISTS events (event_id TEXT PRIMARY KEY, payload TEXT NOT NULL, backend_stored INTEGER NOT NULL DEFAULT 0)")

    @contextmanager
    def _connection(self):
        db = sqlite3.connect(self.database, timeout=5)
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA synchronous=FULL")
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def accept(self, tx: dict, speak_alert: bool = True) -> tuple[str, bool]:
        telemetry, alert = convert_tx_event(tx)
        event_id = telemetry.event_id
        raw = json.dumps(tx, sort_keys=True, separators=(",", ":"))
        with self.lock, self._connection() as db:
            existing = db.execute("SELECT payload FROM events WHERE event_id=?", (event_id,)).fetchone()
            if existing and existing[0] != raw:
                raise ValueError("event ID was reused with different data")
            if not existing:
                db.execute("INSERT INTO events (event_id,payload) VALUES (?,?)", (event_id, raw))
        if not existing and alert is not None and speak_alert:
            from scripts.bt_alert_receiver import speak
            try:
                speak({"room": ROOMS[alert["room"]], "channel": CHANNELS[alert["channel"]],
                       "horizon_minutes": alert["horizon_minutes"]})
            except OSError as error:
                print(f"voice attempt unavailable for {event_id}: {error}", flush=True)
        return event_id, existing is not None

    def sync_once(self) -> int:
        with self._connection() as db:
            rows = db.execute("SELECT event_id,payload FROM events WHERE backend_stored=0 ORDER BY rowid LIMIT 8").fetchall()
        synced = 0
        for event_id, payload in rows:
            tx = json.loads(payload)
            telemetry, _ = convert_tx_event(tx)
            body = telemetry.model_dump_json().encode("utf-8")
            request = Request(f"{self.api}/api/v1/telemetry", data=body,
                              headers={"Content-Type": "application/json",
                                       "X-SafeSense-Ingress": self.ingress})
            try:
                with urlopen(request, timeout=5) as response:
                    result = json.load(response)
                if result.get("accepted") is not True or result.get("event_id") != event_id:
                    break
            except (HTTPError, URLError, TimeoutError, OSError, ValueError) as error:
                print(f"backend sync deferred for {event_id}: {error}", flush=True)
                break
            with self._connection() as db:
                db.execute("UPDATE events SET backend_stored=1 WHERE event_id=?", (event_id,))
            synced += 1
        return synced

    def counts(self) -> dict:
        with self._connection() as db:
            total, pending = db.execute(
                "SELECT COUNT(*), SUM(CASE WHEN backend_stored=0 THEN 1 ELSE 0 END) FROM events"
            ).fetchone()
        return {"wifi_fault": self.wifi_fault, "laptop_stored": total,
                "backend_pending": pending or 0}


def handler_for(receiver: Receiver):
    class Handler(BaseHTTPRequestHandler):
        def _json(self, code: int, payload: dict):
            body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path == "/status" and self.client_address[0] == "127.0.0.1":
                self._json(200, receiver.counts())
            else:
                self._json(404, {"error": "not found"})

        def do_POST(self):
            if self.path == "/test-alert":
                if (self.client_address[0] != "127.0.0.1" or
                        self.headers.get("X-SafeSense-Control") != "dashboard"):
                    self._json(403, {"error": "local control only"})
                    return
                try:
                    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                        sock.connect(("192.168.4.1", 3334))
                        if not sock.getsockname()[0].startswith("192.168.4."):
                            self._json(409, {"error": "Connect laptop Wi-Fi to SafeSense-TX-Laptop before requesting a Wi-Fi test alert"})
                            return
                        sock.send(b"SAFESENSE_TEST_ALERT_V1")
                except OSError as error:
                    self._json(503, {"error": str(error)})
                    return
                self._json(202, {"accepted": True, "test_alert": "requested"})
                return
            if self.path == "/fault":
                if (self.client_address[0] != "127.0.0.1" or
                        self.headers.get("X-SafeSense-Control") != "dashboard"):
                    self._json(403, {"error": "local control only"})
                    return
                try:
                    size = int(self.headers.get("Content-Length", "0"))
                    if not 1 <= size <= 64:
                        raise ValueError("invalid body size")
                    value = json.loads(self.rfile.read(size))
                    if type(value.get("enabled")) is not bool:
                        raise ValueError("enabled must be a boolean")
                    receiver.wifi_fault = value["enabled"]
                except (ValueError, TypeError, KeyError, json.JSONDecodeError):
                    self._json(400, {"error": "invalid fault control"})
                    return
                self._json(200, receiver.counts())
                return
            if self.path != "/api/v1/tx/environment":
                self._json(404, {"error": "not found"})
                return
            if not (self.client_address[0].startswith("192.168.4.") or
                    self.client_address[0] == "127.0.0.1"):
                self._json(403, {"error": "outside the direct device network"})
                return
            if receiver.wifi_fault:
                self._json(503, {"error": "Wi-Fi receiver fault injected"})
                return
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not 1 <= size <= 2048:
                    raise ValueError("invalid body size")
                tx = json.loads(self.rfile.read(size))
                event_id, duplicate = receiver.accept(tx)
            except (ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
                self._json(400, {"error": str(error)})
                return
            print(f"Wi-Fi laptop stored {event_id} duplicate={duplicate}", flush=True)
            self._json(202, {"event_id": event_id, "status": "ACCEPTED"})

    return Handler


def discovery_loop(stop: threading.Event) -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        while not stop.wait(2):
            try:
                sock.sendto(DISCOVERY, ("192.168.4.1", 3334))
            except OSError:
                continue


def main() -> None:
    parser = argparse.ArgumentParser(description="SafeSense direct ESP32 Wi-Fi laptop receiver")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--database", type=Path, default=Path("data/live/direct_laptop.db"))
    parser.add_argument("--api", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    receiver = Receiver(args.database, args.api)
    stop = threading.Event()
    threading.Thread(target=discovery_loop, args=(stop,), daemon=True).start()

    def sync_loop():
        while not stop.wait(2):
            receiver.sync_once()

    threading.Thread(target=sync_loop, daemon=True).start()
    with ThreadingHTTPServer(("0.0.0.0", args.port), handler_for(receiver)) as server:
        print(f"Direct laptop receiver listening on port {args.port}", flush=True)
        try:
            server.serve_forever(poll_interval=0.5)
        finally:
            stop.set()


if __name__ == "__main__":
    main()
