"""Scenario-first forecasting demonstration. All episodes and route receipts here are simulated."""

from __future__ import annotations

import html
import time
from pathlib import Path

import numpy as np
import streamlit as st
import streamlit.components.v1 as components

from safesense.forecast_model import ForecastModel, HORIZONS
from safesense.forecast_hardware import replay_on_tx
from safesense.forecast_scenarios import CHANNELS, SCENARIOS, first_breach, generate_episode, safe_limits


ROOT = Path(__file__).resolve().parents[2]
MODEL_PATH = ROOT / "ml" / "forecast_release" / "synthetic_v1" / "model.json"

THEMES = {
    "Cold storage": ("#061d2d", "#155b7d", "#7ce0ee", "❄", "A cold chain under pressure"),
    "Laboratory": ("#10251f", "#236b5a", "#9de2b7", "◈", "A process shifting quietly"),
    "Classroom": ("#241b3c", "#66509b", "#d2b9ff", "✦", "A room filling over time"),
    "Bakery": ("#382019", "#a9613d", "#ffd18e", "✷", "A hot process with a second wave"),
    "Server room": ("#101d33", "#2f5d9a", "#97c6ff", "▦", "A cooling margin that is shrinking"),
}
LABELS = {"temperature_c": "Temperature", "humidity_pct": "Humidity", "pressure_pa": "Pressure",
          "gas_resistance_ohm": "BME680 gas resistance", "mq135_adc_raw": "MQ-135 raw ADC"}
UNITS = {"temperature_c": "°C", "humidity_pct": "%", "pressure_pa": "Pa",
         "gas_resistance_ohm": "Ω", "mq135_adc_raw": "raw"}


@st.cache_resource
def load_model() -> ForecastModel:
    return ForecastModel.load(MODEL_PATH)


def value_text(channel: str, value: float) -> str:
    return f"{value:,.0f}" if channel in {"pressure_pa", "gas_resistance_ohm", "mq135_adc_raw"} else f"{value:.1f}"


def chart_svg(values: np.ndarray, now: int, prediction: np.ndarray, channel: str,
              room: str, reveal: bool) -> str:
    index = CHANNELS.index(channel)
    observed = values[max(0, now - 45):now + 1, index]
    future = prediction[:, index]
    truth = values[[now + h for h in HORIZONS], index]
    displayed = np.r_[observed, future, truth if reveal else []]
    lower, upper = safe_limits(room).get(channel, (float(np.min(displayed)), float(np.max(displayed))))
    lo = min(float(np.min(displayed)), lower) - 0.08 * max(1, float(np.ptp(displayed)))
    hi = max(float(np.max(displayed)), upper) + 0.08 * max(1, float(np.ptp(displayed)))
    if hi - lo < 1:
        hi = lo + 1
    def xy(i: float, v: float) -> str:
        x = 46 + 758 * i / 75
        y = 230 - 177 * (float(v) - lo) / (hi - lo)
        return f"{x:.1f},{y:.1f}"
    past_x = list(range(45 - (len(observed) - 1), 46))
    past = " ".join(xy(i, v) for i, v in zip(past_x, observed))
    forecast = " ".join(xy(i, v) for i, v in zip((45, 50, 55, 60, 65, 70, 75), (values[now, index], *future)))
    actual = " ".join(xy(i, v) for i, v in zip((45, 50, 55, 60, 65, 70, 75), (values[now, index], *truth)))
    yl = 230 - 177 * (lower - lo) / (hi - lo)
    yu = 230 - 177 * (upper - lo) / (hi - lo)
    band_top, band_bottom = sorted((yl, yu))
    truth_line = f'<polyline points="{actual}" fill="none" stroke="#a7b5c0" stroke-width="2" stroke-dasharray="5 5" />' if reveal else ""
    return f'''<svg viewBox="0 0 850 265" role="img" aria-label="Observed and predicted {html.escape(LABELS[channel])}">
      <rect x="46" y="{band_top:.1f}" width="758" height="{band_bottom-band_top:.1f}" fill="#4fd2b0" opacity=".075" />
      <line x1="501" y1="35" x2="501" y2="232" stroke="#8aa5b8" stroke-dasharray="4 6" opacity=".55" />
      <line x1="46" y1="232" x2="804" y2="232" stroke="#8aa5b8" opacity=".35" />
      <polyline points="{past}" fill="none" stroke="#81dfeb" stroke-width="3" stroke-linejoin="round" />
      <polyline points="{forecast}" fill="none" stroke="#ffbd76" stroke-width="3.5" stroke-linejoin="round" />
      {truth_line}<circle cx="501" cy="{xy(45, values[now,index]).split(',')[1]}" r="5" fill="#ffffff" />
      <text x="46" y="253">45 min ago</text><text x="478" y="253">NOW</text><text x="767" y="253">+30 min</text>
      <text x="48" y="24">Safe demo range: {value_text(channel,lower)}–{value_text(channel,upper)} {UNITS[channel]}</text>
      </svg>'''


def route_html(event_id: str, failure: bool, alert: bool, hardware: dict | None = None) -> str:
    if not alert:
        if hardware:
            return ('<div class="route-note">No edge forecast alert. TX sample '
                    + ('reached RX with an exact ACK.' if hardware["rx_ack"] else 'has no RX ACK.')
                    + '</div>')
        return '<div class="route-note">No forecast alert at this minute. The route is ready for a future event.</div>'
    if hardware:
        blocks = [
            ("01", "TX ESP32", "NVS persisted" if hardware["tx_persisted"] else "NVS write failed"),
            ("02", "Wi-Fi → RX ESP32", "exact-ID ACK received" if hardware["rx_ack"] else "no RX ACK"),
            ("03", "Bluetooth → nearby laptop", "stored receipt received" if hardware["bt_ack"] else "receipt unconfirmed"),
            ("04", "Voice alert", "local receiver attempted playback" if hardware["bt_ack"] else "manual demo playback available"),
        ]
        classes = ("active" if hardware["tx_persisted"] else "failed",
                   "active" if hardware["rx_ack"] else "failed",
                   "active" if hardware["bt_ack"] else "idle",
                   "idle")
        return ('<div class="route-row">' + ''.join(
            f'<div class="route-step {classes[i]}"><span>{number}</span><strong>{title}</strong><small>{detail}</small></div>'
            for i, (number, title, detail) in enumerate(blocks))
            + '</div><div class="route-event">TX reported event ID · ' + html.escape(event_id) + '</div>')
    blocks = [
        ("01", "TX ESP32", "event prepared in simulation"),
        ("02", "Wi-Fi → RX ESP32", "simulated link failed" if failure else "simulated exact-ID ACK"),
        ("03", "Bluetooth → nearby laptop", "simulated receipt" if failure else "standby"),
        ("04", "Voice alert", "demo playback available"),
    ]
    return '<div class="route-row">' + ''.join(
        f'<div class="route-step {"failed" if failure and i == 1 else "active" if i in (0,3) or (i==1 and not failure) or (i==2 and failure) else "idle"}">'
        f'<span>{number}</span><strong>{title}</strong><small>{detail}</small></div>'
        for i, (number, title, detail) in enumerate(blocks)
    ) + '</div><div class="route-event">Simulated event ID · ' + html.escape(event_id) + '</div>'


def voice_button(message: str):
    safe = html.escape(message, quote=True)
    components.html(f'''<button id="speak" style="background:#ffc083;border:0;border-radius:12px;padding:12px 18px;font-weight:700;cursor:pointer;color:#17191c">▶ Play demo voice alert</button>
      <script>document.getElementById('speak').onclick=()=>{{speechSynthesis.cancel();speechSynthesis.speak(new SpeechSynthesisUtterance(document.getElementById('copy').textContent));}};</script>
      <span id="copy" hidden>{safe}</span>''', height=56)


st.set_page_config(page_title="Forecast Lab · SafeSense", page_icon="◈", layout="wide", initial_sidebar_state="expanded")
st.sidebar.title("Forecast lab")
st.sidebar.caption("Controlled synthetic demonstration")
heldout = [s for s in SCENARIOS if s.split == "test"]
scenario = st.sidebar.selectbox("Choose an unseen scenario", heldout, format_func=lambda s: f"{s.room} · {s.title}")
episode = st.sidebar.number_input("Episode seed", min_value=1, max_value=999, value=17, step=1)
if "scenario_next_minute" in st.session_state:
    st.session_state.scenario_minute = st.session_state.pop("scenario_next_minute")
minute = st.sidebar.slider("Simulation minute", min_value=60, max_value=110, value=82, step=1, key="scenario_minute")
wifi_failure = st.sidebar.toggle("Inject Wi-Fi TX→RX send failure", value=False)
reveal = st.sidebar.toggle("Reveal hidden simulator future", value=False)
hardware_mode = st.sidebar.toggle("Replay through connected TX ESP32", value=False)
if st.sidebar.button("Pause" if st.session_state.get("scenario_playing") else "Play", use_container_width=True):
    st.session_state.scenario_playing = not st.session_state.get("scenario_playing", False)
st.sidebar.divider()
st.sidebar.info("The scenarios and readings are synthetic. Physical route receipts appear only after an explicit TX hardware replay. No SOS service is contacted.")

if not MODEL_PATH.exists():
    st.error("Forecast model is missing. Run `python ml/training/train_synthetic_forecast.py` first.")
    st.stop()

values = generate_episode(scenario, 90_000 + SCENARIOS.index(scenario) * 1000 + int(episode))
model = load_model()
predicted = model.predict(values, minute, scenario.room)
predicted_path = np.vstack((values[minute], predicted))
forecast_offset, forecast_channel = first_breach(predicted_path, scenario.room, 0, 6)
actual_offset, actual_channel = first_breach(values, scenario.room, minute, 30)
alert = forecast_offset is not None
event_id = f"sim-{scenario.key}-{int(episode):03d}-{minute:03d}"
run_key = (scenario.key, int(episode), minute, wifi_failure)
if hardware_mode:
    tx_port = st.sidebar.text_input("TX USB serial port", value="COM11")
    if st.sidebar.button("Send 61-minute history to TX", use_container_width=True):
        try:
            with st.spinner("Replaying sensor history through TX and waiting for receipts…"):
                result = replay_on_tx(tx_port, values, minute, scenario.room, wifi_failure)
            st.session_state.forecast_hardware_result = (run_key, result)
        except (OSError, ValueError, RuntimeError, TimeoutError) as error:
            st.sidebar.error(str(error))
hardware = None
if hardware_mode and st.session_state.get("forecast_hardware_result", (None,))[0] == run_key:
    hardware = st.session_state.forecast_hardware_result[1]
    event_id = hardware["event_id"]
    if hardware["alert"] != alert:
        st.warning("TX and dashboard forecast alert decisions differ for this rounded replay. Use the TX receipt as the hardware result.")
bg, accent, light, symbol, heading = THEMES[scenario.room]

st.markdown(f"""<style>
  .stApp {{background:linear-gradient(145deg,{bg} 0%,#101b27 65%,#101820 100%);color:#edf6f8}}
  [data-testid="stSidebar"] {{background:#101924}}
  [data-testid="stSidebar"] h1,[data-testid="stSidebar"] h2,[data-testid="stSidebar"] h3 {{color:#e9f4f7!important}}
  [data-testid="stHeader"] {{background:{bg}!important}}
  [data-testid="stToolbar"] {{background:transparent!important}}
  [data-testid="stSidebar"] div.stButton > button {{background:{accent};color:#fff;border:1px solid {light};font-weight:700}}
  .block-container {{max-width:1320px;padding-top:1.6rem}}
  h1,h2,h3,p,label {{color:#edf6f8}}
  .hero {{background:radial-gradient(circle at 83% 35%,{accent} 0%,transparent 38%),linear-gradient(112deg,{bg},#172e3f);border:1px solid #ffffff20;border-radius:24px;padding:30px 36px;min-height:204px;position:relative;overflow:hidden}}
  .hero:after {{content:'{symbol}';font-size:130px;color:{light};opacity:.16;position:absolute;right:8%;top:0;line-height:1.1}}
  .hero h1 {{font-size:2.8rem;letter-spacing:-.05em;line-height:1.05;margin:13px 0 8px;max-width:700px}}
  .hero p {{font-size:1.05rem;max-width:760px;color:#d5e9ee;line-height:1.5}}
  .eyebrow {{font-size:.78rem;letter-spacing:.18em;text-transform:uppercase;color:{light};font-weight:700}}
  .panel {{background:#ffffff0b;border:1px solid #ffffff22;border-radius:20px;padding:22px 25px;margin-top:16px}}
  .metric-grid {{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px}}
  .metric {{background:#ffffff0b;border:1px solid #ffffff20;border-radius:16px;padding:16px 20px}}
  .metric small {{display:block;color:#aabec7;font-size:.78rem;margin-bottom:8px}}
  .metric strong {{font-size:1.72rem;color:#f1f7f8;letter-spacing:-.04em}}
  .metric em {{display:block;color:{light};font-size:.78rem;font-style:normal;margin-top:6px}}
  .callout {{border-left:4px solid {('#ff9c81' if alert else '#73d8b0')};background:#ffffff10;padding:16px 20px;border-radius:6px 14px 14px 6px;margin:14px 0}}
  .callout b {{color:{('#ffbfaa' if alert else '#a5ebc9')}}}
  .route-row {{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:11px;margin-top:14px}}
  .route-step {{min-height:122px;background:#ffffff09;border:1px solid #ffffff26;border-radius:15px;padding:14px}}
  .route-step span {{display:block;color:{light};font-size:.8rem;font-weight:700}}
  .route-step strong {{display:block;margin:8px 0 6px;color:#fff}}
  .route-step small {{color:#bfd2db}} .route-step.failed {{border-color:#ff9c81;background:#ff9c8114}}
  .route-step.active {{border-color:{light};background:#ffffff12}} .route-step.idle {{opacity:.54}}
  .route-event,.route-note {{color:#a8bdc8;font-size:.84rem;margin-top:12px}}
  .chart svg {{width:100%;height:auto}} .chart text {{fill:#b5c9d2;font:13px system-ui,sans-serif}}
  @media(max-width:800px) {{.hero h1 {{font-size:2rem}} .metric-grid,.route-row {{grid-template-columns:repeat(2,1fr)}}}}
</style>""", unsafe_allow_html=True)

st.markdown(f'''<div class="hero"><div class="eyebrow">{html.escape(scenario.room)} · minute {minute}</div>
<h1>{html.escape(heading)}</h1><p>{html.escape(scenario.story)}</p>
<div style="font-size:.85rem;color:{light}">UNSEEN SCENARIO FAMILY · CONTROLLED SYNTHETIC EPISODE</div></div>''', unsafe_allow_html=True)

st.markdown("### Current room → 30 minutes ahead")
channels = ("temperature_c", "humidity_pct", "gas_resistance_ohm", "mq135_adc_raw")
st.markdown('<div class="metric-grid">' + ''.join(
    f'<div class="metric"><small>{LABELS[ch]}</small><strong>{value_text(ch,values[minute,CHANNELS.index(ch)])} {UNITS[ch]}</strong>'
    f'<em>Predicted +30m: {value_text(ch,predicted[-1,CHANNELS.index(ch)])} {UNITS[ch]}</em></div>' for ch in channels
) + '</div>', unsafe_allow_html=True)

if alert:
    # Six points at 5-minute spacing; the first breach is an interval estimate.
    estimated_minute = forecast_offset * 5
    st.markdown(f'<div class="callout"><b>Early forecast alert · about {estimated_minute} minutes ahead</b><br>'
                f'{html.escape(LABELS[forecast_channel])} is forecast to cross the configured {html.escape(scenario.room.lower())} demo range. '
                f'{html.escape(scenario.response)}</div>', unsafe_allow_html=True)
else:
    st.markdown('<div class="callout"><b>No 30-minute forecast breach in the configured demo ranges.</b><br>'
                'This does not establish that the room is safe.</div>', unsafe_allow_html=True)

st.markdown("### Alert journey")
route_label = ('TX HARDWARE RECEIPTS' if hardware else 'SIMULATED ROUTE') + (' · WI-FI SEND BLOCKED' if wifi_failure else ' · PRIMARY WI-FI')
st.markdown('<div class="panel"><div class="eyebrow">' + route_label + '</div>'
            + route_html(event_id, wifi_failure, hardware["alert"] if hardware else alert, hardware) + '</div>', unsafe_allow_html=True)
if alert:
    voice_button(f"SafeSense demonstration alert. {scenario.room}. A sensor trend may cross the configured range in about {estimated_minute} minutes. {scenario.response}")
if hardware:
    st.caption("Hardware evidence: TX USB result reports its NVS, RX exact-ID ACK and nearby laptop Bluetooth stored receipt separately. Speech completion and backend storage are not proved by this result.")
else:
    st.caption("Route blocks and acknowledgments are simulated. Enable TX hardware replay and run the paired laptop SPP receiver for physical-route evidence.")

left, right = st.columns([1.85, 1], gap="large")
with left:
    chart_channel = st.selectbox("Trace to inspect", CHANNELS, format_func=lambda c: LABELS[c])
    st.markdown('<div class="panel chart">' + chart_svg(values, minute, predicted, chart_channel, scenario.room, reveal) + '</div>', unsafe_allow_html=True)
    st.caption("Cyan: observed so far · amber: TinyML forecast · dashed: hidden simulator future (only when revealed). Green band: configured demo range.")
with right:
    st.markdown("#### Why it alerted")
    current_index = CHANNELS.index(forecast_channel) if forecast_channel else 0
    if alert:
        low, high = safe_limits(scenario.room)[forecast_channel]
        st.write(f"Current {LABELS[forecast_channel].lower()}: **{value_text(forecast_channel,values[minute,current_index])} {UNITS[forecast_channel]}**")
        st.write(f"Forecast in ~{estimated_minute} min: **{value_text(forecast_channel,predicted[forecast_offset-1,current_index])} {UNITS[forecast_channel]}**")
        st.write(f"Demo range: **{value_text(forecast_channel,low)}–{value_text(forecast_channel,high)} {UNITS[forecast_channel]}**")
    else:
        st.write("All predicted points remain within the configured demo ranges.")
    if reveal:
        st.write(f"Simulator's hidden future: **{'breach after ' + str(actual_offset) + ' min in ' + LABELS[actual_channel] if actual_offset else 'no breach in 30 min'}**")
    st.caption("The model sees only the previous 60 minutes and the selected room type. It does not see the scenario name, future readings or hidden simulator parameters.")

if hardware and hardware.get("edge_forecast_30min"):
    edge_t = hardware["edge_forecast_30min"][0]
    st.caption(f"TX TinyML +30 min temperature output: {edge_t:.2f} °C. Dashboard model output: {predicted[-1,0]:.2f} °C. The serial replay uses rounded sensor values, so small differences are expected.")
if st.session_state.get("scenario_playing"):
    if minute < 110:
        time.sleep(0.7)
        st.session_state.scenario_next_minute = minute + 1
        st.rerun()
    else:
        st.session_state.scenario_playing = False
