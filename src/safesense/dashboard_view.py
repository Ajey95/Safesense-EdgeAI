from __future__ import annotations

from html import escape

UNAVAILABLE = "UNAVAILABLE"


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
    enabled = [name for name, active in (
        ("GREEN", system.get("green_led")),
        ("YELLOW", system.get("yellow_led")),
        ("RED", system.get("red_led")),
    ) if active]
    if len(enabled) > 1:
        return "CONFIGURATION ERROR"
    return enabled[0] if enabled else "OFF"


def build_dashboard_view(latest: dict) -> dict:
    payload = latest.get("payload") or {}
    environment = payload.get("environment") or {}
    csi = payload.get("csi") or {}
    system = payload.get("system") or {}
    fusion_state = str(latest.get("fusion_state") or "DEGRADED")
    model_release = str(csi.get("model_release_state") or "UNAVAILABLE").replace("_", " ")
    gas_measurement = "VALID / STABLE" if environment.get("gas_valid") and environment.get("heat_stable") else UNAVAILABLE
    sections = {
        "ENVIRONMENT": [
            ("Temperature", _number(environment.get("temperature_c"), "°C", 1)),
            ("Humidity", _number(environment.get("humidity_pct"), "%", 1)),
            ("Pressure", _number(environment.get("pressure_pa"), "Pa", 0, True)),
            ("Gas Resistance", _number(environment.get("gas_resistance_ohm"), "Ω", 0, True)),
            ("Gas Baseline", _number(environment.get("gas_baseline_ohm"), "Ω", 0, True)),
            ("Gas Ratio", UNAVAILABLE if environment.get("gas_ratio") is None else f"{float(environment['gas_ratio']):.3f}"),
            ("Gas Measurement", gas_measurement),
            ("Environmental Risk", str(environment.get("gas_risk") or "UNAVAILABLE")),
            ("Reading Freshness", "FRESH" if environment.get("is_fresh") else "STALE / UNAVAILABLE"),
        ],
        "WI-FI CSI": [
            ("TX Node", str(csi.get("tx_node") or "UNKNOWN")),
            ("RX Node", str(csi.get("rx_node") or "UNKNOWN")),
            ("RSSI", _number(csi.get("rssi_dbm"), "dBm", 0)),
            ("Packet Rate", _number(csi.get("packet_rate_hz"), "packets/s", 1)),
            ("CSI Quality", str(csi.get("quality") or "UNAVAILABLE")),
            ("Window", "READY" if csi.get("window_ready") else "NOT READY"),
            ("Model Release", model_release),
        ],
        "HUMAN CONTEXT": [
            ("Current Activity", str(csi.get("activity") or "UNKNOWN")),
            ("Confidence", _number(float(csi.get("confidence") or 0.0) * 100.0, "%", 0)),
            ("Context Freshness", "FRESH" if csi.get("is_fresh") else "STALE / UNAVAILABLE"),
        ],
        "SYSTEM": [
            ("MQTT", str(system.get("mqtt") or "UNKNOWN")),
            ("Local Storage", str(system.get("local_storage") or "UNKNOWN")),
            ("Node 1 · Sensor/TX", str(system.get("node1_status") or "UNKNOWN")),
            ("Node 2 · CSI/Gateway", str(system.get("node2_status") or "UNKNOWN")),
            ("Output State", str(system.get("output_state") or fusion_state)),
            ("LED Output", _led_output(system)),
            ("Buzzer", "ACTIVE" if system.get("buzzer_on") else "OFF"),
            ("NVS Queue", f"{int(system.get('queue_depth') or 0)} / 16"),
            ("CSI Queue Drops", str(int(system.get("csi_drops") or 0))),
        ],
        "REVIEW EVIDENCE": [
            ("Custom BME680 Driver", "HOST VERIFIED"),
            ("NVS Persistence", "HOST VERIFIED"),
            ("CSI Pre-processing", "HOST VERIFIED"),
            ("Reliable MQTT Contract", "HOST VERIFIED"),
            ("Dashboard Prototype", "LIVE"),
            ("Hardware Verification", "PENDING DEVICE TEST"),
        ],
    }
    return {
        "overall_status": fusion_state,
        "device_id": str(latest.get("device_id") or "NOT REPORTED"),
        "observed_at": latest.get("observed_at"),
        "sections": sections,
    }


def render_section_html(title: str, rows: list[tuple[str, str]]) -> str:
    rendered_rows = "".join(
        f"<div class='status-row'><span class='status-label'>{escape(str(label))}</span>"
        f"<span class='status-value {tone(str(value))}'>{escape(str(value))}</span></div>"
        for label, value in rows
    )
    return f"<section class='review-card'><h2>{escape(title)}</h2>{rendered_rows}</section>"
