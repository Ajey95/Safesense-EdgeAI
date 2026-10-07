from datetime import datetime, timezone
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from safesense.database import Base, get_session
from safesense.main import app


def _telemetry(event_id: str, *, simulated: bool = False) -> dict:
    return {
        "event_id": event_id,
        "device_id": "safesense-tx-01" if not simulated else "safesense-synthetic-tx",
        "firmware_version": "synthetic-forecast-demo" if simulated else None,
        "observed_at": None,
        "environment": {
            "temperature_c": 28.6, "humidity_pct": 61.2, "pressure_pa": 97382,
            "gas_resistance_ohm": 13200, "gas_valid": True, "heat_stable": True,
            "gas_adc_raw": 427, "gas_risk": "UNAVAILABLE", "sensor_healthy": True,
        },
        "csi": {
            "activity": "UNKNOWN", "confidence": 0, "quality": "UNAVAILABLE",
            "tx_node": "ONLINE", "rx_node": "ONLINE", "packet_rate_hz": 0,
            "rssi_dbm": -127, "is_fresh": False,
        },
        "communication": {
            "tx_rx_transport": "HTTP POST", "rx_device_id": "safesense-rx-01",
            "rx_received_uptime_ms": 44521, "rx_queue_persisted": True,
            "tx_sequence": 71,
        },
    }


@pytest.fixture
def client(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'live-test.db'}",
                           connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    sessions = sessionmaker(bind=engine)

    def test_session():
        with sessions() as session:
            yield session

    app.dependency_overrides[get_session] = test_session
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.pop(get_session, None)
        engine.dispose()


def test_live_view_joins_real_wifi_and_bluetooth_receipts_by_exact_id(client):
    event_id = f"tx-{uuid4().hex}"
    assert client.post("/api/v1/telemetry", json=_telemetry(event_id),
                       headers={"X-SafeSense-Ingress": "rx-http-bridge"}).status_code == 202
    receipt = {"event_id": event_id, "kind": "RX_FORWARD_ACKED"}
    rx_headers = {"X-SafeSense-Ingress": "rx-http-bridge"}
    bt_headers = {"X-SafeSense-Ingress": "bt-alert-receiver"}
    assert client.post("/api/v1/live/receipts", json=receipt, headers=rx_headers).status_code == 202
    assert client.post("/api/v1/live/receipts", json=receipt, headers=rx_headers).json()["duplicate"] is True
    assert client.post("/api/v1/live/receipts", json={
        "event_id": event_id, "kind": "BLUETOOTH_STORED", "room": "cold storage",
        "channel": "temperature", "horizon_minutes": 15,
        "simulated": False,
        "stored_at_utc": datetime.now(timezone.utc).isoformat(),
    }, headers=bt_headers).status_code == 202
    data = client.get("/api/v1/live").json()
    row = next(item for item in data["events"] if item["event_id"] == event_id)
    assert data["latest_fresh"] is True
    assert row["sequence"] == 71
    assert row["environment"]["gas_adc_raw"] == 427
    assert row["rx_queue_persisted"] is True
    assert row["backend_stored_at"] and row["rx_forward_acked_at"] and row["bluetooth_stored_at"]


def test_live_view_excludes_serial_synthetic_replay_and_keeps_bt_only_receipt(client):
    simulated_id = f"tx-{uuid4().hex}"
    bt_id = f"tx-{uuid4().hex}"
    assert client.post("/api/v1/telemetry", json=_telemetry(simulated_id, simulated=True),
                       headers={"X-SafeSense-Ingress": "rx-http-bridge"}).status_code == 202
    assert client.post("/api/v1/live/receipts", json={
        "event_id": bt_id, "kind": "BLUETOOTH_STORED",
        "room": "laboratory", "channel": "temperature", "horizon_minutes": 10,
        "simulated": False,
    }, headers={"X-SafeSense-Ingress": "bt-alert-receiver"}).status_code == 202
    data = client.get("/api/v1/live").json()
    assert all(row["event_id"] != simulated_id for row in data["events"])
    assert any(row["event_id"] == bt_id for row in data["bluetooth_only"])


def test_generic_api_post_cannot_appear_as_physical_reading(client):
    event_id = f"tx-{uuid4().hex}"
    assert client.post("/api/v1/telemetry", json=_telemetry(event_id)).status_code == 202
    assert client.get("/api/v1/live").json()["events"] == []


def test_transport_receipt_rejects_mismatched_reporter(client):
    response = client.post("/api/v1/live/receipts", json={
        "event_id": f"tx-{uuid4().hex}", "kind": "BLUETOOTH_STORED", "simulated": False,
    }, headers={"X-SafeSense-Ingress": "rx-http-bridge"})
    assert response.status_code == 403


def test_synthetic_bluetooth_receipt_is_not_physical_evidence(client):
    event_id = f"tx-{uuid4().hex}"
    assert client.post("/api/v1/live/receipts", json={
        "event_id": event_id, "kind": "BLUETOOTH_STORED", "simulated": True,
    }, headers={"X-SafeSense-Ingress": "bt-alert-receiver"}).status_code == 202
    assert all(item["event_id"] != event_id for item in client.get("/api/v1/live").json()["bluetooth_only"])


def test_direct_laptop_route_requires_receiver_ingress_and_labels_test_alert(client):
    physical_id = f"tx-{uuid4().hex}"
    test_id = f"tx-{uuid4().hex}"
    physical = _telemetry(physical_id)
    physical["communication"] = None
    physical["firmware_version"] = "direct-wifi-bme680-mq135"
    physical["csi"]["rx_node"] = "UNKNOWN"
    test_alert = _telemetry(test_id, simulated=True)
    test_alert["communication"] = None
    for item in (physical, test_alert):
        assert client.post("/api/v1/telemetry", json=item,
                           headers={"X-SafeSense-Ingress": "direct-laptop-receiver"}).status_code == 202
    rows = client.get("/api/v1/live/direct").json()["events"]
    assert next(row for row in rows if row["event_id"] == physical_id)["test_alert"] is False
    assert next(row for row in rows if row["event_id"] == test_id)["test_alert"] is True
    assert all(row["event_id"] != physical_id for row in client.get("/api/v1/live").json()["events"])


def test_bluetooth_sensor_ingress_is_a_physical_reading_with_its_own_route(client):
    event_id = f"tx-{uuid4().hex}"
    sample = _telemetry(event_id)
    sample["communication"] = None
    sample["firmware_version"] = "direct-wifi-bme680-mq135"
    sample["csi"]["rx_node"] = "UNKNOWN"
    assert client.post("/api/v1/telemetry", json=sample,
                       headers={"X-SafeSense-Ingress": "bt-sensor-receiver"}).status_code == 202
    rows = client.get("/api/v1/live/direct").json()["events"]
    reading = next(row for row in rows if row["event_id"] == event_id)
    assert reading["route"] == "DIRECT_BLUETOOTH"
    assert reading["environment"]["temperature_c"] == 28.6
    assert reading["environment"]["gas_adc_raw"] == 427
