from __future__ import annotations

import pytest
from pydantic import ValidationError as PydanticValidationError

from app.scenario.validators import validate_descriptor

VALID_DESCRIPTOR = {
    "version": 1,
    "scenario_name": "osc_follow_leading_vehicle",
    "map_name": "Town01",
    "weather": {"preset": "ClearNoon"},
    "sync": {"enabled": True, "fixed_delta_seconds": 0.05},
    "ego_vehicle": {
        "blueprint": "vehicle.tesla.model3",
        "spawn_point": {
            "x": 230.0,
            "y": 195.0,
            "z": 0.5,
            "roll": 0.0,
            "pitch": 0.0,
            "yaw": 90.0,
        },
    },
    "traffic": {"enabled": False, "num_vehicles": 0, "num_walkers": 0},
    "sensors": {"enabled": False},
    "termination": {"timeout_seconds": 10, "success_condition": "timeout"},
    "recorder": {"enabled": False},
    "metadata": {"author": "test", "tags": ["unit"], "description": "descriptor test"},
}


def test_descriptor_validation_success() -> None:
    descriptor = validate_descriptor(VALID_DESCRIPTOR)
    assert descriptor.scenario_name == "osc_follow_leading_vehicle"
    assert descriptor.sync.fixed_delta_seconds == 0.05
    assert descriptor.debug.viewer_friendly is False


def test_descriptor_validation_failure() -> None:
    bad_payload = {
        **VALID_DESCRIPTOR,
        "termination": {"timeout_seconds": 0, "success_condition": "timeout"},
    }
    with pytest.raises(PydanticValidationError):
        validate_descriptor(bad_payload)


def test_descriptor_validation_with_custom_weather_and_sensors() -> None:
    descriptor = validate_descriptor(
        {
            **VALID_DESCRIPTOR,
            "weather": {
                "preset": "CloudyNoon",
                "cloudiness": 70.0,
                "fog_density": 10.0,
            },
            "sensors": {
                "enabled": True,
                "auto_start": False,
                "profile_name": "front_rgb",
                "sensors": [
                    {
                        "id": "FrontRGB",
                        "type": "sensor.camera.rgb",
                        "x": 1.5,
                        "y": 0.0,
                        "z": 1.7,
                        "width": 1920,
                        "height": 1080,
                        "fov": 90.0,
                    }
                ],
            },
        }
    )

    assert descriptor.weather.cloudiness == 70.0
    assert descriptor.sensors.enabled is True
    assert descriptor.sensors.auto_start is False
    assert descriptor.sensors.profile_name == "front_rgb"
    assert descriptor.sensors.sensors[0].type == "sensor.camera.rgb"


def test_descriptor_validation_rejects_sensor_auto_start_when_disabled() -> None:
    with pytest.raises(PydanticValidationError):
        validate_descriptor(
            {
                **VALID_DESCRIPTOR,
                "sensors": {
                    "enabled": False,
                    "auto_start": True,
                },
            }
        )
