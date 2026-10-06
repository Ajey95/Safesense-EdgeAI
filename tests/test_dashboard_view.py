from datetime import datetime, timedelta, timezone

from safesense.dashboard_view import build_dashboard_view, render_section_html


NOW = datetime(2026, 9, 23, 12, 0, tzinfo=timezone.utc)


def _stored_event():
    return {
        "event_id": "tx-12345678",
        "device_id": "safesense-tx-01",
        "observed_at": NOW.isoformat(),
        "received_at": NOW.isoformat(),
        "backend_ingress": "HTTP POST",
        "fusion_state": "DEGRADED",
        "payload": {
            "firmware_version": "device-looking-name",
            "environment": {"temperature_c": 30.5, "humidity_pct": 67.2, "pressure_pa": 97380,
                            "gas_adc_raw": 0, "gas_risk": "UNAVAILABLE", "sensor_healthy": True},
            "csi": {"activity": "UNKNOWN", "confidence": 0, "quality": "UNAVAILABLE",
                    "tx_node": "UNKNOWN", "rx_node": "UNKNOWN", "packet_rate_hz": 0,
                    "rssi_dbm": -127, "is_fresh": False},
            "system": {"local_storage": "UNKNOWN", "esp32_status": "UNKNOWN"},
        },
    }


def test_dashboard_shows_server_receipt_but_not_device_proof():
    view = build_dashboard_view(_stored_event(), now=NOW + timedelta(seconds=3))
    assert view["event_id"] == "tx-12345678"
    assert view["received_at"] == NOW.isoformat()
    assert view["data_source"] == "UNVERIFIED"
    evidence = dict(view["sections"]["COMMUNICATION EVIDENCE"])
    assert evidence["Backend ingress"] == "HTTP POST"
    assert evidence["TX to RX"] == "UNVERIFIED"
    assert evidence["Device origin"] == "UNVERIFIED"
    assert "HOST VERIFIED" not in str(view)


def test_old_report_is_marked_stale_even_if_payload_says_online():
    event = _stored_event()
    event["payload"]["system"]["esp32_status"] = "ONLINE"
    view = build_dashboard_view(event, now=NOW + timedelta(minutes=2))
    assert view["telemetry_fresh"] is False
    assert view["overall_status"] == "STALE DATA"
    assert dict(view["sections"]["SYSTEM"])["ESP32 Status"] == "UNKNOWN (STALE)"


def test_gas_validity_requires_a_positive_resistance_value():
    event = _stored_event()
    event["payload"]["environment"].update({"gas_valid": True, "heat_stable": True,
                                             "gas_resistance_ohm": None})
    view = build_dashboard_view(event, now=NOW + timedelta(seconds=3))
    environment = dict(view["sections"]["ENVIRONMENT"])
    assert environment["BME680 Gas Resistance"] == "UNAVAILABLE"
    assert environment["BME680 Gas Measurement"] == "UNAVAILABLE"


def test_section_html_escapes_untrusted_values():
    rendered = render_section_html("SYSTEM", [("Device", '<script>alert("x")</script>')])
    assert "<script>" not in rendered
    assert "&lt;script&gt;" in rendered


def test_dashboard_labels_rx_http_receipt_as_reported_not_authenticated():
    event = _stored_event()
    event["payload"]["communication"] = {
        "tx_rx_transport": "HTTP POST",
        "rx_device_id": "safesense-rx-01",
        "rx_received_uptime_ms": 123456,
        "rx_queue_persisted": True,
    }
    view = build_dashboard_view(event, now=NOW + timedelta(seconds=2))
    evidence = dict(view["sections"]["COMMUNICATION EVIDENCE"])
    assert evidence["TX to RX"] == "RX REPORTED HTTP POST"
    assert evidence["RX NVS"] == "RX REPORTED PERSISTED"
    assert evidence["Device origin"] == "UNVERIFIED"


def test_dashboard_marks_zero_mq_adc_and_missing_actuator_evidence_unverified():
    view = build_dashboard_view(_stored_event(), now=NOW + timedelta(seconds=2))
    environment = dict(view["sections"]["ENVIRONMENT"])
    system = dict(view["sections"]["SYSTEM"])
    assert environment["MQ-135 Raw ADC"] == "0"
    assert environment["MQ-135 Signal"] == "UNVERIFIED (ADC ZERO)"
    assert system["NVS Queue"] == "UNAVAILABLE"
    assert system["CSI Queue Drops"] == "UNAVAILABLE"
    assert system["Buzzer"] == "UNKNOWN"
    assert system["LED Output"] == "UNKNOWN"


def test_live_csi_packets_do_not_imply_activity_confidence():
    event = _stored_event()
    event["payload"]["csi"].update({"is_fresh": True, "packet_rate_hz": 100.0,
                                      "rssi_dbm": -50, "window_ready": True,
                                      "activity": "UNKNOWN", "confidence": 0})
    view = build_dashboard_view(event, now=NOW + timedelta(seconds=2))
    context = dict(view["sections"]["HUMAN CONTEXT"])
    assert context["Current Activity"] == "UNKNOWN"
    assert context["Confidence"] == "UNAVAILABLE"
    assert context["Context Freshness"] == "CSI FRESH / ACTIVITY UNKNOWN"
