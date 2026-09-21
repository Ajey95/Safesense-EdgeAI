"""MQTT-to-FastAPI bridge with exact application acknowledgements."""
from __future__ import annotations
import json
import os
from urllib.request import Request, urlopen
import paho.mqtt.client as mqtt
from safesense.mqtt_contract import build_application_ack

API = os.getenv("SAFESENSE_API_URL", "http://127.0.0.1:8000")

def on_message(client, userdata, message):
    try:
        payload = json.loads(message.payload.decode())
        request = Request(f"{API}/api/v1/telemetry", data=json.dumps(payload).encode(), headers={"Content-Type":"application/json"}, method="POST")
        with urlopen(request, timeout=5) as response:
            accepted = json.loads(response.read().decode())
        acknowledgement = build_application_ack(payload, accepted)
        if acknowledgement is None:
            raise ValueError("backend response did not exactly accept this event")
        topic = os.getenv("SAFESENSE_MQTT_ACK_TOPIC", f"safesense/{payload['device_id']}/ack")
        client.publish(topic, json.dumps(acknowledgement, separators=(",", ":")), qos=1)
    except (ValueError, OSError, KeyError) as error:
        print(f"Rejected MQTT event: {error}")

def run() -> None:
    broker = os.environ["SAFESENSE_MQTT_BROKER"]
    event_topic = os.getenv("SAFESENSE_MQTT_EVENT_TOPIC", "safesense/+/event")
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.on_message = on_message
    client.connect(broker)
    client.subscribe(event_topic, qos=1)
    client.loop_forever()


if __name__ == "__main__":
    run()
