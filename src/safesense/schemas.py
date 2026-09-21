from datetime import datetime
from enum import StrEnum
from pydantic import BaseModel, ConfigDict, Field


class Activity(StrEnum):
    VACANT = "VACANT"
    STATIONARY = "STATIONARY"
    WALKING = "WALKING"
    UNKNOWN = "UNKNOWN"


class Risk(StrEnum):
    NORMAL = "NORMAL"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"
    UNAVAILABLE = "UNAVAILABLE"


class FusionState(StrEnum):
    NORMAL = "NORMAL"
    WARNING = "WARNING"
    INCIDENT = "INCIDENT"
    DEGRADED = "DEGRADED"


class HumanContext(StrEnum):
    KNOWN = "KNOWN"
    UNKNOWN = "UNKNOWN"


class NodeState(StrEnum):
    ONLINE = "ONLINE"
    OFFLINE = "OFFLINE"
    UNKNOWN = "UNKNOWN"


class CsiQuality(StrEnum):
    GOOD = "GOOD"
    FAIR = "FAIR"
    POOR = "POOR"
    UNAVAILABLE = "UNAVAILABLE"


class ServiceState(StrEnum):
    CONNECTED = "CONNECTED"
    DISCONNECTED = "DISCONNECTED"
    UNKNOWN = "UNKNOWN"


class StorageState(StrEnum):
    OK = "OK"
    DEGRADED = "DEGRADED"
    UNKNOWN = "UNKNOWN"


class EnvironmentalReading(BaseModel):
    model_config = ConfigDict(extra="forbid")
    temperature_c: float = Field(ge=-40, le=100)
    humidity_pct: float = Field(ge=0, le=100)
    pressure_pa: float | None = Field(default=None, ge=30000, le=110000)
    gas_risk: Risk
    sensor_healthy: bool = True


class CsiReading(BaseModel):
    model_config = ConfigDict(extra="forbid")
    activity: Activity
    confidence: float = Field(ge=0, le=1)
    quality: CsiQuality = CsiQuality.UNAVAILABLE
    tx_node: NodeState = NodeState.UNKNOWN
    rx_node: NodeState = NodeState.UNKNOWN
    packet_rate_hz: float = Field(ge=0, le=10000)
    rssi_dbm: int = Field(ge=-127, le=0)
    is_fresh: bool
    window_frames: int | None = Field(default=None, ge=1, le=1000)
    selected_subcarriers: int | None = Field(default=None, ge=1, le=256)
    model_version: str | None = Field(default=None, max_length=80)
    amplitude_summary: list[float] | None = Field(default=None, max_length=64)
    motion_rms: float | None = Field(default=None, ge=0)


class SystemReading(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mqtt: ServiceState = ServiceState.UNKNOWN
    local_storage: StorageState = StorageState.UNKNOWN
    esp32_status: NodeState = NodeState.UNKNOWN


class TelemetryIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event_id: str = Field(min_length=8, max_length=100, pattern=r"^[A-Za-z0-9_.:-]+$")
    device_id: str = Field(min_length=3, max_length=80, pattern=r"^[A-Za-z0-9_.:-]+$")
    # ESP32 nodes do not have a trustworthy wall clock until time sync. The
    # server substitutes its receive timestamp when the device sends null.
    observed_at: datetime | None = None
    firmware_version: str | None = Field(default=None, max_length=80)
    environment: EnvironmentalReading
    csi: CsiReading
    system: SystemReading = Field(default_factory=SystemReading)


class FusionResult(BaseModel):
    state: FusionState
    reason: str
    reason_code: str
    human_context: HumanContext
    local_alarm: bool
    incident_required: bool
