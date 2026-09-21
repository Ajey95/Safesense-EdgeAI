"""Verify broker -> bridge -> API -> exact application ACK locally."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from threading import Event
from uuid import uuid4

import paho.mqtt.client as mqtt


def payload(event_id: str) -> dict:
    return {
        "event_id": event_id,
        "device_id": "esp32s3-node2",
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "firmware_version": "mqtt-smoke-v2",
        "environment": {
            "temperature_c": 29.3,
            "humidity_pct": 61.0,
            "pressure_pa": 100920.0,
            "gas_resistance_ohm": 102000.0,
            "gas_baseline_ohm": 100000.0,
            "gas_ratio": 1.02,
            "gas_risk": "NORMAL",
            "gas_valid": True,
            "heat_stable": True,
            "sensor_healthy": True,
            "is_fresh": True,
        },
        "csi": {
            "activity": "UNKNOWN",
            "confidence": 0.0,
            "quality": "UNAVAILABLE",
            "tx_node": "ONLINE",
            "rx_node": "ONLINE",
            "packet_rate_hz": 0.0,
            "rssi_dbm": -49,
            "is_fresh": False,
            "window_ready": False,
            "model_release_state": "DISABLED_RELEASE_GATE",
        },
        "system": {
            "mqtt": "CONNECTED",
            "local_storage": "OK",
            "node1_status": "ONLINE",
            "node2_status": "ONLINE",
            "output_state": "DEGRADED",
            "green_led": False,
            "yellow_led": True,
            "red_led": False,
            "buzzer_on": False,
            "queue_depth": 1,
            "csi_drops": 0,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=1884)
    parser.add_argument("--timeout", type=float, default=8.0)
    args = parser.parse_args()

    event_id = str(uuid4())
    ack_topic = "safesense/esp32s3-node2/ack"
    subscription_ready = Event()
    acknowledgement_ready = Event()
    received: dict = {}

    def on_subscribe(client, userdata, mid, reason_codes, properties):
        subscription_ready.set()

    def on_message(client, userdata, message):
        try:
            acknowledgement = json.loads(message.payload.decode())
        except (UnicodeDecodeError, json.JSONDecodeError):
            return
        if acknowledgement.get("event_id") == event_id:
            received.update(acknowledgement)
            acknowledgement_ready.set()

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.on_subscribe = on_subscribe
    client.on_message = on_message
    client.connect(args.host, port=args.port)
    client.loop_start()
    try:
        client.subscribe(ack_topic, qos=1)
        if not subscription_ready.wait(args.timeout):
            raise TimeoutError("broker did not confirm the ACK subscription")
        message = json.dumps(payload(event_id), separators=(",", ":"))
        publication = client.publish("safesense/esp32s3-node2/event", message, qos=1)
        publication.wait_for_publish(timeout=args.timeout)
        if not acknowledgement_ready.wait(args.timeout):
            raise TimeoutError("exact application ACK was not received")
    finally:
        client.disconnect()
        client.loop_stop()

    expected = {"event_id": event_id, "status": "ACCEPTED"}
    if received != expected:
        raise RuntimeError(f"unexpected ACK: {received!r}")
    print(json.dumps({"mqtt_round_trip": "PASS", "ack": received}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
