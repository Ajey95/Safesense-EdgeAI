import json
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

from scripts.rx_http_bridge import append_forward_receipt, convert_rx_event, forward_once, sync_forward_receipts


def pending_event(*, healthy=True, adc=0):
    return {
        "event_id": "tx-0123456789abcdef",
        "tx": {
            "schema_version": 1,
            "event_id": "tx-0123456789abcdef",
            "tx_device_id": "safesense-tx-01",
            "sequence": 12,
            "observed_at": None,
            "bme680": {
                "sensor_healthy": healthy,
                "temperature_c": 29.8 if healthy else None,
                "humidity_pct": 72.0 if healthy else None,
                "pressure_pa": 97368.0 if healthy else None,
                "gas_resistance_ohm": 29142.0 if healthy else None,
                "gas_valid": healthy,
                "heat_stable": healthy,
            },
            "mq135": {"adc_raw": adc, "calibrated": False},
            "gas_risk": "UNAVAILABLE",
        },
        "rx": {
            "device_id": "safesense-rx-01",
            "received_uptime_ms": 123456,
            "seen_age_ms": 1200,
            "queue_persisted": True,
            "transport": "HTTP POST",
            "csi_frames": 120,
            "csi_rssi_dbm": -55,
            "csi_packet_rate_hz": 48.0,
            "csi_windows": 2,
            "csi_min_measured_subcarriers": 47,
        },
    }


def test_bridge_preserves_real_sensor_values_and_unavailable_risk():
    converted = convert_rx_event(pending_event())
    assert converted["event_id"] == "tx-0123456789abcdef"
    assert converted["device_id"] == "safesense-tx-01"
    assert converted["environment"]["temperature_c"] == 29.8
    assert converted["environment"]["gas_resistance_ohm"] == 29142.0
    assert converted["environment"]["gas_adc_raw"] == 0
    assert converted["environment"]["gas_risk"] == "UNAVAILABLE"
    assert converted["csi"]["activity"] == "UNKNOWN"
    assert converted["csi"]["is_fresh"] is True
    assert converted["csi"]["window_ready"] is True
    assert converted["csi"]["window_frames"] == 100
    assert converted["csi"]["selected_subcarriers"] == 47
    assert converted["communication"]["tx_rx_transport"] == "HTTP POST"
    assert converted["communication"]["rx_queue_persisted"] is True


def test_bridge_does_not_invent_temperature_or_csi_when_sensor_missing():
    pending = pending_event(healthy=False, adc=None)
    pending["rx"].update({"csi_frames": 0, "csi_rssi_dbm": None,
                          "csi_packet_rate_hz": 0, "seen_age_ms": 30000})
    converted = convert_rx_event(pending)
    assert converted["environment"]["temperature_c"] is None
    assert converted["environment"]["gas_adc_raw"] is None
    assert converted["environment"]["sensor_healthy"] is False
    assert converted["csi"]["is_fresh"] is False
    assert converted["csi"]["quality"] == "UNAVAILABLE"


def test_bridge_handles_rx_with_no_csi_packets_or_receipt_timestamp():
    pending = pending_event()
    pending["rx"].update({"csi_frames": 0, "csi_rssi_dbm": None,
                          "csi_packet_rate_hz": 0, "seen_age_ms": None,
                          "received_uptime_ms": None})
    converted = convert_rx_event(pending)
    assert converted["csi"]["is_fresh"] is False
    assert converted["csi"]["rssi_dbm"] == -127
    assert converted["communication"]["rx_received_uptime_ms"] is None


def test_bridge_does_not_invent_heater_stability_for_legacy_v1_record():
    pending = pending_event()
    del pending["tx"]["bme680"]["heat_stable"]
    converted = convert_rx_event(pending)
    assert converted["environment"]["heat_stable"] is False
    assert converted["environment"]["gas_valid"] is False
    assert converted["environment"]["gas_resistance_ohm"] == 29142.0


@contextmanager
def servers(*, backend_event_id=None, backend_status=202):
    state = {"posted": [], "acked": [], "api_ingress": []}
    expected = pending_event()

    class RxHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            body = json.dumps(expected).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            body = self.rfile.read(int(self.headers["Content-Length"]))
            ack = json.loads(body)
            state["acked"].append(ack)
            response = json.dumps({"event_id": ack["event_id"], "status": "ACKED"}).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(response)))
            self.end_headers()
            self.wfile.write(response)

        def log_message(self, *_):
            pass

    class ApiHandler(BaseHTTPRequestHandler):
        def do_POST(self):
            body = self.rfile.read(int(self.headers["Content-Length"]))
            state["posted"].append(json.loads(body))
            state["api_ingress"].append(self.headers.get("X-SafeSense-Ingress"))
            response = json.dumps({"event_id": backend_event_id or expected["event_id"],
                                   "accepted": True}).encode()
            self.send_response(backend_status)
            self.send_header("Content-Length", str(len(response)))
            self.end_headers()
            self.wfile.write(response)

        def log_message(self, *_):
            pass

    rx = ThreadingHTTPServer(("127.0.0.1", 0), RxHandler)
    api = ThreadingHTTPServer(("127.0.0.1", 0), ApiHandler)
    threads = [Thread(target=server.serve_forever, daemon=True) for server in (rx, api)]
    for thread in threads:
        thread.start()
    try:
        yield (f"http://127.0.0.1:{rx.server_port}",
               f"http://127.0.0.1:{api.server_port}", state)
    finally:
        for server in (rx, api):
            server.shutdown()
            server.server_close()
        for thread in threads:
            thread.join()


def test_bridge_acknowledges_rx_only_after_matching_backend_acceptance():
    with servers() as (rx, api, state):
        assert forward_once(rx, api) == "forwarded"
    assert len(state["posted"]) == 1
    assert state["posted"][0]["event_id"] == "tx-0123456789abcdef"
    assert state["api_ingress"] == ["rx-http-bridge"]
    assert state["acked"] == [{"event_id": "tx-0123456789abcdef"}]


def test_bridge_leaves_rx_queued_on_wrong_backend_id_or_failure():
    with servers(backend_event_id="tx-wrong") as (rx, api, state):
        assert forward_once(rx, api) == "deferred"
    assert state["acked"] == []
    with servers(backend_status=503) as (rx, api, state):
        assert forward_once(rx, api) == "deferred"
    assert state["acked"] == []


def test_receipt_sync_is_bounded_so_rx_polling_can_continue(tmp_path, monkeypatch):
    import scripts.rx_http_bridge as bridge

    journal = tmp_path / "forward.jsonl"
    for index in range(12):
        append_forward_receipt(journal, f"tx-{index:08d}")
    sent = []

    def accepted(url, payload=None, headers=None):
        sent.append(payload["event_id"])
        return {"accepted": True, "event_id": payload["event_id"]}

    monkeypatch.setattr(bridge, "_request_json", accepted)
    reported = set()
    sync_forward_receipts(journal, "http://127.0.0.1:8000", reported)
    assert len(sent) == len(reported) == 5
