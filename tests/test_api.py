from datetime import datetime, timezone
from uuid import uuid4
from fastapi.testclient import TestClient
from safesense.main import app


def payload():
    return {
        "event_id": f"api-test-{uuid4()}",
        "device_id": "esp32s3-node2",
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "firmware_version": "esp32s3-v2",
        "environment": {
            "temperature_c": 25.0,
            "humidity_pct": 50.0,
            "pressure_pa": 100900,
            "gas_resistance_ohm": 52000,
            "gas_baseline_ohm": 110000,
            "gas_ratio": 0.473,
            "gas_risk": "CRITICAL",
            "gas_valid": True,
            "heat_stable": True,
            "sensor_healthy": True,
            "is_fresh": True,
        },
        "csi": {
            "activity": "UNKNOWN",
            "confidence": 0,
            "quality": "UNAVAILABLE",
            "tx_node": "ONLINE",
            "rx_node": "ONLINE",
            "packet_rate_hz": 0,
            "rssi_dbm": -50,
            "is_fresh": False,
            "window_ready": False,
            "model_release_state": "DISABLED_RELEASE_GATE",
        },
        "system": {
            "mqtt": "CONNECTED",
            "local_storage": "OK",
            "node1_status": "ONLINE",
            "node2_status": "ONLINE",
            "output_state": "INCIDENT",
            "green_led": False,
            "yellow_led": False,
            "red_led": True,
            "buzzer_on": True,
            "queue_depth": 1,
            "csi_drops": 0,
        },
    }


def test_ingestion_is_idempotent_and_preserves_critical_incident():
    event = payload()
    with TestClient(app) as client:
        first = client.post("/api/v1/telemetry", json=event)
        second = client.post("/api/v1/telemetry", json=event)
    assert first.status_code == 202
    assert first.json()["event_id"] == event["event_id"]
    assert first.json()["status"] == "ACCEPTED"
    assert first.json()["fusion_state"] == "INCIDENT"
    assert first.json()["incident_id"]
    assert second.json()["duplicate"] is True
    assert second.json()["event_id"] == event["event_id"]
    assert second.json()["status"] == "ACCEPTED"


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
    assert stored["payload"]["environment"]["gas_resistance_ohm"] == 52000
    assert stored["payload"]["system"]["node1_status"] == "ONLINE"
    assert stored["payload"]["system"]["node2_status"] == "ONLINE"
    assert stored["payload"]["system"]["queue_depth"] == 1


def test_unavailable_bme680_accepts_null_measurements_and_degrades():
    event = payload()
    event["environment"] = {
        "temperature_c": None,
        "humidity_pct": None,
        "pressure_pa": None,
        "gas_resistance_ohm": None,
        "gas_baseline_ohm": None,
        "gas_ratio": None,
        "gas_risk": "UNAVAILABLE",
        "gas_valid": False,
        "heat_stable": False,
        "sensor_healthy": False,
        "is_fresh": True,
    }
    event["system"]["output_state"] = "DEGRADED"
    event["system"]["red_led"] = False
    event["system"]["buzzer_on"] = False
    event["system"]["yellow_led"] = True
    with TestClient(app) as client:
        response = client.post("/api/v1/telemetry", json=event)
    assert response.status_code == 202
    assert response.json()["fusion_state"] == "DEGRADED"
    assert response.json()["status"] == "ACCEPTED"
