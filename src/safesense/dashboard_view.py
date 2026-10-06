from __future__ import annotations

from datetime import datetime, timezone, tzinfo
from html import escape

UNAVAILABLE = "UNAVAILABLE"
TELEMETRY_STALE_SECONDS = 15


def incident_display(incidents: list[dict], limit: int = 3) -> tuple[list[dict], int]:
    """Return the newest active incidents without turning the page into an alert log."""
    if limit < 1:
        raise ValueError("incident display limit must be positive")
    active = [incident for incident in incidents if incident.get("state") == "NEW"]
    return active[:limit], max(0, len(active) - limit)


def tone(value: str) -> str:
    normalized = value.upper()
    if normalized in {"SAFE", "NORMAL", "GOOD", "ONLINE", "CONNECTED", "OK", "VALID / STABLE", "HOST VERIFIED", "LIVE"}:
        return "good"
    if normalized in {"WARNING", "FAIR", "STATIONARY", "YELLOW", "PENDING DEVICE TEST", "ACTIVE"}:
        return "warning"
    if normalized in {"DANGER", "CRITICAL", "POOR", "OFFLINE", "DISCONNECTED", "INCIDENT", "RED", "CONFIGURATION ERROR"}:
        return "danger"
    return "unknown"


def _number(value, suffix: str, decimals: int = 0, thousands: bool = False) -> str:
    if value is None:
        return UNAVAILABLE
    number = float(value)
    formatted = f"{number:,.{decimals}f}" if thousands else f"{number:.{decimals}f}"
    return f"{formatted} {suffix}".strip()


def _led_output(system: dict) -> str:
    if not any(key in system for key in ("green_led", "yellow_led", "red_led")):
        return "UNKNOWN"
    enabled = [name for name, active in (
        ("GREEN", system.get("green_led")),
        ("YELLOW", system.get("yellow_led")),
        ("RED", system.get("red_led")),
    ) if active]
    if len(enabled) > 1:
        return "CONFIGURATION ERROR"
    return enabled[0] if enabled else "OFF"


def _parse_utc_timestamp(observed_at: object) -> datetime | None:
    if not isinstance(observed_at, str) or not observed_at:
        return None
    try:
        observed = datetime.fromisoformat(observed_at.replace("Z", "+00:00"))
    except ValueError:
        return None
    if observed.tzinfo is None:
        observed = observed.replace(tzinfo=timezone.utc)
    return observed.astimezone(timezone.utc)


def local_clock(value: object, *, local_timezone: tzinfo | None = None) -> str:
    """Format API timestamps, treating SQLite's offset-free values as UTC."""
    observed = _parse_utc_timestamp(value)
    if observed is None:
        return "--:--:--" if value in (None, "") else str(value)
    display_timezone = local_timezone or datetime.now().astimezone().tzinfo
    return observed.astimezone(display_timezone).strftime("%H:%M:%S")


def _telemetry_age_seconds(observed_at: object, now: datetime) -> float | None:
    observed = _parse_utc_timestamp(observed_at)
    if observed is None:
        return None
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return max(0.0, (now.astimezone(timezone.utc) - observed).total_seconds())


def _age_label(age_seconds: float | None) -> str:
    if age_seconds is None:
        return "AGE UNKNOWN"
    seconds = int(age_seconds)
    if seconds < 60:
        return f"{seconds} sec ago"
    if seconds < 3600:
        return f"{seconds // 60} min ago"
    if seconds < 86400:
        return f"{seconds // 3600} h ago"
    return f"{seconds // 86400} d ago"


def build_dashboard_view(latest: dict, *, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    telemetry_age_seconds = _telemetry_age_seconds(latest.get("observed_at"), now)
    telemetry_fresh = (
        telemetry_age_seconds is not None
        and telemetry_age_seconds <= TELEMETRY_STALE_SECONDS
    )
    payload = latest.get("payload") or {}
    environment = payload.get("environment") or {}
    csi = payload.get("csi") or {}
    system = payload.get("system") or {}
    communication = payload.get("communication") or {}
    fusion_state = str(latest.get("fusion_state") or "DEGRADED")
    model_release = str(csi.get("model_release_state") or "UNAVAILABLE").replace("_", " ")
    environment_current = telemetry_fresh and environment.get("sensor_healthy") is not False
    csi_current = telemetry_fresh and bool(csi.get("is_fresh"))
    activity_known = csi_current and csi.get("activity") in {"VACANT", "STATIONARY", "WALKING"}
    stale_status = "UNKNOWN (STALE)"
    gas_measurement = (
        "VALID / STABLE"
        if environment_current and environment.get("gas_valid") and environment.get("heat_stable")
        and isinstance(environment.get("gas_resistance_ohm"), (int, float))
        and environment["gas_resistance_ohm"] > 0
        else UNAVAILABLE
    )
    mq_raw = environment.get("gas_adc_raw") if environment_current else None
    mq_signal = (UNAVAILABLE if mq_raw is None else
                 "UNVERIFIED (ADC ZERO)" if mq_raw == 0 else
                 "RAW ONLY (UNCALIBRATED)")
    sections = {
        "ENVIRONMENT": [
            ("Temperature", _number(environment.get("temperature_c"), "°C", 1) if environment_current else UNAVAILABLE),
            ("Humidity", _number(environment.get("humidity_pct"), "%", 1) if environment_current else UNAVAILABLE),
            ("Pressure", _number(environment.get("pressure_pa"), "Pa", 0, True) if environment_current else UNAVAILABLE),
            ("BME680 Gas Resistance", _number(environment.get("gas_resistance_ohm"), "Ω", 0, True) if environment_current else UNAVAILABLE),
            ("MQ-135 Raw ADC", _number(environment.get("gas_adc_raw"), "", 0) if environment_current else UNAVAILABLE),
            ("MQ-135 Signal", mq_signal),
            ("BME680 Gas Measurement", gas_measurement),
            ("Environmental Risk", str(environment.get("gas_risk") or "UNAVAILABLE") if environment_current else UNAVAILABLE),
            ("Reading Freshness", "FRESH" if environment_current else "STALE / UNAVAILABLE"),
        ],
        "WI-FI CSI": [
            ("TX Node", str(csi.get("tx_node") or "UNKNOWN") if telemetry_fresh else stale_status),
            ("RX Node", str(csi.get("rx_node") or "UNKNOWN") if telemetry_fresh else stale_status),
            ("RSSI", _number(csi.get("rssi_dbm"), "dBm", 0) if csi_current else UNAVAILABLE),
            ("Packet Rate", _number(csi.get("packet_rate_hz"), "packets/s", 1) if csi_current else UNAVAILABLE),
            ("CSI Quality", str(csi.get("quality") or "UNAVAILABLE") if csi_current else UNAVAILABLE),
            ("Window", "READY" if csi_current and csi.get("window_ready") else "NOT READY"),
            ("Model Release", model_release),
        ],
        "HUMAN CONTEXT": [
            ("Current Activity", str(csi.get("activity") or "UNKNOWN") if csi_current else "UNKNOWN"),
            ("Confidence", _number(float(csi.get("confidence") or 0.0) * 100.0, "%", 0) if activity_known else UNAVAILABLE),
            ("Context Freshness", "FRESH" if activity_known else "CSI FRESH / ACTIVITY UNKNOWN" if csi_current else "STALE / UNAVAILABLE"),
        ],
        "SYSTEM": [
            ("Local Storage", str(system.get("local_storage") or "UNKNOWN") if telemetry_fresh else stale_status),
            ("ESP32 Status", str(system.get("esp32_status") or "UNKNOWN") if telemetry_fresh else stale_status),
            ("Node 1 · Sensor/TX", str(system.get("node1_status") or "UNKNOWN") if telemetry_fresh else stale_status),
            ("Node 2 · CSI/Gateway", str(system.get("node2_status") or "UNKNOWN") if telemetry_fresh else stale_status),
            ("Output State", str(system.get("output_state") or fusion_state) if telemetry_fresh else stale_status),
            ("LED Output", _led_output(system) if telemetry_fresh else "UNKNOWN"),
            ("Buzzer", ("ACTIVE" if system.get("buzzer_on") else "OFF") if telemetry_fresh and "buzzer_on" in system else "UNKNOWN"),
            ("NVS Queue", f"{int(system['queue_depth'])} / 16" if telemetry_fresh and system.get("queue_depth") is not None else UNAVAILABLE),
            ("CSI Queue Drops", str(int(system["csi_drops"])) if telemetry_fresh and system.get("csi_drops") is not None else UNAVAILABLE),
        ],
        "COMMUNICATION EVIDENCE": [
            ("Backend ingress", str(latest.get("backend_ingress") or "UNVERIFIED")),
            ("Event ID", str(latest.get("event_id") or "UNAVAILABLE")),
            ("Server received", local_clock(latest.get("received_at"))),
            ("TX to RX", "RX REPORTED HTTP POST" if communication.get("tx_rx_transport") == "HTTP POST" else "UNVERIFIED"),
            ("RX NVS", "RX REPORTED PERSISTED" if communication.get("rx_queue_persisted") is True else "UNVERIFIED"),
            ("Device origin", "UNVERIFIED"),
        ],
    }
    return {
        "overall_status": fusion_state if telemetry_fresh else "STALE DATA",
        "device_id": str(latest.get("device_id") or "NOT REPORTED"),
        "event_id": str(latest.get("event_id") or "UNAVAILABLE"),
        "observed_at": latest.get("observed_at"),
        "received_at": latest.get("received_at"),
        "data_source": "UNVERIFIED",
        "telemetry_fresh": telemetry_fresh,
        "telemetry_age_label": _age_label(telemetry_age_seconds),
        "sections": sections,
    }


def render_section_html(title: str, rows: list[tuple[str, str]]) -> str:
    rendered_rows = "".join(
        f"<div class='status-row'><span class='status-label'>{escape(str(label))}</span>"
        f"<span class='status-value {tone(str(value))}'>{escape(str(value))}</span></div>"
        for label, value in rows
    )
    return f"<section class='review-card'><h2>{escape(title)}</h2>{rendered_rows}</section>"
