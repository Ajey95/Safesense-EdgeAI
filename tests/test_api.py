from datetime import datetime, timezone
from uuid import uuid4
from fastapi.testclient import TestClient
from safesense.main import app


def payload():
    return {"event_id": f"api-test-{uuid4()}", "device_id": "device-api", "observed_at": datetime.now(timezone.utc).isoformat(), "environment": {"temperature_c": 25, "humidity_pct": 50, "gas_risk": "CRITICAL", "sensor_healthy": True}, "csi": {"activity": "UNKNOWN", "confidence": 0, "packet_rate_hz": 0, "rssi_dbm": -50, "is_fresh": False}}


def test_ingestion_is_idempotent_and_preserves_critical_incident():
    event = payload()
    with TestClient(app) as client:
        first = client.post("/api/v1/telemetry", json=event)
        second = client.post("/api/v1/telemetry", json=event)
    assert first.status_code == 202
    assert first.json()["fusion_state"] == "INCIDENT"
    assert first.json()["incident_id"]
    assert second.json()["duplicate"] is True


def test_device_without_wall_clock_uses_server_receive_time():
    event = payload()
    event["observed_at"] = None
    event["environment"]["gas_risk"] = "UNAVAILABLE"
    with TestClient(app) as client:
        response = client.post("/api/v1/telemetry", json=event)
        overview = client.get("/api/v1/overview")
    assert response.status_code == 202
    assert response.json()["fusion_state"] == "DEGRADED"
    stored = next(item for item in overview.json()["telemetry"] if item["payload"]["event_id"] == event["event_id"])
    assert stored["observed_at"]
