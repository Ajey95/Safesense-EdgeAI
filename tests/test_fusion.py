from datetime import datetime, timezone
from safesense.fusion import evaluate
from safesense.schemas import TelemetryIn


def event(*, risk="NORMAL", activity="VACANT", fresh=True):
    return TelemetryIn.model_validate({"event_id": "event-0001", "device_id": "device-1", "observed_at": datetime.now(timezone.utc), "environment": {"temperature_c": 27, "humidity_pct": 55, "gas_risk": risk, "sensor_healthy": True}, "csi": {"activity": activity, "confidence": .9 if fresh else 0, "packet_rate_hz": 20 if fresh else 0, "rssi_dbm": -50, "is_fresh": fresh}})


def test_critical_environment_creates_incident_even_when_csi_unknown():
    result = evaluate(event(risk="CRITICAL", activity="UNKNOWN", fresh=False))
    assert result.state == "INCIDENT"
    assert result.incident_required is True
    assert result.local_alarm is True


def test_unknown_is_not_vacant_and_is_visible_as_degraded_context():
    result = evaluate(event(activity="UNKNOWN", fresh=False))
    assert result.state == "DEGRADED"
    assert result.reason_code == "CSI_STALE"


def test_unavailable_environmental_risk_fails_closed():
    result = evaluate(event(risk="UNAVAILABLE", activity="VACANT", fresh=True))
    assert result.state == "DEGRADED"
    assert result.reason_code == "ENVIRONMENT_UNAVAILABLE"
