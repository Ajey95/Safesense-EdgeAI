import json
import sqlite3
import threading
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
