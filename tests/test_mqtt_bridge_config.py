from scripts import mqtt_bridge
from scripts.mqtt_smoke_test import payload


def test_broker_address_uses_configured_port(monkeypatch):
    monkeypatch.setenv("SAFESENSE_MQTT_BROKER", "127.0.0.1")
    monkeypatch.setenv("SAFESENSE_MQTT_PORT", "1884")

    assert mqtt_bridge.broker_address() == ("127.0.0.1", 1884)


def test_connect_and_reconnect_restore_event_subscription(monkeypatch):
    monkeypatch.setenv("SAFESENSE_MQTT_EVENT_TOPIC", "safesense/review/event")

    class Client:
        def __init__(self):
            self.subscriptions = []

        def subscribe(self, topic, qos):
            self.subscriptions.append((topic, qos))

    client = Client()
    mqtt_bridge.on_connect(client, None, {}, 0, None)
    mqtt_bridge.on_connect(client, None, {}, 0, None)
    assert client.subscriptions == [
        ("safesense/review/event", 1),
        ("safesense/review/event", 1),
    ]


def test_smoke_payload_does_not_claim_physical_hardware():
    event = payload("mqtt-smoke-test")
    assert event["environment"]["gas_risk"] == "UNAVAILABLE"
    assert event["csi"]["tx_node"] == "UNKNOWN"
    assert event["csi"]["rx_node"] == "UNKNOWN"
    assert event["system"]["node1_status"] == "UNKNOWN"
    assert event["system"]["node2_status"] == "UNKNOWN"
