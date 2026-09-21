from datetime import datetime, timezone
from safesense.fusion import evaluate
from safesense.schemas import TelemetryIn


def event(*, risk="NORMAL", activity="VACANT", csi_fresh=True, environment_fresh=True):
    ratio = {"NORMAL": 1.0, "WARNING": 0.7, "CRITICAL": 0.4, "UNAVAILABLE": None}[risk]
    return TelemetryIn.model_validate({
        "event_id": "event-0001",
        "device_id": "device-1",
        "observed_at": datetime.now(timezone.utc),
        "environment": {
            "temperature_c": 27,
            "humidity_pct": 55,
            "pressure_pa": 100800,
            "gas_resistance_ohm": 100000 if ratio else None,
            "gas_baseline_ohm": 100000 if ratio else None,
            "gas_ratio": ratio,
            "gas_risk": risk,
            "gas_valid": risk != "UNAVAILABLE",
            "heat_stable": risk != "UNAVAILABLE",
            "sensor_healthy": True,
            "is_fresh": environment_fresh,
        },
        "csi": {
            "activity": activity,
            "confidence": .9 if csi_fresh else 0,
            "packet_rate_hz": 20 if csi_fresh else 0,
            "rssi_dbm": -50,
            "is_fresh": csi_fresh,
            "window_ready": csi_fresh,
            "model_release_state": "DISABLED_RELEASE_GATE",
        },
    })


def test_critical_environment_creates_incident_even_when_csi_unknown():
    result = evaluate(event(risk="CRITICAL", activity="UNKNOWN", csi_fresh=False,
                            environment_fresh=False))
    assert result.state == "INCIDENT"
    assert result.incident_required is True
    assert result.local_alarm is True


def test_unknown_is_not_vacant_and_is_visible_as_degraded_context():
    result = evaluate(event(activity="UNKNOWN", csi_fresh=False))
    assert result.state == "DEGRADED"
    assert result.reason_code == "CSI_STALE"


def test_unavailable_environmental_risk_fails_closed():
    result = evaluate(event(risk="UNAVAILABLE", activity="VACANT", csi_fresh=True))
    assert result.state == "DEGRADED"
    assert result.reason_code == "ENVIRONMENT_UNAVAILABLE"


def test_stale_normal_environment_fails_closed_before_csi_context():
    result = evaluate(event(risk="NORMAL", activity="WALKING", csi_fresh=True,
                            environment_fresh=False))
    assert result.state == "DEGRADED"
    assert result.reason_code == "ENVIRONMENT_STALE"
