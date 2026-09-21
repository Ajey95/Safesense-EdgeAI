from datetime import datetime
from enum import StrEnum
from pydantic import BaseModel, ConfigDict, Field, model_validator


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


class ModelReleaseState(StrEnum):
    RELEASED_INT8 = "RELEASED_INT8"
    DISABLED_RELEASE_GATE = "DISABLED_RELEASE_GATE"
    UNAVAILABLE = "UNAVAILABLE"


class EnvironmentalReading(BaseModel):
    model_config = ConfigDict(extra="forbid")
    temperature_c: float | None = Field(default=None, ge=-40, le=100)
    humidity_pct: float | None = Field(default=None, ge=0, le=100)
    pressure_pa: float | None = Field(default=None, ge=30000, le=110000)
    gas_resistance_ohm: float | None = Field(default=None, gt=0)
    gas_baseline_ohm: float | None = Field(default=None, gt=0)
    gas_ratio: float | None = Field(default=None, ge=0, le=2)
    gas_risk: Risk
    gas_valid: bool = False
    heat_stable: bool = False
    sensor_healthy: bool = True
    is_fresh: bool = True

    @model_validator(mode="after")
    def require_valid_gas_for_classification(self):
        if self.sensor_healthy and (
            self.temperature_c is None or self.humidity_pct is None or self.pressure_pa is None
        ):
            raise ValueError("healthy BME680 data requires temperature, humidity, and pressure")
        if self.gas_risk != Risk.UNAVAILABLE:
            if not self.gas_valid or not self.heat_stable:
                raise ValueError("classified gas risk requires valid, heat-stable BME680 data")
            if self.gas_resistance_ohm is None or self.gas_baseline_ohm is None or self.gas_ratio is None:
                raise ValueError("classified gas risk requires resistance, baseline, and ratio")
        return self


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
    window_ready: bool = False
    model_release_state: ModelReleaseState = ModelReleaseState.UNAVAILABLE
    window_frames: int | None = Field(default=None, ge=1, le=1000)
    selected_subcarriers: int | None = Field(default=None, ge=1, le=256)
    model_version: str | None = Field(default=None, max_length=80)
    amplitude_summary: list[float] | None = Field(default=None, max_length=64)
    motion_rms: float | None = Field(default=None, ge=0)


class SystemReading(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mqtt: ServiceState = ServiceState.UNKNOWN
    local_storage: StorageState = StorageState.UNKNOWN
    node1_status: NodeState = NodeState.UNKNOWN
    node2_status: NodeState = NodeState.UNKNOWN
    output_state: FusionState = FusionState.DEGRADED
    green_led: bool = False
    yellow_led: bool = False
    red_led: bool = False
    buzzer_on: bool = False
    queue_depth: int = Field(default=0, ge=0, le=16)
    csi_drops: int = Field(default=0, ge=0)


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
