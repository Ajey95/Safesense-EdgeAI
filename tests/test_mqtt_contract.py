from safesense.mqtt_contract import build_application_ack


def test_ack_requires_exact_backend_acceptance():
    event = {"event_id": "evt-12345678", "device_id": "esp32s3-node2"}
    accepted = {
        "accepted": True,
        "event_id": "evt-12345678",
        "status": "ACCEPTED",
    }
    assert build_application_ack(event, accepted) == {
        "event_id": "evt-12345678",
        "status": "ACCEPTED",
    }
    assert build_application_ack(event, {**accepted, "event_id": "evt-wrong"}) is None
    assert build_application_ack(event, {**accepted, "status": "REJECTED"}) is None
    assert build_application_ack(event, {"accepted": True}) is None
    assert build_application_ack({"device_id": "missing-event"}, accepted) is None
