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
    payload = {"event_id": str(uuid4()), "device_id": "safesense-rx-01", "observed_at": datetime.now(timezone.utc).isoformat(), "firmware_version": "sim-0.2", "environment": {"temperature_c": 29.3, "humidity_pct": 61.0, "pressure_pa": 100920.0, "gas_risk": risk, "sensor_healthy": True}, "csi": {"activity": activity, "confidence": confidence, "quality": "GOOD" if fresh else "UNAVAILABLE", "tx_node": "ONLINE" if fresh else "UNKNOWN", "rx_node": "ONLINE", "packet_rate_hz": 85.0 if fresh else 0.0, "rssi_dbm": -49, "is_fresh": fresh}, "system": {"mqtt": "CONNECTED", "local_storage": "OK", "esp32_status": "ONLINE"}}
    request = Request(URL, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urlopen(request, timeout=3) as response:
            print(response.read().decode())
    except OSError as error:
        print(f"Delivery deferred: {error}")
    time.sleep(3)
