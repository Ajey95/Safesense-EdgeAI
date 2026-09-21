"""Local operations dashboard for SafeSense."""

from __future__ import annotations

import json
import os
from datetime import datetime
from html import escape
from urllib.error import URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

import streamlit as st

from safesense.dashboard_view import build_dashboard_view, incident_display, render_section_html, tone

API_URL = os.getenv("SAFESENSE_API_URL", "http://127.0.0.1:8000").rstrip("/")
REFRESH_SECONDS = 3


def api_json(path: str, method: str = "GET") -> dict:
    request = Request(f"{API_URL}{path}", method=method)
    with urlopen(request, timeout=3) as response:
        return json.loads(response.read().decode("utf-8"))


def stamp(value: str | None) -> str:
    if not value:
        return "--:--:--"
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone().strftime("%H:%M:%S")
    except ValueError:
        return value


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
    incidents = data.get("incidents") or []
    if not telemetry:
        st.info("Waiting for the first device report.")
        return

    latest = telemetry[0]
    payload = latest.get("payload", {})
    csi = payload.get("csi", {})
    view = build_dashboard_view(latest)
    overall_status = view["overall_status"]

    st.markdown(
        f"<div class='summary-strip'><div><span>Overall status</span><strong class='{tone(overall_status)}'>{escape(overall_status)}</strong></div>"
        f"<div><span>Device</span><strong>{escape(view['device_id'])}</strong></div>"
        f"<div><span>Source</span><strong class='{tone(view['data_source'])}'>{escape(view['data_source'])}</strong></div>"
        f"<div><span>Last update</span><strong>{escape(stamp(view['observed_at']))}</strong></div></div>",
        unsafe_allow_html=True,
    )

    left, right = st.columns(2, gap="large")
    with left:
        render_section("ENVIRONMENT", view["sections"]["ENVIRONMENT"])
        render_section("HUMAN CONTEXT", view["sections"]["HUMAN CONTEXT"])
    with right:
        render_section("WI-FI CSI", view["sections"]["WI-FI CSI"])
        render_section("SYSTEM", view["sections"]["SYSTEM"])

    render_section("REVIEW EVIDENCE", view["sections"]["REVIEW EVIDENCE"])

    recent_rows = "".join(
        f"<div class='event-row'><time>{escape(stamp(item.get('observed_at')))}</time><span>{escape(event_description(item))}</span></div>"
        for item in telemetry[:8]
    )
    st.markdown(f"<section class='review-card events'><h2>RECENT EVENTS</h2>{recent_rows}</section>", unsafe_allow_html=True)

    values = csi.get("amplitude_summary")
    if values:
        with st.expander("CSI window detail"):
            st.line_chart({"Amplitude": values}, height=240, use_container_width=True)
            st.caption(f"{csi.get('window_frames', '—')} frames · {csi.get('selected_subcarriers', '—')} subcarriers · {csi.get('model_version') or csi.get('model_release_state', 'Model unavailable')}")

    active_incidents, hidden_incident_count = incident_display(incidents)
    if active_incidents:
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
