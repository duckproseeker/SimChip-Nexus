from __future__ import annotations

import base64
import io
import json
import zipfile
from pathlib import Path

from fastapi.testclient import TestClient

from app.api import routes_runs
from app.api.carla_worker_runner import CarlaWorkerError
from app.api.main import app
from app.core.config import get_settings
from app.core.models import EventLevel, RunEvent, RunStatus
from app.storage.artifact_store import ArtifactStore
from app.storage.run_control_store import RunControlStore
from app.storage.run_store import RunStore
from app.utils.time_utils import now_utc


def _write_fake_sensor_capture_outputs(output_root: Path) -> None:
    worker_root = output_root / "_worker"
    worker_root.mkdir(parents=True, exist_ok=True)
    (output_root / "manifest.json").write_text(
        json.dumps(
            {
                "profile_name": "front_rgb",
                "hero_role_name": "hero",
                "sensors": [
                    {"id": "FrontRGB", "type": "sensor.camera.rgb"},
                    {"id": "FrontIMU", "type": "sensor.other.imu"},
                ],
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (worker_root / "state.json").write_text(
        json.dumps({"status": "ready", "sensor_count": 2}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    (worker_root / "worker.log").write_text(
        "\n".join(
            [
                "boot",
                "connect",
                "attach FrontRGB",
                "attach FrontIMU",
                "record frame 1",
                "record frame 2",
                "flush manifest",
                "ready",
            ]
        ),
        encoding="utf-8",
    )

    front_rgb_dir = output_root / "FrontRGB"
    front_rgb_dir.mkdir(parents=True, exist_ok=True)
    (front_rgb_dir / "frame_000001.png").write_bytes(b"png-one")
    (front_rgb_dir / "frame_000002.png").write_bytes(b"png-two")

    front_imu_dir = output_root / "FrontIMU"
    front_imu_dir.mkdir(parents=True, exist_ok=True)
    (front_imu_dir / "records.jsonl").write_text(
        "\n".join(
            [
                json.dumps({"frame": 1, "timestamp": 1.0}, ensure_ascii=False),
                json.dumps({"frame": 2, "timestamp": 2.0}, ensure_ascii=False),
            ]
        )
        + "\n",
        encoding="utf-8",
    )


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
    "metadata": {"author": "test", "tags": ["api"], "description": "api test"},
}


def test_create_start_stop_run() -> None:
    client = TestClient(app)

    create_resp = client.post("/runs", json={"descriptor": VALID_DESCRIPTOR})
    assert create_resp.status_code == 200
    run_id = create_resp.json()["data"]["run_id"]

    start_resp = client.post(f"/runs/{run_id}/start")
    assert start_resp.status_code == 200
    assert start_resp.json()["data"]["status"] == "QUEUED"
    assert "created_at_utc" in start_resp.json()["data"]
    assert "updated_at_utc" in start_resp.json()["data"]
    assert "started_at_utc" in start_resp.json()["data"]
    assert "sim_time" in start_resp.json()["data"]
    assert "executed_tick_count" in start_resp.json()["data"]
    assert "achieved_tick_rate_hz" in start_resp.json()["data"]
    assert "wall_elapsed_seconds" in start_resp.json()["data"]

    stop_resp = client.post(f"/runs/{run_id}/stop")
    assert stop_resp.status_code == 200
    assert stop_resp.json()["data"]["status"] == "CANCELED"

    get_resp = client.get(f"/runs/{run_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["data"]["status"] == "CANCELED"
    assert "started_at_utc" in get_resp.json()["data"]
    assert "ended_at_utc" in get_resp.json()["data"]

    events_resp = client.get(f"/runs/{run_id}/events")
    assert events_resp.status_code == 200
    assert len(events_resp.json()["data"]) >= 2


def test_create_run_with_hil_config_and_evaluation_profile() -> None:
    client = TestClient(app)

    register_resp = client.post(
        "/gateways/register",
        json={
            "gateway_id": "rpi5-x1301-01",
            "name": "bench-a",
            "capabilities": {
                "video_input_modes": ["hdmi_x1301", "frame_stream"],
                "dut_output_modes": ["uvc_gadget"],
            },
        },
    )
    assert register_resp.status_code == 200

    create_resp = client.post(
        "/runs",
        json={
            "descriptor": VALID_DESCRIPTOR,
            "hil_config": {
                "mode": "camera_open_loop",
                "gateway_id": "rpi5-x1301-01",
                "video_source": "hdmi_x1301",
                "dut_input_mode": "uvc_camera",
                "result_ingest_mode": "http_push",
            },
            "evaluation_profile": {
                "profile_name": "yolo_open_loop_v1",
                "metrics": ["precision", "recall"],
                "iou_threshold": 0.5,
                "classes": ["car"],
            },
        },
    )
    assert create_resp.status_code == 200

    run_id = create_resp.json()["data"]["run_id"]
    get_resp = client.get(f"/runs/{run_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["data"]["hil_config"]["gateway_id"] == "rpi5-x1301-01"
    assert get_resp.json()["data"]["evaluation_profile"]["profile_name"] == "yolo_open_loop_v1"


def test_create_run_allows_hil_config_without_gateway_id() -> None:
    client = TestClient(app)

    create_resp = client.post(
        "/runs",
        json={
            "descriptor": VALID_DESCRIPTOR,
            "hil_config": {
                "mode": "camera_open_loop",
                "video_source": "hdmi_x1301",
                "dut_input_mode": "uvc_camera",
                "result_ingest_mode": "http_push",
            },
        },
    )
    assert create_resp.status_code == 200

    run_id = create_resp.json()["data"]["run_id"]
    assert create_resp.json()["data"]["hil_config"]["gateway_id"] is None

    get_resp = client.get(f"/runs/{run_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["data"]["hil_config"]["gateway_id"] is None


def test_get_run_includes_run_scoped_device_metrics() -> None:
    client = TestClient(app)

    register_resp = client.post(
        "/gateways/register",
        json={
            "gateway_id": "rpi5-x1301-01",
            "name": "bench-a",
            "capabilities": {"video_input_modes": ["hdmi_x1301"]},
        },
    )
    assert register_resp.status_code == 200

    create_resp = client.post(
        "/runs",
        json={
            "descriptor": VALID_DESCRIPTOR,
            "hil_config": {
                "mode": "camera_open_loop",
                "gateway_id": "rpi5-x1301-01",
                "video_source": "hdmi_x1301",
                "dut_input_mode": "uvc_camera",
                "result_ingest_mode": "http_push",
            },
        },
    )
    assert create_resp.status_code == 200
    run_id = create_resp.json()["data"]["run_id"]

    heartbeat_resp = client.post(
        "/gateways/rpi5-x1301-01/heartbeat",
        json={
            "status": "READY",
            "metrics": {
                "dut_model_name": "yolov4-tiny",
                "output_fps": 10.9,
                "avg_latency_ms": 55.1,
                "detection_count": 1320,
            },
            "current_run_id": run_id,
        },
    )
    assert heartbeat_resp.status_code == 200

    get_resp = client.get(f"/runs/{run_id}")
    assert get_resp.status_code == 200
    payload = get_resp.json()["data"]
    assert payload["device_metrics"]["gateway_id"] == "rpi5-x1301-01"
    assert payload["device_metrics"]["dut_model_name"] == "yolov4-tiny"
    assert payload["device_metrics"]["output_fps"] == 10.9
    assert payload["device_metrics"]["detection_count"] == 1320


def test_get_run_environment_for_native_run() -> None:
    client = TestClient(app)

    create_resp = client.post("/runs", json={"descriptor": VALID_DESCRIPTOR})
    assert create_resp.status_code == 200
    run_id = create_resp.json()["data"]["run_id"]

    get_resp = client.get(f"/runs/{run_id}/environment")
    assert get_resp.status_code == 200
    assert get_resp.json()["data"]["runtime_control"]["sensor_capture"]["enabled"] is False
    assert get_resp.json()["data"]["descriptor_weather"]["preset"] == "ClearNoon"
    assert get_resp.json()["data"]["runtime_control"]["weather"] is None
    assert get_resp.json()["data"]["runtime_control"]["debug"] is None
    assert get_resp.json()["data"]["runtime_control"]["sensor_capture"]["status"] == "DISABLED"
    assert get_resp.json()["data"]["runtime_control"]["recorder"]["status"] == "DISABLED"


def test_native_run_sensor_capture_start_is_rejected() -> None:
    client = TestClient(app)

    create_resp = client.post(
        "/runs",
        json={
            "descriptor": {
                **VALID_DESCRIPTOR,
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
                            "z": 1.6,
                            "width": 1280,
                            "height": 720,
                            "fov": 90.0,
                        }
                    ],
                },
                "recorder": {"enabled": True},
            }
        },
    )
    assert create_resp.status_code == 200
    run_id = create_resp.json()["data"]["run_id"]

    settings = get_settings()
    run_store = RunStore(settings.runs_root)
    run_store.transition(run_id, RunStatus.QUEUED)
    run_store.transition(run_id, RunStatus.STARTING, set_started_at=True)
    run_store.transition(run_id, RunStatus.RUNNING, set_started_at=True)

    environment_resp = client.get(f"/runs/{run_id}/environment")
    assert environment_resp.status_code == 200
    environment_payload = environment_resp.json()["data"]["runtime_control"]
    assert environment_payload["sensor_capture"]["enabled"] is True
    assert environment_payload["sensor_capture"]["auto_start"] is False
    assert environment_payload["sensor_capture"]["desired_state"] == "STOPPED"
    assert environment_payload["sensor_capture"]["status"] == "STOPPED"
    assert environment_payload["recorder"]["enabled"] is True
    assert environment_payload["recorder"]["status"] == "STOPPED"

    start_resp = client.post(f"/runs/{run_id}/sensor-capture/start")
    assert start_resp.status_code == 409
    assert start_resp.json()["detail"]["code"] == "RUN_SENSOR_CAPTURE_UNSUPPORTED"


def test_run_environment_includes_sensor_capture_artifacts_and_download() -> None:
    client = TestClient(app)

    create_resp = client.post(
        "/runs",
        json={
            "descriptor": {
                **VALID_DESCRIPTOR,
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
                            "z": 1.6,
                            "width": 1280,
                            "height": 720,
                            "fov": 90.0,
                        },
                        {
                            "id": "FrontIMU",
                            "type": "sensor.other.imu",
                            "x": 0.0,
                            "y": 0.0,
                            "z": 1.6,
                        },
                    ],
                },
                "recorder": {"enabled": True},
            }
        },
    )
    assert create_resp.status_code == 200
    run_id = create_resp.json()["data"]["run_id"]

    settings = get_settings()
    control_store = RunControlStore(settings.controls_root)
    output_root = settings.artifacts_root / run_id / "outputs" / "sensors"
    _write_fake_sensor_capture_outputs(output_root)
    control_store.update(
        run_id,
        {
            "sensor_capture": {
                "status": "RUNNING",
                "active": True,
                "desired_state": "RUNNING",
                "last_error": "worker restarted once",
            },
            "recorder": {
                "status": "RUNNING",
                "active": True,
            },
        },
    )

    environment_resp = client.get(f"/runs/{run_id}/environment")
    assert environment_resp.status_code == 200
    runtime_control = environment_resp.json()["data"]["runtime_control"]
    sensor_capture = runtime_control["sensor_capture"]
    assert sensor_capture["status"] == "RUNNING"
    assert sensor_capture["active"] is True
    assert sensor_capture["saved_frames"] == 2
    assert sensor_capture["saved_samples"] == 4
    assert sensor_capture["manifest"]["profile_name"] == "front_rgb"
    assert sensor_capture["manifest_path"] == str(output_root / "manifest.json")
    assert sensor_capture["worker_state_path"] == str(output_root / "_worker" / "state.json")
    assert sensor_capture["worker_log_path"] == str(output_root / "_worker" / "worker.log")
    assert "ready" in str(sensor_capture["worker_log_tail"])
    assert sensor_capture["download_url"] == f"/runs/{run_id}/sensor-capture/download"
    assert len(sensor_capture["sensor_outputs"]) == 2
    front_rgb_summary = next(
        item for item in sensor_capture["sensor_outputs"] if item["sensor_id"] == "FrontRGB"
    )
    assert front_rgb_summary["frame_file_count"] == 2
    assert front_rgb_summary["record_count"] == 0
    assert str(front_rgb_summary["latest_artifact_path"]).startswith("FrontRGB/frame_")
    front_imu_summary = next(
        item for item in sensor_capture["sensor_outputs"] if item["sensor_id"] == "FrontIMU"
    )
    assert front_imu_summary["frame_file_count"] == 0
    assert front_imu_summary["record_count"] == 2
    assert runtime_control["recorder"]["status"] == "RUNNING"
    assert runtime_control["recorder"]["output_path"].endswith(f"/{run_id}.log")

    download_resp = client.get(sensor_capture["download_url"])
    assert download_resp.status_code == 200
    assert download_resp.headers["content-type"] == "application/zip"
    archive = zipfile.ZipFile(io.BytesIO(download_resp.content))
    assert sorted(archive.namelist()) == [
        "sensors/FrontIMU/records.jsonl",
        "sensors/FrontRGB/frame_000001.png",
        "sensors/FrontRGB/frame_000002.png",
        "sensors/_worker/state.json",
        "sensors/_worker/worker.log",
        "sensors/manifest.json",
    ]


def test_run_viewer_info_on_created_run() -> None:
    client = TestClient(app)

    create_resp = client.post("/runs", json={"descriptor": VALID_DESCRIPTOR})
    assert create_resp.status_code == 200
    run_id = create_resp.json()["data"]["run_id"]

    viewer_resp = client.get(f"/runs/{run_id}/viewer")
    assert viewer_resp.status_code == 200
    payload = viewer_resp.json()["data"]
    assert payload["available"] is False
    assert len(payload["views"]) >= 2
    assert payload["snapshot_url"].endswith("/viewer/frame")
    assert payload["stream_ws_path"].endswith("/ws/runs/" + run_id + "/viewer")
    assert payload["playback_interval_ms"] >= payload["stream_interval_ms"]
    assert payload["stream_buffer_min_frames"] >= 1
    assert payload["stream_buffer_max_frames"] > payload["stream_buffer_min_frames"]

    frame_resp = client.get(f"/runs/{run_id}/viewer/frame")
    assert frame_resp.status_code == 409


def test_run_viewer_waits_for_ego_during_starting_run() -> None:
    client = TestClient(app)

    create_resp = client.post("/runs", json={"descriptor": VALID_DESCRIPTOR})
    assert create_resp.status_code == 200
    run_id = create_resp.json()["data"]["run_id"]

    settings = get_settings()
    run_store = RunStore(settings.runs_root)
    artifact_store = ArtifactStore(settings.artifacts_root)
    run_store.transition(run_id, RunStatus.QUEUED)
    run_store.transition(run_id, RunStatus.STARTING, set_started_at=True)

    viewer_resp = client.get(f"/runs/{run_id}/viewer")
    assert viewer_resp.status_code == 200
    payload = viewer_resp.json()["data"]
    assert payload["available"] is False
    assert "等待 ego" in payload["reason"]

    frame_resp = client.get(f"/runs/{run_id}/viewer/frame")
    assert frame_resp.status_code == 409
    assert "等待 ego" in frame_resp.json()["detail"]["message"]

    artifact_store.append_event(
        RunEvent(
            timestamp=now_utc(),
            run_id=run_id,
            level=EventLevel.INFO,
            event_type="EGO_SPAWNED",
            message="hero ready",
            payload={"actor_id": 42},
        )
    )

    viewer_ready_resp = client.get(f"/runs/{run_id}/viewer")
    assert viewer_ready_resp.status_code == 200
    assert viewer_ready_resp.json()["data"]["available"] is True


def test_run_viewer_frame_returns_png_from_worker(monkeypatch) -> None:
    client = TestClient(app)

    create_resp = client.post("/runs", json={"descriptor": VALID_DESCRIPTOR})
    assert create_resp.status_code == 200
    run_id = create_resp.json()["data"]["run_id"]

    settings = get_settings()
    run_store = RunStore(settings.runs_root)
    artifact_store = ArtifactStore(settings.artifacts_root)
    run_store.transition(run_id, RunStatus.QUEUED)
    run_store.transition(run_id, RunStatus.STARTING, set_started_at=True)
    artifact_store.append_event(
        RunEvent(
            timestamp=now_utc(),
            run_id=run_id,
            level=EventLevel.INFO,
            event_type="EGO_SPAWNED",
            message="hero ready",
            payload={"actor_id": 42},
        )
    )
    run_store.transition(run_id, RunStatus.RUNNING)

    expected_png = b"\x89PNG\r\n\x1a\nviewer-frame"
    monkeypatch.setattr(
        routes_runs,
        "run_carla_worker",
        lambda *args, **kwargs: {
            "ok": True,
            "image_base64": base64.b64encode(expected_png).decode("ascii"),
        },
    )

    frame_resp = client.get(f"/runs/{run_id}/viewer/frame")

    assert frame_resp.status_code == 200
    assert frame_resp.headers["content-type"] == "image/png"
    assert frame_resp.content == expected_png


def test_run_viewer_frame_returns_503_when_worker_fails(monkeypatch) -> None:
    client = TestClient(app)

    create_resp = client.post("/runs", json={"descriptor": VALID_DESCRIPTOR})
    assert create_resp.status_code == 200
    run_id = create_resp.json()["data"]["run_id"]

    settings = get_settings()
    run_store = RunStore(settings.runs_root)
    artifact_store = ArtifactStore(settings.artifacts_root)
    run_store.transition(run_id, RunStatus.QUEUED)
    run_store.transition(run_id, RunStatus.STARTING, set_started_at=True)
    artifact_store.append_event(
        RunEvent(
            timestamp=now_utc(),
            run_id=run_id,
            level=EventLevel.INFO,
            event_type="EGO_SPAWNED",
            message="hero ready",
            payload={"actor_id": 42},
        )
    )
    run_store.transition(run_id, RunStatus.RUNNING)

    def raise_worker_error(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise CarlaWorkerError(status_code=503, detail="viewer worker timed out")

    monkeypatch.setattr(routes_runs, "run_carla_worker", raise_worker_error)

    frame_resp = client.get(f"/runs/{run_id}/viewer/frame")

    assert frame_resp.status_code == 503
    assert frame_resp.json()["detail"]["code"] == "RUN_VIEWER_UNAVAILABLE"
    assert "viewer worker timed out" in frame_resp.json()["detail"]["message"]


def test_run_viewer_stream_uses_persistent_worker(monkeypatch) -> None:
    client = TestClient(app)

    create_resp = client.post("/runs", json={"descriptor": VALID_DESCRIPTOR})
    assert create_resp.status_code == 200
    run_id = create_resp.json()["data"]["run_id"]

    settings = get_settings()
    run_store = RunStore(settings.runs_root)
    artifact_store = ArtifactStore(settings.artifacts_root)
    run_store.transition(run_id, RunStatus.QUEUED)
    run_store.transition(run_id, RunStatus.STARTING, set_started_at=True)
    artifact_store.append_event(
        RunEvent(
            timestamp=now_utc(),
            run_id=run_id,
            level=EventLevel.INFO,
            event_type="EGO_SPAWNED",
            message="hero ready",
            payload={"actor_id": 42},
        )
    )
    run_store.transition(run_id, RunStatus.RUNNING)

    expected_png = b"\x89PNG\r\n\x1a\nviewer-stream"
    frame_line = (
        json.dumps(
            {
                "ok": True,
                "mime": "image/png",
                "image_base64": base64.b64encode(expected_png).decode("ascii"),
            }
        )
        + "\n"
    ).encode("utf-8")

    class FakeStdout:
        def __init__(self, chunks: list[bytes]) -> None:
            self._chunks = list(chunks)

        async def read(self, _n: int = -1) -> bytes:
            if self._chunks:
                return self._chunks.pop(0)
            return b""

    class FakeStderr:
        async def read(self) -> bytes:
            return b""

    class FakeProcess:
        def __init__(self) -> None:
            self.stdout = FakeStdout([frame_line])
            self.stderr = FakeStderr()
            self.returncode: int | None = None
            self.terminated = False
            self.killed = False

        def terminate(self) -> None:
            self.terminated = True
            self.returncode = 0

        def kill(self) -> None:
            self.killed = True
            self.returncode = -9

        async def wait(self) -> int:
            self.returncode = 0
            return 0

    created: dict[str, FakeProcess] = {}

    async def fake_create_subprocess_exec(*args, **kwargs):  # type: ignore[no-untyped-def]
        process = FakeProcess()
        created["process"] = process
        return process

    monkeypatch.setattr(routes_runs.asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    with client.websocket_connect(f"/ws/runs/{run_id}/viewer?view=third_person") as websocket:
        payload = websocket.receive_json()

    assert payload["type"] == "frame"
    assert payload["mime"] == "image/png"
    assert payload["image_base64"] == base64.b64encode(expected_png).decode("ascii")
    assert created["process"].terminated is True


def test_start_run_rejects_when_another_run_is_active() -> None:
    client = TestClient(app)

    first_resp = client.post("/runs", json={"descriptor": VALID_DESCRIPTOR})
    second_resp = client.post("/runs", json={"descriptor": VALID_DESCRIPTOR})
    assert first_resp.status_code == 200
    assert second_resp.status_code == 200

    first_run_id = first_resp.json()["data"]["run_id"]
    second_run_id = second_resp.json()["data"]["run_id"]

    start_first_resp = client.post(f"/runs/{first_run_id}/start")
    assert start_first_resp.status_code == 200
    assert start_first_resp.json()["data"]["status"] == "QUEUED"

    start_second_resp = client.post(f"/runs/{second_run_id}/start")
    assert start_second_resp.status_code == 409
    assert "已有活跃运行" in start_second_resp.json()["detail"]["message"]


def test_update_run_environment_updates_native_run(tmp_path, monkeypatch) -> None:
    scenario_runner_root = tmp_path / "scenario_runner"
    (scenario_runner_root / "srunner" / "examples").mkdir(parents=True, exist_ok=True)
    (scenario_runner_root / "scenario_runner.py").write_text(
        "#!/usr/bin/env python3\n", encoding="utf-8"
    )
    (scenario_runner_root / "srunner" / "examples" / "FollowLeadingVehicle.xosc").write_text(
        "\n".join(
            [
                '<?xml version="1.0" encoding="UTF-8"?>',
                "<OpenSCENARIO>",
                '  <RoadNetwork><LogicFile filepath="Town01"/></RoadNetwork>',
                "  <Entities>",
                '    <ScenarioObject name="hero"><Vehicle name="vehicle.lincoln.mkz_2017" vehicleCategory="car"/></ScenarioObject>',
                "  </Entities>",
                "  <Storyboard/>",
                "</OpenSCENARIO>",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("SCENARIO_RUNNER_ROOT", str(scenario_runner_root))
    get_settings.cache_clear()

    client = TestClient(app)
    create_resp = client.post(
        "/runs",
        json={
            "descriptor": {
                **VALID_DESCRIPTOR,
                "scenario_name": "osc_follow_leading_vehicle",
                "map_name": "Town01",
            }
        },
    )
    assert create_resp.status_code == 200
    run_id = create_resp.json()["data"]["run_id"]

    update_resp = client.post(
        f"/runs/{run_id}/environment",
        json={
            "weather": {"preset": "CloudyNoon"},
            "debug": {"viewer_friendly": True},
        },
    )
    assert update_resp.status_code == 200
    payload = update_resp.json()["data"]
    assert payload["weather"]["preset"] == "CloudyNoon"
    assert payload["descriptor_debug"]["viewer_friendly"] is True
