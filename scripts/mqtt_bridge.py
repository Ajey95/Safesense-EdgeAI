"""Optional MQTT-to-FastAPI bridge. Requires a configured broker; never embeds credentials."""
from __future__ import annotations
import json, os
from urllib.request import Request, urlopen
import paho.mqtt.client as mqtt

BROKER = os.environ["SAFESENSE_MQTT_BROKER"]
API = os.getenv("SAFESENSE_API_URL", "http://127.0.0.1:8000")

def on_message(client, userdata, message):
    try:
        payload = json.loads(message.payload.decode())
        request = Request(f"{API}/api/v1/telemetry", data=json.dumps(payload).encode(), headers={"Content-Type":"application/json"}, method="POST")
        with urlopen(request, timeout=5) as response:
            accepted = json.loads(response.read().decode())
        if accepted.get("accepted") is not True:
            raise ValueError("backend did not accept telemetry")
        client.publish(f"safesense/{payload['device_id']}/ack", json.dumps({"event_id":payload["event_id"],"status":"ACCEPTED"}), qos=1)
    except (ValueError, OSError, KeyError) as error:
        print(f"Rejected MQTT event: {error}")

client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
client.on_message = on_message
client.connect(BROKER)
client.subscribe("safesense/+/event", qos=1)
client.loop_forever()
