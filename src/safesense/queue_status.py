"""Validated, payload-free ESP32 NVS queue observations."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class BoardQueueIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status_id: str = Field(pattern=r"^st-[0-9a-f]{16}$")
    device_id: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_.:-]+$")
    sequence: int = Field(ge=1)
    uptime_ms: int = Field(ge=0)
    queue_depth: int = Field(ge=0, le=16)
    pending_event_ids: list[str] = Field(max_length=16)
    last_enqueued_id: str = Field(max_length=63, pattern=r"^$|^[A-Za-z0-9_-]{8,63}$")
    last_acked_id: str = Field(max_length=63, pattern=r"^$|^[A-Za-z0-9_-]{8,63}$")
    last_ack_route: Literal["NONE", "WIFI", "BLUETOOTH"]

    @model_validator(mode="after")
    def consistent_queue(self):
        if len(self.pending_event_ids) != self.queue_depth:
            raise ValueError("queue depth does not match pending ID list")
        if len(set(self.pending_event_ids)) != len(self.pending_event_ids):
            raise ValueError("duplicate pending event ID")
        if any(not 8 <= len(value) <= 63 or
               not all(char.isalnum() and char.isascii() or char in "_-" for char in value)
               for value in self.pending_event_ids):
            raise ValueError("invalid pending event ID")
        if bool(self.last_acked_id) != (self.last_ack_route != "NONE"):
            raise ValueError("last ACK route and event ID disagree")
        return self
