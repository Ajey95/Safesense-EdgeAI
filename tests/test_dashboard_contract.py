from safesense.dashboard_view import build_dashboard_view, render_section_html


def latest_payload():
    return {
        "device_id": "esp32s3-node2",
        "observed_at": "2026-09-21T20:00:00+00:00",
        "fusion_state": "WARNING",
        "payload": {
            "environment": {
                "temperature_c": 31.8,
                "humidity_pct": 64.0,
                "pressure_pa": 100920,
                "gas_resistance_ohm": 72000,
                "gas_baseline_ohm": 100000,
                "gas_ratio": 0.72,
                "gas_risk": "WARNING",
                "gas_valid": True,
                "heat_stable": True,
                "sensor_healthy": True,
                "is_fresh": True,
            },
            "csi": {
                "activity": "WALKING",
                "confidence": 0.93,
                "quality": "GOOD",
                "tx_node": "ONLINE",
                "rx_node": "ONLINE",
                "packet_rate_hz": 92,
                "rssi_dbm": -48,
                "is_fresh": True,
                "window_ready": True,
                "model_release_state": "DISABLED_RELEASE_GATE",
            },
            "system": {
                "mqtt": "CONNECTED",
                "local_storage": "OK",
                "node1_status": "ONLINE",
                "node2_status": "ONLINE",
                "output_state": "WARNING",
                "green_led": False,
                "yellow_led": True,
                "red_led": False,
                "buzzer_on": True,
                "queue_depth": 2,
                "csi_drops": 0,
            },
        },
    }


def test_view_contains_every_review_section_and_v2_field():
    view = build_dashboard_view(latest_payload())
    assert list(view["sections"]) == [
        "ENVIRONMENT",
        "WI-FI CSI",
        "HUMAN CONTEXT",
        "SYSTEM",
        "REVIEW EVIDENCE",
    ]
    rows = {label: value for section in view["sections"].values() for label, value in section}
    assert rows["Gas Resistance"] == "72,000 Ω"
    assert rows["Gas Baseline"] == "100,000 Ω"
    assert rows["Gas Ratio"] == "0.720"
    assert rows["Gas Measurement"] == "VALID / STABLE"
    assert rows["Node 1 · Sensor/TX"] == "ONLINE"
    assert rows["Node 2 · CSI/Gateway"] == "ONLINE"
    assert rows["LED Output"] == "YELLOW"
    assert rows["Buzzer"] == "ACTIVE"
    assert rows["NVS Queue"] == "2 / 16"
    assert rows["Model Release"] == "DISABLED RELEASE GATE"
    assert rows["Hardware Verification"] == "PENDING DEVICE TEST"


def test_unavailable_values_are_not_rendered_as_zero_or_safe():
    latest = latest_payload()
    latest["payload"]["environment"] = {
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
        "is_fresh": False,
    }
    latest["fusion_state"] = "DEGRADED"
    view = build_dashboard_view(latest)
    rows = dict(view["sections"]["ENVIRONMENT"])
    assert rows["Temperature"] == "UNAVAILABLE"
    assert rows["Pressure"] == "UNAVAILABLE"
    assert rows["Gas Resistance"] == "UNAVAILABLE"
    assert view["overall_status"] == "DEGRADED"


def test_dynamic_values_are_html_escaped_and_ui_has_no_internal_instructions():
    latest = latest_payload()
    latest["payload"]["csi"]["activity"] = "<script>alert(1)</script>"
    view = build_dashboard_view(latest)
    html = render_section_html("HUMAN CONTEXT", view["sections"]["HUMAN CONTEXT"])
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    visible = " ".join(
        [view["overall_status"], *[str(value) for rows in view["sections"].values() for _, value in rows]]
    ).lower()
    for banned in ("system prompt", "internal instruction", "todo", "menuconfig", "credential"):
        assert banned not in visible
