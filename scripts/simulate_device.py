"""Replay an ESP32-shaped device stream against a local SafeSense server."""
from datetime import datetime, timezone
from itertools import cycle
from uuid import uuid4
import json
from urllib.request import Request, urlopen
import time

URL = "http://127.0.0.1:8000/api/v1/telemetry"
SCENES = cycle([
    ("VACANT", 0.93, "NORMAL", True),
    ("WALKING", 0.88, "NORMAL", True),
    ("STATIONARY", 0.81, "WARNING", True),
    ("UNKNOWN", 0.0, "NORMAL", False),
    ("STATIONARY", 0.91, "CRITICAL", True),
])

while True:
    activity, confidence, risk, fresh = next(SCENES)
    ratio = {"NORMAL": 1.02, "WARNING": 0.70, "CRITICAL": 0.45}[risk]
    output_state = {"NORMAL": "NORMAL", "WARNING": "WARNING", "CRITICAL": "INCIDENT"}[risk]
    payload = {
        "event_id": str(uuid4()),
        "device_id": "esp32s3-node2",
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "firmware_version": "sim-esp32s3-v2",
        "environment": {
            "temperature_c": 29.3,
            "humidity_pct": 61.0,
            "pressure_pa": 100920.0,
            "gas_resistance_ohm": 100000 * ratio,
            "gas_baseline_ohm": 100000,
            "gas_ratio": ratio,
            "gas_risk": risk,
            "gas_valid": True,
            "heat_stable": True,
            "sensor_healthy": True,
            "is_fresh": True,
        },
        "csi": {
            "activity": activity,
            "confidence": confidence,
            "quality": "GOOD" if fresh else "UNAVAILABLE",
            "tx_node": "ONLINE",
            "rx_node": "ONLINE",
            "packet_rate_hz": 85.0 if fresh else 0.0,
            "rssi_dbm": -49,
            "is_fresh": fresh,
            "window_ready": fresh,
            "model_release_state": "DISABLED_RELEASE_GATE",
        },
        "system": {
            "mqtt": "CONNECTED",
            "local_storage": "OK",
            "node1_status": "ONLINE",
            "node2_status": "ONLINE",
            "output_state": output_state if fresh or risk != "NORMAL" else "DEGRADED",
            "green_led": output_state == "NORMAL" and fresh,
            "yellow_led": output_state == "WARNING" or (not fresh and risk == "NORMAL"),
            "red_led": output_state == "INCIDENT",
            "buzzer_on": output_state == "INCIDENT",
            "queue_depth": 1,
            "csi_drops": 0,
        },
    }
    request = Request(URL, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urlopen(request, timeout=3) as response:
            print(response.read().decode())
    except OSError as error:
        print(f"Delivery deferred: {error}")
    time.sleep(3)
