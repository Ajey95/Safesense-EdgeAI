import json
import sqlite3
import threading
from datetime import datetime, timezone
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import pytest

from scripts.direct_laptop_receiver import Receiver, handler_for


def _tx(event_id="tx-transport-test-001"):
    return {
        "schema_version": 1, "event_id": event_id, "tx_device_id": "safesense-tx-01",
        "sequence": 1, "observed_at": None,
        "bme680": {"sensor_healthy": True, "temperature_c": 23.0,
                   "humidity_pct": 43.0, "pressure_pa": 101300.0,
                   "gas_resistance_ohm": 59000.0, "gas_valid": True,
                   "heat_stable": True},
        "mq135": {"adc_raw": 705, "calibrated": False},
        "gas_risk": "UNAVAILABLE", "simulated": False,
    }


def test_wifi_ack_follows_durable_laptop_storage_and_fault_blocks_it(tmp_path):
    database = tmp_path / "direct.db"
    receiver = Receiver(database, "http://127.0.0.1:1")
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler_for(receiver))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        event = _tx()
        body = json.dumps(event).encode()
        request = Request(f"{base}/api/v1/tx/environment", data=body,
                          headers={"Content-Type": "application/json"})
        with urlopen(request) as response:
            assert response.status == 202
            assert json.load(response) == {"event_id": event["event_id"],
                                           "status": "ACCEPTED"}
        with sqlite3.connect(database) as db:
            assert db.execute("SELECT payload FROM events WHERE event_id=?",
                              (event["event_id"],)).fetchone() is not None
        with urlopen(request) as response:
            assert response.status == 202
        with sqlite3.connect(database) as db:
            assert db.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 1
        fault = Request(f"{base}/fault", data=b'{"enabled":true}',
                        headers={"Content-Type": "application/json",
                                 "X-SafeSense-Control": "dashboard"})
        with urlopen(fault) as response:
            assert json.load(response)["wifi_fault"] is True
        with pytest.raises(HTTPError) as failure:
            urlopen(request)
        assert failure.value.code == 503
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_wireless_receiver_uses_board_uptime_to_date_capture(tmp_path):
    database = tmp_path / "wireless.db"
    receiver = Receiver(database, "http://127.0.0.1:1")
    event = _tx("tx-capture-age-001")
    event["captured_uptime_ms"] = 10_000
    event["transmitted_uptime_ms"] = 12_000
    before = datetime.now(timezone.utc)
    event_id, duplicate = receiver.accept(event, speak_alert=False)
    assert event_id == event["event_id"] and not duplicate
    event["transmitted_uptime_ms"] = 13_000
    assert receiver.accept(event, speak_alert=False) == (event_id, True)
    with sqlite3.connect(database) as db:
        observed, age = db.execute("SELECT observed_at_utc,capture_age_ms FROM events "
                                   "WHERE event_id=?", (event_id,)).fetchone()
    assert age == 2000
    assert 1.9 <= (before - datetime.fromisoformat(observed)).total_seconds() <= 2.1


def test_wifi_board_status_is_journaled_before_receiver_reply(tmp_path):
    database = tmp_path / "direct.db"
    receiver = Receiver(database, "http://127.0.0.1:1")
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler_for(receiver))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    status = {"status_id": "st-0123456789abcdef", "device_id": "safesense-tx-01",
              "sequence": 1, "uptime_ms": 1000, "queue_depth": 1,
              "pending_event_ids": ["tx-queue-test-001"],
              "last_enqueued_id": "tx-queue-test-001", "last_acked_id": "",
              "last_ack_route": "NONE"}
    try:
        request = Request(f"http://127.0.0.1:{server.server_port}/api/v1/tx/status",
                          data=json.dumps(status).encode(),
                          headers={"Content-Type": "application/json"})
        with urlopen(request) as response:
            assert response.status == 202
            assert json.load(response)["status_id"] == status["status_id"]
        with sqlite3.connect(database) as db:
            assert db.execute("SELECT backend_stored,payload FROM board_queue_status "
                              "WHERE status_id=?", (status["status_id"],)).fetchone() == (
                                  0, json.dumps(status, separators=(",", ":")))
        invalid = {**status, "status_id": "st-fedcba9876543210", "queue_depth": 0}
        invalid_request = Request(f"http://127.0.0.1:{server.server_port}/api/v1/tx/status",
                                  data=json.dumps(invalid).encode())
        with pytest.raises(HTTPError) as rejected:
            urlopen(invalid_request)
        assert rejected.value.code == 400
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
