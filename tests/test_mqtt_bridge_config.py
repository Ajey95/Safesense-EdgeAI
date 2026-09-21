from scripts import mqtt_bridge


def test_broker_address_uses_configured_port(monkeypatch):
    monkeypatch.setenv("SAFESENSE_MQTT_BROKER", "127.0.0.1")
    monkeypatch.setenv("SAFESENSE_MQTT_PORT", "1884")

    assert mqtt_bridge.broker_address() == ("127.0.0.1", 1884)
