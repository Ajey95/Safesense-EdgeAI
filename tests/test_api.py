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


def test_bmp280_telemetry_keeps_missing_humidity_and_uncalibrated_gas_explicit():
    event = payload()
    event["environment"]["humidity_pct"] = None
    event["environment"]["pressure_pa"] = 100653.25
    event["environment"]["gas_adc_raw"] = 0
    event["environment"]["gas_risk"] = "UNAVAILABLE"
    with TestClient(app) as client:
        response = client.post("/api/v1/telemetry", json=event)
        overview = client.get("/api/v1/overview")
    assert response.status_code == 202
    assert response.json()["fusion_state"] == "DEGRADED"
    stored = next(item for item in overview.json()["telemetry"] if item["payload"]["event_id"] == event["event_id"])
    assert stored["payload"]["environment"]["humidity_pct"] is None
    assert stored["payload"]["environment"]["gas_adc_raw"] == 0


def test_overview_exposes_persisted_http_receipt_without_claiming_device_origin():
    event = payload()
    event["firmware_version"] = "looks-like-a-device"
    with TestClient(app) as client:
        response = client.post("/api/v1/telemetry", json=event)
        overview = client.get("/api/v1/overview")
    assert response.status_code == 202
    stored = next(item for item in overview.json()["telemetry"] if item["payload"]["event_id"] == event["event_id"])
    assert stored["event_id"] == event["event_id"]
    assert stored["received_at"]
    assert stored["backend_ingress"] == "HTTP POST"
    assert stored["payload"]["environment"]["temperature_c"] == 25
    assert "device_verified" not in stored


def test_bme680_gas_resistance_and_mq_raw_are_persisted_without_ppm_claim():
    event = payload()
    event["environment"].update({
        "temperature_c": 29.7,
        "humidity_pct": 70.4,
        "pressure_pa": 97341.0,
        "gas_resistance_ohm": 86139.0,
        "gas_valid": True,
        "heat_stable": True,
        "gas_adc_raw": 0,
        "gas_risk": "UNAVAILABLE",
    })
    with TestClient(app) as client:
        response = client.post("/api/v1/telemetry", json=event)
        overview = client.get("/api/v1/overview")
    assert response.status_code == 202
    stored = next(item for item in overview.json()["telemetry"] if item["event_id"] == event["event_id"])
    env = stored["payload"]["environment"]
    assert env["gas_resistance_ohm"] == 86139.0
    assert env["gas_valid"] is True and env["heat_stable"] is True
    assert env["gas_adc_raw"] == 0 and env["gas_risk"] == "UNAVAILABLE"
    assert "ppm" not in env


def test_backend_echoes_event_id_and_stores_rx_reported_http_receipt():
    event = payload()
    event["environment"]["gas_risk"] = "UNAVAILABLE"
    event["communication"] = {
        "tx_rx_transport": "HTTP POST",
        "rx_device_id": "safesense-rx-01",
        "rx_received_uptime_ms": 123456,
        "rx_queue_persisted": True,
    }
    with TestClient(app) as client:
        response = client.post("/api/v1/telemetry", json=event)
        overview = client.get("/api/v1/overview")
    assert response.status_code == 202
    assert response.json()["event_id"] == event["event_id"]
    stored = next(item for item in overview.json()["telemetry"] if item["event_id"] == event["event_id"])
    assert stored["payload"]["communication"]["rx_queue_persisted"] is True


def test_backend_accepts_missing_temperature_only_when_sensor_unhealthy():
    event = payload()
    event["environment"].update({"temperature_c": None, "humidity_pct": None,
                                 "gas_risk": "UNAVAILABLE", "sensor_healthy": False})
    with TestClient(app) as client:
        accepted = client.post("/api/v1/telemetry", json=event)
        event["event_id"] = f"api-test-{uuid4()}"
        event["environment"]["sensor_healthy"] = True
        rejected = client.post("/api/v1/telemetry", json=event)
    assert accepted.status_code == 202
    assert accepted.json()["fusion_state"] == "DEGRADED"
    assert rejected.status_code == 422
