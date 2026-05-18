from __future__ import annotations

from fastapi.testclient import TestClient

from app.api.main import app
from app.core.config import get_settings


def _sensor_payload(profile_id: str = "front_rgb") -> dict[str, object]:
    return {
        "sensor_profile_id": profile_id,
        "name": "Front RGB",
        "description": "baseline camera profile",
        "vehicle_model": "vehicle.lincoln.mkz_2017",
        "fixed_delta_seconds": 0.05,
        "expected_fps": 20.0,
        "output_mode": "carla_live",
        "hil_output_mode": "camera_open_loop",
        "metadata": {"category": "baseline"},
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
    }


def test_sensor_profiles_import_yaml_and_return_stable_hash() -> None:
    settings = get_settings()
    settings.sensor_profiles_root.mkdir(parents=True, exist_ok=True)
    (settings.sensor_profiles_root / "front_rgb.yaml").write_text(
        "\n".join(
            [
                "profile_name: front_rgb",
                "display_name: Front RGB",
                "description: legacy yaml profile",
                "sensors:",
                "  - id: FrontRGB",
                "    type: sensor.camera.rgb",
                "    x: 1.5",
                "    y: 0.0",
                "    z: 1.7",
                "    width: 1920",
                "    height: 1080",
                "    fov: 90.0",
            ]
        ),
        encoding="utf-8",
    )
    client = TestClient(app)

    first = client.get("/sensor-profiles")
    second = client.get("/sensor-profiles")

    assert first.status_code == 200
    assert second.status_code == 200
    first_item = first.json()["data"]["items"][0]
    second_item = second.json()["data"]["items"][0]
    assert first_item["sensor_profile_id"] == "front_rgb"
    assert first_item["profile_hash"] == second_item["profile_hash"]
    assert first_item["fixed_delta_seconds"] == 0.05
    assert first_item["expected_fps"] == 20.0


def test_sensor_profiles_create_update_copy() -> None:
    client = TestClient(app)

    create = client.post("/sensor-profiles", json=_sensor_payload())
    assert create.status_code == 200, create.text
    created = create.json()["data"]
    assert created["sensor_profile_id"] == "front_rgb"
    assert created["profile_hash"]

    update_payload = _sensor_payload()
    update_payload["name"] = "Front RGB Updated"
    update_payload["fixed_delta_seconds"] = 0.1
    update_payload["expected_fps"] = 10.0
    update = client.put("/sensor-profiles/front_rgb", json=update_payload)
    assert update.status_code == 200, update.text
    updated = update.json()["data"]
    assert updated["name"] == "Front RGB Updated"
    assert updated["profile_hash"] != created["profile_hash"]

    copied = client.post(
        "/sensor-profiles/front_rgb/copy",
        json={"sensor_profile_id": "front_rgb_copy", "name": "Front RGB Copy"},
    )
    assert copied.status_code == 200, copied.text
    copy_data = copied.json()["data"]
    assert copy_data["sensor_profile_id"] == "front_rgb_copy"
    assert copy_data["profile_hash"] == updated["profile_hash"]
