from __future__ import annotations


def build_application_ack(device_event: dict, backend_response: dict) -> dict | None:
    """Return the only ACK that is allowed to advance the device NVS queue."""
    event_id = device_event.get("event_id")
    if not isinstance(event_id, str) or not event_id:
        return None
    if (
        backend_response.get("accepted") is True
        and backend_response.get("event_id") == event_id
        and backend_response.get("status") == "ACCEPTED"
    ):
        return {"event_id": event_id, "status": "ACCEPTED"}
    return None
