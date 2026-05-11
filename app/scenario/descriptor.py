from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator


class SpawnPoint(BaseModel):
    x: float
    y: float
    z: float
    roll: float = 0.0
    pitch: float = 0.0
    yaw: float = 0.0


class WeatherConfig(BaseModel):
    preset: str = "ClearNoon"
    cloudiness: float | None = Field(default=None, ge=0.0, le=100.0)
    precipitation: float | None = Field(default=None, ge=0.0, le=100.0)
    precipitation_deposits: float | None = Field(default=None, ge=0.0, le=100.0)
    wind_intensity: float | None = Field(default=None, ge=0.0, le=100.0)
    wetness: float | None = Field(default=None, ge=0.0, le=100.0)
    fog_density: float | None = Field(default=None, ge=0.0, le=100.0)
    sun_altitude_angle: float | None = Field(default=None, ge=-90.0, le=90.0)
    sun_azimuth_angle: float | None = Field(default=None, ge=0.0, le=360.0)

    @field_validator("preset")
    @classmethod
    def validate_preset(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("weather.preset must not be empty")
        return value.strip()

    def to_runtime_payload(self) -> dict[str, Any]:
        return self.model_dump(mode="python", exclude_none=True)


class SyncConfig(BaseModel):
    enabled: bool = True
    fixed_delta_seconds: float = 0.05

    @field_validator("fixed_delta_seconds")
    @classmethod
    def validate_fixed_delta_seconds(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("fixed_delta_seconds must be > 0")
        if value > 0.2:
            raise ValueError("fixed_delta_seconds should be <= 0.2 for stable control")
        return value


class EgoVehicleConfig(BaseModel):
    blueprint: str = "vehicle.tesla.model3"
    spawn_point: SpawnPoint


class TrafficConfig(BaseModel):
    enabled: bool = False
    num_vehicles: int = 0
    num_walkers: int = 0
    seed: int | None = Field(default=None, ge=0, le=2147483647)
    injection_mode: str | None = None

    @field_validator("num_vehicles", "num_walkers")
    @classmethod
    def validate_non_negative(cls, value: int) -> int:
        if value < 0:
            raise ValueError("traffic counts must be non-negative")
        return value

    @field_validator("injection_mode")
    @classmethod
    def validate_injection_mode(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


class SensorsConfig(BaseModel):
    enabled: bool = False
    auto_start: bool = False
    profile_name: str | None = None
    config_yaml_path: str | None = None
    sensors: list[SensorSpec] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_enabled_state(self) -> SensorsConfig:
        if self.enabled and not self.sensors and not self.profile_name:
            raise ValueError("enabled sensors require sensors[] or profile_name")
        if self.auto_start and not self.enabled:
            raise ValueError("auto_start sensors require sensors.enabled=true")
        return self


class SensorSpec(BaseModel):
    id: str
    type: str
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    roll: float = 0.0
    pitch: float = 0.0
    yaw: float = 0.0
    width: int | None = Field(default=None, ge=1)
    height: int | None = Field(default=None, ge=1)
    fov: float | None = Field(default=None, gt=0.0, le=180.0)
    horizontal_fov: float | None = Field(default=None, gt=0.0, le=180.0)
    vertical_fov: float | None = Field(default=None, gt=0.0, le=180.0)
    range: float | None = Field(default=None, gt=0.0)
    channels: int | None = Field(default=None, ge=1)
    points_per_second: int | None = Field(default=None, ge=1)
    rotation_frequency: float | None = Field(default=None, gt=0.0)
    reading_frequency: float | None = Field(default=None, gt=0.0)
    attributes: dict[str, Any] = Field(default_factory=dict)

    @field_validator("id", "type")
    @classmethod
    def validate_required_text(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("sensor field must not be empty")
        return value.strip()


class TerminationConfig(BaseModel):
    timeout_seconds: int = 30
    success_condition: str = "timeout"

    @field_validator("timeout_seconds")
    @classmethod
    def validate_timeout_seconds(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("timeout_seconds must be > 0")
        return value


class RecorderConfig(BaseModel):
    enabled: bool = False


class DebugConfig(BaseModel):
    viewer_friendly: bool = False


class MetadataConfig(BaseModel):
    author: str = "unknown"
    tags: list[str] = Field(default_factory=list)
    description: str = ""
    dut_model: str | None = None


class ScenarioDescriptor(BaseModel):
    version: int = 1
    scenario_name: str
    map_name: str
    weather: WeatherConfig = Field(default_factory=WeatherConfig)
    sync: SyncConfig = Field(default_factory=SyncConfig)
    ego_vehicle: EgoVehicleConfig
    traffic: TrafficConfig = Field(default_factory=TrafficConfig)
    sensors: SensorsConfig = Field(default_factory=SensorsConfig)
    termination: TerminationConfig = Field(default_factory=TerminationConfig)
    recorder: RecorderConfig = Field(default_factory=RecorderConfig)
    debug: DebugConfig = Field(default_factory=DebugConfig)
    metadata: MetadataConfig = Field(default_factory=MetadataConfig)

    @field_validator("scenario_name", "map_name")
    @classmethod
    def validate_non_empty_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("field must not be empty")
        return value

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


SensorsConfig.model_rebuild()
