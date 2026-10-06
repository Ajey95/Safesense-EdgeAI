"""Local operations dashboard for SafeSense."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from html import escape
from urllib.error import URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

import streamlit as st

from safesense.dashboard_view import (
    build_dashboard_view,
    incident_display,
    local_clock,
    render_section_html,
    tone,
)

API_URL = os.getenv("SAFESENSE_API_URL", "http://127.0.0.1:8000").rstrip("/")
R1_REVIEW = os.getenv("SAFESENSE_R1_REVIEW") == "1"
REFRESH_SECONDS = 3


def stored_number(value: object, unit: str, decimals: int = 1) -> str:
    if value is None:
        return "UNAVAILABLE"
    try:
        return f"{float(value):,.{decimals}f} {unit}"
    except (TypeError, ValueError):
        return "UNAVAILABLE"


def reported_node(value: object, fresh: bool) -> str:
    state = str(value or "UNKNOWN").upper()
    if state not in {"ONLINE", "OFFLINE"}:
        return "UNAVAILABLE"
    return f"REPORTED {state}" if fresh else f"LAST REPORTED {state} · STALE"


def api_json(path: str, method: str = "GET") -> dict:
    request = Request(f"{API_URL}{path}", method=method)
    with urlopen(request, timeout=3) as response:
        return json.loads(response.read().decode("utf-8"))


def render_section(title: str, rows: list[tuple[str, str]]) -> None:
    st.markdown(render_section_html(title, rows), unsafe_allow_html=True)


def acknowledge(incident_id: str) -> None:
    api_json(f"/api/v1/incidents/{quote(incident_id, safe='')}/acknowledge?operator=Local%20operator", method="POST")
    st.toast("Incident acknowledged", icon="✅")


def event_description(item: dict) -> str:
    payload = item.get("payload", {})
    csi = payload.get("csi", {})
    risk = payload.get("environment", {}).get("gas_risk")
    activity = csi.get("activity", "UNKNOWN")
    if risk == "CRITICAL":
        return "Critical environmental risk"
    if risk == "WARNING":
        return "Environmental warning"
    if activity == "WALKING":
        return "Walking detected"
    if activity == "STATIONARY":
        return "Stationary"
    if activity == "VACANT":
        return "Vacant"
    return "Telemetry received"


@st.fragment(run_every=REFRESH_SECONDS)
def live_workspace() -> None:
    try:
        data = api_json("/api/v1/overview")
    except (URLError, TimeoutError, json.JSONDecodeError):
        st.error("Telemetry service unavailable. Retrying automatically.")
        return

    telemetry = data.get("telemetry") or []
    if R1_REVIEW:
        telemetry = [item for item in telemetry if str(item.get("event_id", "")).startswith("tx-")]
    incidents = data.get("incidents") or []
    if not telemetry:
        st.info("Waiting for the first device report.")
        return

    latest = telemetry[0]
    payload = latest.get("payload", {})
    csi = payload.get("csi", {})
    view = build_dashboard_view(latest, now=datetime.now(timezone.utc))
    overall_status = ("FRESH" if view["telemetry_fresh"] else "STALE DATA") if R1_REVIEW else view["overall_status"]

    if not view["telemetry_fresh"]:
        if R1_REVIEW:
            st.warning(
                f"No fresh device telemetry ({view['telemetry_age_label']}). "
                "Last stored readings remain visible below; they are not current."
            )
        else:
            st.warning(
                f"No fresh device telemetry ({view['telemetry_age_label']}). "
                "Connectivity and output states are shown as unknown until a new report arrives."
            )

    st.markdown(
        f"<div class='summary-strip'><div><span>{'Data freshness' if R1_REVIEW else 'Overall status'}</span><strong class='{'good' if R1_REVIEW and view['telemetry_fresh'] else tone(overall_status)}'>{escape(overall_status)}</strong></div>"
        f"<div><span>Device</span><strong>{escape(view['device_id'])}</strong></div>"
        f"<div><span>Backend ingress</span><strong class='{tone(str(latest.get('backend_ingress') or 'UNVERIFIED'))}'>{escape(str(latest.get('backend_ingress') or 'UNVERIFIED'))}</strong></div>"
        f"<div><span>Last update</span><strong>{escape(local_clock(view['observed_at']))} · {escape(view['telemetry_age_label'])}</strong></div></div>",
        unsafe_allow_html=True,
    )

    environment_rows = view["sections"]["ENVIRONMENT"]
    csi_rows = view["sections"]["WI-FI CSI"]
    system_rows = view["sections"]["SYSTEM"]
    communication_rows = view["sections"]["COMMUNICATION EVIDENCE"]
    if R1_REVIEW:
        environment = payload.get("environment") or {}
        environment_rows = [
            ("Temperature", stored_number(environment.get("temperature_c"), "°C")),
            ("Humidity", stored_number(environment.get("humidity_pct"), "%")),
            ("Pressure", stored_number(environment.get("pressure_pa"), "Pa", 0)),
            ("Sensor healthy", str(environment.get("sensor_healthy", "UNKNOWN")).upper()),
            ("Reading freshness", "FRESH" if view["telemetry_fresh"] else "STALE · LAST STORED"),
        ]
        csi_rows = [
            ("TX Node", reported_node(csi.get("tx_node"), view["telemetry_fresh"])),
            ("RX Node", reported_node(csi.get("rx_node"), view["telemetry_fresh"])),
            ("RSSI", stored_number(csi.get("rssi_dbm"), "dBm", 0)),
            ("Packet Rate", stored_number(csi.get("packet_rate_hz"), "packets/s")),
            ("Window", "READY" if csi.get("window_ready") else "NOT READY"),
            ("Window frames", str(csi.get("window_frames") or "UNAVAILABLE")),
            ("Measured carriers", str(csi.get("selected_subcarriers") or "UNAVAILABLE")),
            ("Model Release", str(csi.get("model_release_state") or "UNAVAILABLE").replace("_", " ")),
        ]
        system_rows = [row for row in system_rows if row[0] not in {
            "Output State", "LED Output", "Buzzer",
        }]
        system_rows = [
            (label, reported_node(csi.get("tx_node"), view["telemetry_fresh"]))
            if label == "Node 1 · Sensor/TX" else
            (label, reported_node(csi.get("rx_node"), view["telemetry_fresh"]))
            if label == "Node 2 · CSI/Gateway" else
            (label, value)
            for label, value in system_rows
        ]
        communication_rows = [
            ("Origin from API alone", value) if label == "Device origin" else (label, value)
            for label, value in communication_rows
        ]

    left, right = st.columns(2, gap="large")
    with left:
        render_section("ENVIRONMENT" if view["telemetry_fresh"] or not R1_REVIEW else "ENVIRONMENT · LAST STORED", environment_rows)
        render_section("HUMAN CONTEXT", view["sections"]["HUMAN CONTEXT"])
    with right:
        render_section("WI-FI CSI" if view["telemetry_fresh"] or not R1_REVIEW else "WI-FI CSI · LAST STORED", csi_rows)
        render_section("SYSTEM", system_rows)

    render_section("COMMUNICATION EVIDENCE", communication_rows)
    st.caption("Backend ingress is observed by FastAPI. RX delivery and persistence are receiver-reported. 'Origin from API alone: UNVERIFIED' means the API cannot identify the physical board; match this event ID with both UART logs and the bridge output during the live demo.")
    with st.expander("Selected stored telemetry" if R1_REVIEW else "Stored JSON telemetry"):
        st.caption(f"Event ID: {view['event_id']} · Server received: {local_clock(view['received_at'])}")
        if R1_REVIEW:
            environment = payload.get("environment") or {}
            communication = payload.get("communication") or {}
            st.json({
                "event_id": view["event_id"],
                "environment": {key: environment.get(key) for key in (
                    "temperature_c", "humidity_pct", "pressure_pa", "sensor_healthy",
                )},
                "csi": {key: csi.get(key) for key in (
                    "activity", "window_ready", "window_frames", "selected_subcarriers",
                    "rssi_dbm", "packet_rate_hz",
                )},
                "communication": {key: communication.get(key) for key in (
                    "tx_rx_transport", "rx_queue_persisted",
                )},
            })
        else:
            st.json(payload)

    recent_rows = "".join(
        f"<div class='event-row'><time>{escape(local_clock(item.get('observed_at')))}</time><span>{escape('Telemetry received' if R1_REVIEW else event_description(item))}</span></div>"
        for item in telemetry[:8]
    )
    st.markdown(f"<section class='review-card events'><h2>RECENT EVENTS</h2>{recent_rows}</section>", unsafe_allow_html=True)

    values = csi.get("amplitude_summary")
    if values:
        with st.expander("CSI window detail"):
            st.line_chart({"Amplitude": values}, height=240, use_container_width=True)
            st.caption(f"{csi.get('window_frames', '—')} frames · {csi.get('selected_subcarriers', '—')} subcarriers · {csi.get('model_version') or csi.get('model_release_state', 'Model unavailable')}")

    active_incidents, hidden_incident_count = incident_display(incidents)
    if active_incidents and not R1_REVIEW:
        st.subheader("Active incidents")
        if hidden_incident_count:
            st.caption(f"Showing the newest {len(active_incidents)}; {hidden_incident_count} more active incident(s) remain in the event store.")
        for incident in active_incidents:
            title, action = st.columns((4, 1))
            with title:
                st.error(f"{incident['severity']} · {incident['reason']}")
            with action:
                if st.button("Acknowledge", key=f"ack-{incident['incident_id']}", use_container_width=True):
                    try:
                        acknowledge(incident["incident_id"])
                    except (URLError, TimeoutError, json.JSONDecodeError):
                        st.error("Acknowledgement failed. Try again.")


st.set_page_config(page_title="SafeSense / WiSense Dashboard", page_icon="◈", layout="wide", initial_sidebar_state="collapsed")
st.markdown("""<style>
  .block-container{max-width:1180px;padding-top:2.2rem;padding-bottom:3rem}
  h1{letter-spacing:-.045em;font-size:2.25rem!important;margin-bottom:.15rem}.review-subtitle{color:var(--text-color);opacity:.62;margin-bottom:1.5rem}
  .summary-strip{display:grid;grid-template-columns:1fr 1.35fr 1.1fr 1fr;gap:1px;background:color-mix(in srgb,var(--text-color) 15%,transparent);border:1px solid color-mix(in srgb,var(--text-color) 15%,transparent);border-radius:.65rem;overflow:hidden;margin:1.2rem 0 1.5rem}
  .summary-strip>div{display:flex;flex-direction:column;gap:.3rem;background:var(--secondary-background-color);padding:.85rem 1rem}.summary-strip span{font-size:.68rem;font-weight:700;letter-spacing:.09em;text-transform:uppercase;opacity:.58}.summary-strip strong{font-size:.98rem}
  .review-card{border:1px solid color-mix(in srgb,var(--text-color) 15%,transparent);border-radius:.75rem;padding:1.1rem 1.25rem;margin-bottom:1.15rem;background:var(--secondary-background-color);box-shadow:0 8px 28px color-mix(in srgb,var(--text-color) 5%,transparent)}
  .review-card h2{font-size:.74rem!important;letter-spacing:.11em;margin:0 0 .7rem!important;opacity:.62}.status-row{display:flex;align-items:center;justify-content:space-between;gap:1rem;min-height:2.05rem;border-top:1px solid color-mix(in srgb,var(--text-color) 9%,transparent)}.status-row:first-of-type{border-top:0}.status-label{opacity:.72}.status-value{font-weight:680;text-align:right}.good{color:#16865b}.warning{color:#b77900}.danger{color:#d13c31}.unknown{color:#4e7fd8}
  .events{margin-top:.2rem}.event-row{display:grid;grid-template-columns:90px 1fr;gap:1rem;align-items:center;min-height:2.2rem;border-top:1px solid color-mix(in srgb,var(--text-color) 9%,transparent)}.event-row:first-of-type{border-top:0}.event-row time{font-variant-numeric:tabular-nums;opacity:.58}.event-row span{font-weight:560}
  @media(max-width:700px){.summary-strip{grid-template-columns:1fr}.status-row{align-items:flex-start}.block-container{padding-top:1.4rem}.event-row{grid-template-columns:76px 1fr}}
</style>""", unsafe_allow_html=True)
st.title("SafeSense / WiSense Dashboard")
st.markdown("<p class='review-subtitle'>BME680 environment · Wi-Fi CSI context · two-node safety status</p>", unsafe_allow_html=True)
live_workspace()
