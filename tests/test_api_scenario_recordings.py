from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.api.main import app
from app.core.config import get_settings
from app.core.models import ScenarioRecordingRecord
from app.storage.artifact_store import ArtifactStore
from app.storage.scenario_recording_store import ScenarioRecordingStore
from app.utils.time_utils import now_utc

VALID_DESCRIPTOR = {
    "version": 1,
    "scenario_name": "town10_autonomous_demo",
    "map_name": "Town10HD_Opt",
    "weather": {"preset": "ClearNoon"},
    "sync": {"enabled": True, "fixed_delta_seconds": 0.05},
    "ego_vehicle": {
        "blueprint": "vehicle.lincoln.mkz_2017",
        "spawn_point": {
            "x": 10.0,
            "y": 20.0,
            "z": 0.5,
            "roll": 0.0,
            "pitch": 0.0,
            "yaw": 90.0,
        },
    },
    "traffic": {"enabled": True, "num_vehicles": 6, "num_walkers": 2, "seed": 42},
    "sensors": {"enabled": True, "auto_start": False, "profile_name": "front_rgb", "sensors": []},
    "termination": {"timeout_seconds": 20, "success_condition": "timeout"},
    "recorder": {"enabled": True},
    "metadata": {
        "author": "test",
        "tags": ["api", "corner"],
        "description": "recording asset test",
    },
}


def _create_run(client: TestClient) -> str:
    response = client.post("/runs", json={"descriptor": VALID_DESCRIPTOR})
    assert response.status_code == 200
    return str(response.json()["data"]["run_id"])


def _write_recorder_log(run_id: str) -> Path:
    artifact_store = ArtifactStore(get_settings().artifacts_root)
    recorder_path = artifact_store.run_dir(run_id) / "recorder" / f"{run_id}.log"
    recorder_path.parent.mkdir(parents=True, exist_ok=True)
    recorder_path.write_bytes(b"carla recorder bytes")
    return recorder_path


def _write_sensor_profile() -> None:
    sensor_root = get_settings().sensor_profiles_root
    sensor_root.mkdir(parents=True, exist_ok=True)
    (sensor_root / "front_rgb.yaml").write_text(
        "\n".join(
            [
                "profile_name: front_rgb",
                "display_name: Front RGB",
                "description: baseline front camera",
                "metadata:",
                "  output_mode: carla_live",
                "  hil_output_mode: camera_open_loop",
                "sensors:",
                "  - id: FrontRGB",
                "    type: sensor.camera.rgb",
                "    x: 1.5",
                "    y: 0.0",
                "    z: 1.7",
                "    width: 1920",
                "    height: 1080",
                "    fov: 90.0",
                "  - id: FrontIMU",
                "    type: sensor.other.imu",
                "    x: 0.0",
                "    y: 0.0",
                "    z: 1.6",
            ]
        ),
        encoding="utf-8",
    )


def test_publish_fails_without_recorder_file() -> None:
    client = TestClient(app)
    run_id = _create_run(client)

    response = client.post(
        "/scenario-recordings/from-run",
        json={"run_id": run_id, "tags": ["night"]},
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "VALIDATION_ERROR"


def test_publish_from_run_writes_sqlite_and_is_idempotent() -> None:
    client = TestClient(app)
    run_id = _create_run(client)
    recorder_path = _write_recorder_log(run_id)

    response = client.post(
        "/scenario-recordings/from-run",
        json={
            "run_id": run_id,
            "name": "Town10 asset",
            "duration_seconds": 18.0,
            "source_type": "recorder_run",
            "source_ref": "manual-smoke",
            "carla_version": "0.9.16",
            "map_version": "Town10HD_Opt",
            "recommended_start_seconds": 2.0,
            "recommended_duration_seconds": 10.0,
            "tags": ["night"],
            "corner_case_labels": ["cut-in"],
            "determinism_level": "world_state_replay_with_carla_live_sensors",
        },
    )
    assert response.status_code == 200
    recording = response.json()["data"]
    assert recording["name"] == "Town10 asset"
    assert recording["source_run_id"] == run_id
    assert recording["source_type"] == "recorder_run"
    assert recording["source_ref"] == "manual-smoke"
    assert recording["recorder_log_path"] == str(recorder_path)
    assert recording["recorder_file_size_bytes"] == len(b"carla recorder bytes")
    assert recording["recorder_file_sha256"]
    assert recording["duration_seconds"] == 18.0
    assert recording["recommended_start_seconds"] == 2.0
    assert recording["recommended_duration_seconds"] == 10.0
    assert recording["carla_version"] == "0.9.16"
    assert recording["map_version"] == "Town10HD_Opt"
    assert recording["map_name"] == "Town10HD_Opt"
    assert recording["sensor_profile_name"] == "front_rgb"
    assert recording["traffic_density"]["num_vehicles"] == 6
    assert "night" in recording["tags"]
    assert "cut-in" in recording["corner_case_labels"]

    duplicate_response = client.post(
        "/scenario-recordings/from-run",
        json={"run_id": run_id, "tags": ["ignored"]},
    )
    assert duplicate_response.status_code == 200
    assert duplicate_response.json()["data"]["recording_id"] == recording["recording_id"]
    assert "ignored" not in duplicate_response.json()["data"]["tags"]

    list_response = client.get("/scenario-recordings", params={"tag": "night"})
    assert list_response.status_code == 200
    assert [item["recording_id"] for item in list_response.json()["data"]["recordings"]] == [
        recording["recording_id"]
    ]


def test_launch_replay_requires_sensor_profile_id() -> None:
    client = TestClient(app)
    run_id = _create_run(client)
    _write_recorder_log(run_id)
    publish_response = client.post(
        "/scenario-recordings/from-run",
        json={"run_id": run_id},
    )
    assert publish_response.status_code == 200
    recording = publish_response.json()["data"]

    launch_response = client.post(
        f"/scenario-recordings/{recording['recording_id']}/launch",
        json={
            "start_seconds": 2.0,
            "duration_seconds": 12.0,
            "sensor_mode": "carla_live",
            "auto_start": False,
        },
    )

    assert launch_response.status_code == 422


def test_launch_replay_run_writes_replay_source_and_link() -> None:
    client = TestClient(app)
    _write_sensor_profile()
    run_id = _create_run(client)
    _write_recorder_log(run_id)
    publish_response = client.post(
        "/scenario-recordings/from-run",
        json={"run_id": run_id, "corner_case_labels": ["pedestrian"]},
    )
    assert publish_response.status_code == 200
    recording = publish_response.json()["data"]

    launch_response = client.post(
        f"/scenario-recordings/{recording['recording_id']}/launch",
        json={
            "sensor_profile_id": "front_rgb",
            "preview_sensor_id": "FrontRGB",
            "start_seconds": 2.0,
            "duration_seconds": 12.0,
            "sensor_mode": "carla_live",
            "fixed_delta_seconds": 0.05,
            "sensor_warmup_seconds": 1.5,
            "timebase": "synchronous_fixed_delta",
            "hil_clock_mode": "fixed_delta",
            "auto_start": False,
            "metadata": {"tags": ["replay"], "description": "short replay"},
        },
    )
    assert launch_response.status_code == 200
    run = launch_response.json()["data"]["run"]
    assert run["status"] == "CREATED"
    assert run["hil_config"]["mode"] == "camera_open_loop"
    assert run["scenario_source"]["launch_mode"] == "carla_recorder_replay"
    assert run["scenario_source"]["recording_id"] == recording["recording_id"]
    assert run["scenario_source"]["replay_start_seconds"] == 2.0
    assert run["scenario_source"]["replay_duration_seconds"] == 12.0
    assert run["scenario_source"]["replay_fixed_delta_seconds"] == 0.05
    assert run["scenario_source"]["replay_sensor_mode"] == "carla_live"
    assert run["scenario_source"]["replay_sensors"] is False
    assert run["scenario_source"]["sensor_profile_id"] == "front_rgb"
    assert run["scenario_source"]["sensor_profile_hash"]
    assert run["scenario_source"]["preview_sensor_id"] == "FrontRGB"
    assert run["scenario_source"]["preview_sensor_snapshot"]["id"] == "FrontRGB"
    assert run["scenario_source"]["preview_sensor_snapshot"]["type"] == "sensor.camera.rgb"
    assert run["scenario_source"]["sensor_warmup_seconds"] == 1.5
    assert run["scenario_source"]["timebase"] == "synchronous_fixed_delta"
    assert run["scenario_source"]["hil_clock_mode"] == "fixed_delta"
    assert run["traffic"]["num_vehicles"] == 0
    assert run["recorder"]["enabled"] is False
    assert run["sensors"]["profile_name"] == "front_rgb"
    assert run["sensors"]["auto_start"] is False

    detail_response = client.get(f"/scenario-recordings/{recording['recording_id']}")
    assert detail_response.status_code == 200
    replay_runs = detail_response.json()["data"]["replay_runs"]
    assert replay_runs[0]["run_id"] == run["run_id"]
    assert replay_runs[0]["duration_seconds"] == 12.0
    assert replay_runs[0]["sensor_profile_id"] == "front_rgb"
    assert replay_runs[0]["sensor_profile_hash"] == run["scenario_source"]["sensor_profile_hash"]
    assert replay_runs[0]["preview_sensor_id"] == "FrontRGB"
    assert replay_runs[0]["preview_sensor_snapshot"]["id"] == "FrontRGB"
    assert replay_runs[0]["sensor_warmup_seconds"] == 1.5


def test_launch_replay_rejects_non_rgb_preview_sensor() -> None:
    client = TestClient(app)
    _write_sensor_profile()
    run_id = _create_run(client)
    _write_recorder_log(run_id)
    publish_response = client.post(
        "/scenario-recordings/from-run",
        json={"run_id": run_id},
    )
    assert publish_response.status_code == 200
    recording = publish_response.json()["data"]

    launch_response = client.post(
        f"/scenario-recordings/{recording['recording_id']}/launch",
        json={
            "sensor_profile_id": "front_rgb",
            "preview_sensor_id": "FrontIMU",
            "start_seconds": 2.0,
            "duration_seconds": 12.0,
            "sensor_warmup_seconds": 1.0,
            "auto_start": False,
        },
    )

    assert launch_response.status_code == 422
    assert launch_response.json()["detail"]["code"] == "VALIDATION_ERROR"
    assert "sensor.camera.rgb" in launch_response.json()["detail"]["message"]


def test_launch_offline_imported_recording_without_source_run() -> None:
    client = TestClient(app)
    _write_sensor_profile()
    settings = get_settings()
    recorder_path = settings.scenario_recordings_root / "offline_asset.log"
    recorder_path.parent.mkdir(parents=True, exist_ok=True)
    recorder_path.write_bytes(b"offline carla recorder bytes")
    timestamp = now_utc()
    store = ScenarioRecordingStore(settings.scenario_recordings_root)
    store.create(
        ScenarioRecordingRecord(
            recording_id="offline_asset",
            name="Offline Asset",
            source_run_id="offline_import_missing_run",
            source_run_status="IMPORTED",
            source_type="carla_recorder_log",
            source_ref=str(recorder_path),
            scenario_name="unregistered_source_scenario",
            map_name="Town10HD_Opt",
            recorder_log_path=str(recorder_path),
            recorder_file_size_bytes=recorder_path.stat().st_size,
            recorder_file_sha256="abc123",
            duration_seconds=20.0,
            recommended_start_seconds=2.0,
            recommended_duration_seconds=10.0,
            tags=["offline"],
            created_at=timestamp,
            updated_at=timestamp,
        )
    )

    launch_response = client.post(
        "/scenario-recordings/offline_asset/launch",
        json={
            "sensor_profile_id": "front_rgb",
            "start_seconds": 2.0,
            "duration_seconds": 10.0,
            "sensor_warmup_seconds": 1.0,
            "auto_start": False,
        },
    )

    assert launch_response.status_code == 200
    run = launch_response.json()["data"]["run"]
    assert run["status"] == "CREATED"
    assert run["scenario_name"] == "free_drive_sensor_collection"
    assert run["hil_config"]["mode"] == "camera_open_loop"
    assert run["scenario_source"]["recording_id"] == "offline_asset"
    assert run["scenario_source"]["sensor_profile_id"] == "front_rgb"
    assert run["scenario_source"]["preview_sensor_id"] == "FrontRGB"
    assert run["scenario_source"]["preview_sensor_snapshot"]["type"] == "sensor.camera.rgb"
    assert run["metadata"]["asset_scenario_name"] == "unregistered_source_scenario"
