from __future__ import annotations

from fastapi.testclient import TestClient

from app.api.main import app
from app.core.config import get_settings
from app.core.models import RunStatus
from app.storage.run_store import RunStore
from app.utils.time_utils import now_utc


def test_list_projects_and_benchmark_definitions() -> None:
    client = TestClient(app)

    projects_resp = client.get("/projects")
    definitions_resp = client.get("/benchmark-definitions")

    assert projects_resp.status_code == 200
    assert definitions_resp.status_code == 200
    project_ids = {item["project_id"] for item in projects_resp.json()["data"]["projects"]}
    definition_ids = {
        item["benchmark_definition_id"] for item in definitions_resp.json()["data"]["definitions"]
    }
    assert "baseline-validation" in project_ids
    assert "perception-baseline" in definition_ids
    assert "custom-suite" in definition_ids
    perception_definition = next(
        item
        for item in definitions_resp.json()["data"]["definitions"]
        if item["benchmark_definition_id"] == "perception-baseline"
    )
    assert perception_definition["planning_mode"] == "single_scenario"
    assert perception_definition["default_project_id"] == "baseline-validation"


def test_project_workspace_endpoint() -> None:
    client = TestClient(app)

    response = client.get("/projects/baseline-validation/workspace")

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["project"]["project_id"] == "baseline-validation"
    assert payload["summary"]["benchmark_definition_count"] == 1
    assert isinstance(payload["benchmark_definitions"], list)
    assert {item["benchmark_definition_id"] for item in payload["benchmark_definitions"]} == {
        "perception-baseline"
    }
    assert isinstance(payload["scenario_presets"], list)
    assert payload["scenario_presets"]
    assert any(
        item["scenario_id"] == "town10_autonomous_demo"
        for item in payload["scenario_presets"]
    )
    assert not any(
        item["scenario_id"] == "osc_follow_leading_vehicle"
        for item in payload["scenario_presets"]
    )
    assert all(
        item["execution_support"] == "native" for item in payload["scenario_presets"]
    )


def test_create_benchmark_task_and_export_report() -> None:
    client = TestClient(app)

    task_resp = client.post(
        "/benchmark-tasks",
        json={
            "project_id": "baseline-validation",
            "benchmark_definition_id": "perception-baseline",
            "dut_model": "演示开发板",
            "scenario_matrix": [
                {
                    "scenario_id": "osc_follow_leading_vehicle",
                    "map_name": "Town01",
                }
            ],
            "evaluation_profile_name": "yolo_open_loop_v1",
            "auto_start": False,
        },
    )

    assert task_resp.status_code == 200
    task_payload = task_resp.json()["data"]
    assert task_payload["project_id"] == "baseline-validation"
    assert task_payload["benchmark_definition_id"] == "perception-baseline"
    assert task_payload["dut_model"] == "演示开发板"
    assert task_payload["status"] == "CREATED"
    assert task_payload["planned_run_count"] == 1
    assert task_payload["scenario_matrix"][0]["resolved_map_name"] == "Town01"
    assert task_payload["scenario_matrix"][0]["execution_backend"] == "native"
    assert task_payload["scenario_matrix"][0]["environment_preset_id"] == "scenario_default"
    assert task_payload["scenario_matrix"][0]["sensor_profile_name"] == "disabled"
    assert len(task_payload["run_ids"]) == 1
    assert task_payload["summary"]["execution_queue"]["active_run_id"] is None
    assert task_payload["summary"]["execution_queue"]["next_run_id"] == task_payload["run_ids"][0]
    assert task_payload["summary"]["execution_queue"]["ordered_runs"][0]["status"] == "CREATED"

    run_id = task_payload["run_ids"][0]
    run_resp = client.get(f"/runs/{run_id}")
    assert run_resp.status_code == 200
    assert run_resp.json()["data"]["map_name"] == "Town01"
    assert run_resp.json()["data"]["metadata"]["dut_model"] == "演示开发板"
    assert run_resp.json()["data"]["project_id"] == "baseline-validation"
    assert run_resp.json()["data"]["benchmark_definition_id"] == "perception-baseline"
    assert run_resp.json()["data"]["benchmark_task_id"] == task_payload["benchmark_task_id"]
    assert run_resp.json()["data"]["dut_model"] == "演示开发板"
    assert run_resp.json()["data"]["project_name"] == task_payload["project_name"]
    assert run_resp.json()["data"]["benchmark_name"] == task_payload["benchmark_name"]
    assert run_resp.json()["data"]["execution_backend"] == "native"

    report_resp = client.post(
        "/reports/export",
        json={"benchmark_task_id": task_payload["benchmark_task_id"]},
    )
    assert report_resp.status_code == 200
    report_payload = report_resp.json()["data"]
    assert report_payload["benchmark_task_id"] == task_payload["benchmark_task_id"]
    assert report_payload["dut_model"] == "演示开发板"
    assert report_payload["status"] == "READY"

    download_resp = client.get(f"/reports/{report_payload['report_id']}/download?format=json")
    assert download_resp.status_code == 200
    assert report_payload["report_id"] in download_resp.text

    reports_by_project_resp = client.get("/reports", params={"project_id": "baseline-validation"})
    assert reports_by_project_resp.status_code == 200
    reports_by_project = reports_by_project_resp.json()["data"]["reports"]
    assert any(item["report_id"] == report_payload["report_id"] for item in reports_by_project)


def test_export_report_includes_gateway_dut_snapshot() -> None:
    client = TestClient(app)

    register_resp = client.post(
        "/gateways/register",
        json={
            "gateway_id": "gw_demo",
            "name": "Gateway Demo",
            "capabilities": {
                "video_input_modes": ["hdmi_x1301"],
                "dut_output_modes": ["uvc_gadget"],
                "result_ingest_modes": ["http_push"],
            },
            "address": "192.168.110.236",
        },
    )
    assert register_resp.status_code == 200

    heartbeat_resp = client.post(
        "/gateways/gw_demo/heartbeat",
        json={
            "status": "READY",
            "metrics": {
                "dut_model_name": "tensorrt_yolov5s",
                "dut_status": "COMPLETED",
                "output_fps": 14.8,
                "avg_latency_ms": 67.5,
                "p95_latency_ms": 92.1,
                "power_w": 8.7,
                "temperature_c": 58.4,
                "processed_frames": 823,
                "detection_count": 1462,
                "dut_input_topic": "/image_raw",
            },
        },
    )
    assert heartbeat_resp.status_code == 200

    task_resp = client.post(
        "/benchmark-tasks",
        json={
            "benchmark_definition_id": "perception-baseline",
            "selected_scenario_ids": ["town10_autonomous_demo"],
            "dut_model": "Jetson Nano",
            "hil_config": {
                "mode": "camera_open_loop",
                "gateway_id": "gw_demo",
                "video_source": "hdmi_x1301",
                "dut_input_mode": "uvc_camera",
                "result_ingest_mode": "http_push",
            },
            "auto_start": False,
        },
    )
    assert task_resp.status_code == 200
    task_payload = task_resp.json()["data"]
    run_id = task_payload["run_ids"][0]

    run_bound_heartbeat_resp = client.post(
        "/gateways/gw_demo/heartbeat",
        json={
            "status": "BUSY",
            "metrics": {
                "dut_model_name": "tensorrt_yolov4_tiny",
                "dut_status": "RUNNING",
                "output_fps": 11.2,
                "avg_latency_ms": 55.4,
                "p95_latency_ms": 71.5,
                "power_w": 9.1,
                "temperature_c": 57.2,
                "processed_frames": 144,
                "detection_count": 1320,
                "dut_input_topic": "/dev/video0",
            },
            "current_run_id": run_id,
        },
    )
    assert run_bound_heartbeat_resp.status_code == 200

    latest_only_heartbeat_resp = client.post(
        "/gateways/gw_demo/heartbeat",
        json={
            "status": "READY",
            "metrics": {
                "dut_model_name": "latest-live-value",
                "output_fps": 4.2,
                "processed_frames": 20,
                "detection_count": 33,
            },
        },
    )
    assert latest_only_heartbeat_resp.status_code == 200

    report_resp = client.post(
        "/reports/export",
        json={"benchmark_task_id": task_payload["benchmark_task_id"]},
    )
    assert report_resp.status_code == 200
    report_payload = report_resp.json()["data"]

    gateway_snapshot = report_payload["summary"]["gateway_snapshot"]
    assert gateway_snapshot["gateway_id"] == "gw_demo"
    assert gateway_snapshot["gateway_status"] == "BUSY"
    assert gateway_snapshot["dut_model_name"] == "tensorrt_yolov4_tiny"
    assert gateway_snapshot["output_fps"] == 11.2
    assert gateway_snapshot["processed_frames"] == 144
    assert gateway_snapshot["detection_count"] == 1320

    markdown_resp = client.get(f"/reports/{report_payload['report_id']}/download?format=markdown")
    assert markdown_resp.status_code == 200
    assert "## DUT 推理快照" in markdown_resp.text
    assert "推理输出 FPS" in markdown_resp.text
    assert "tensorrt_yolov4_tiny" in markdown_resp.text
    assert "1320" in markdown_resp.text
    assert "Gateway ID" in markdown_resp.text


def test_reports_workspace_endpoint() -> None:
    client = TestClient(app)

    task_resp = client.post(
        "/benchmark-tasks",
        json={
            "benchmark_definition_id": "perception-baseline",
            "selected_scenario_ids": ["town10_autonomous_demo"],
            "auto_start": False,
        },
    )
    assert task_resp.status_code == 200
    task_payload = task_resp.json()["data"]

    report_resp = client.post(
        "/reports/export",
        json={"benchmark_task_id": task_payload["benchmark_task_id"]},
    )
    assert report_resp.status_code == 200

    workspace_resp = client.get("/reports/workspace")
    assert workspace_resp.status_code == 200
    payload = workspace_resp.json()["data"]
    assert payload["summary"]["report_count"] == 1
    assert payload["summary"]["benchmark_task_count"] == 1
    assert len(payload["reports"]) == 1
    assert payload["reports"][0]["benchmark_task_id"] == task_payload["benchmark_task_id"]
    assert payload["exportable_tasks"] == []
    assert payload["pending_report_tasks"] == []


def test_devices_workspace_endpoints() -> None:
    client = TestClient(app)

    register_resp = client.post(
        "/gateways/register",
        json={
            "gateway_id": "gw_alpha",
            "name": "Gateway Alpha",
            "capabilities": {"video_source": "hdmi_x1301"},
            "address": "192.168.1.10",
        },
    )
    assert register_resp.status_code == 200

    capture_resp = client.post(
        "/captures",
        json={
            "gateway_id": "gw_alpha",
            "source": "hdmi_x1301",
            "save_format": "jpg",
            "sample_fps": 2,
            "max_frames": 30,
            "save_dir": "/tmp/gw_alpha_capture",
        },
    )
    assert capture_resp.status_code == 200

    task_resp = client.post(
        "/benchmark-tasks",
        json={
            "benchmark_definition_id": "perception-baseline",
            "selected_scenario_ids": ["town10_autonomous_demo"],
            "dut_model": "Orin NX",
            "hil_config": {
                "mode": "camera_open_loop",
                "gateway_id": "gw_alpha",
                "video_source": "hdmi_x1301",
                "dut_input_mode": "uvc_camera",
                "result_ingest_mode": "http_push",
            },
            "auto_start": False,
        },
    )
    assert task_resp.status_code == 200

    workspace_resp = client.get("/devices/workspace")
    assert workspace_resp.status_code == 200
    workspace_payload = workspace_resp.json()["data"]
    assert workspace_payload["summary"]["online_device_count"] == 0
    assert len(workspace_payload["gateways"]) == 1
    assert workspace_payload["gateways"][0]["gateway_id"] == "gw_alpha"
    assert len(workspace_payload["captures"]) == 1
    assert len(workspace_payload["benchmark_tasks"]) == 1

    detail_resp = client.get("/devices/gw_alpha/workspace")
    assert detail_resp.status_code == 200
    detail_payload = detail_resp.json()["data"]
    assert detail_payload["gateway"]["gateway_id"] == "gw_alpha"
    assert detail_payload["summary"]["capture_count"] == 1
    assert detail_payload["summary"]["linked_benchmark_task_count"] == 1
    assert len(detail_payload["captures"]) == 1
    assert len(detail_payload["benchmark_tasks"]) == 1


def test_create_benchmark_task_with_scenario_defaults() -> None:
    client = TestClient(app)

    task_resp = client.post(
        "/benchmark-tasks",
        json={
            "project_id": "baseline-validation",
            "benchmark_definition_id": "perception-baseline",
            "scenario_matrix": [{"scenario_id": "town10_autonomous_demo"}],
            "auto_start": False,
        },
    )

    assert task_resp.status_code == 200
    task_payload = task_resp.json()["data"]
    assert task_payload["planned_run_count"] == 1
    assert task_payload["scenario_matrix"][0]["resolved_map_name"] == "Town10HD_Opt"
    assert task_payload["scenario_matrix"][0]["environment_preset_id"] == "scenario_default"
    assert task_payload["scenario_matrix"][0]["sensor_profile_name"] == "front_rgb"

    run_id = task_payload["run_ids"][0]
    run_resp = client.get(f"/runs/{run_id}")
    assert run_resp.status_code == 200
    assert run_resp.json()["data"]["map_name"] == "Town10HD_Opt"
    assert run_resp.json()["data"]["sensors"]["enabled"] is True
    assert run_resp.json()["data"]["execution_backend"] == "native"


def test_create_benchmark_task_from_definition_selected_scenarios() -> None:
    client = TestClient(app)

    task_resp = client.post(
        "/benchmark-tasks",
        json={
            "benchmark_definition_id": "perception-baseline",
            "selected_scenario_ids": ["town10_autonomous_demo"],
            "auto_start": False,
        },
    )

    assert task_resp.status_code == 200
    task_payload = task_resp.json()["data"]
    assert task_payload["project_id"] == "baseline-validation"
    assert task_payload["planning_mode"] == "single_scenario"
    assert task_payload["selected_scenario_ids"] == ["town10_autonomous_demo"]
    assert task_payload["planned_run_count"] == 1
    assert task_payload["scenario_matrix"][0]["scenario_id"] == "town10_autonomous_demo"


def test_create_benchmark_task_for_power_thermal_duration_override() -> None:
    client = TestClient(app)

    task_resp = client.post(
        "/benchmark-tasks",
        json={
            "benchmark_definition_id": "power-thermal",
            "selected_scenario_ids": ["free_drive_sensor_collection"],
            "run_duration_seconds": 1800,
            "auto_start": False,
        },
    )

    assert task_resp.status_code == 200
    task_payload = task_resp.json()["data"]
    assert task_payload["project_id"] == "thermal-soak"
    assert task_payload["planning_mode"] == "timed_single_scenario"
    assert task_payload["requested_duration_seconds"] == 1800
    assert task_payload["selected_scenario_ids"] == ["free_drive_sensor_collection"]
    assert task_payload["planned_run_count"] == 1
    assert task_payload["scenario_matrix"][0]["resolved_timeout_seconds"] == 1800


def test_create_benchmark_task_for_stress_matrix_uses_all_runnable() -> None:
    client = TestClient(app)

    task_resp = client.post(
        "/benchmark-tasks",
        json={
            "benchmark_definition_id": "stress-matrix",
            "auto_start": False,
        },
    )

    assert task_resp.status_code == 200
    task_payload = task_resp.json()["data"]
    assert task_payload["project_id"] == "matrix-regression"
    assert task_payload["planning_mode"] == "all_runnable"
    assert task_payload["planned_run_count"] > 1
    assert len(task_payload["run_ids"]) == task_payload["planned_run_count"]
    assert len(task_payload["selected_scenario_ids"]) == task_payload["planned_run_count"]
    assert (
        len(task_payload["summary"]["execution_queue"]["ordered_runs"])
        == task_payload["planned_run_count"]
    )
    assert task_payload["summary"]["execution_queue"]["next_run_id"] == task_payload["run_ids"][0]


def test_create_benchmark_task_rejects_incompatible_project() -> None:
    client = TestClient(app)

    task_resp = client.post(
        "/benchmark-tasks",
        json={
            "project_id": "thermal-soak",
            "benchmark_definition_id": "perception-baseline",
            "selected_scenario_ids": ["town10_autonomous_demo"],
            "auto_start": False,
        },
    )

    assert task_resp.status_code == 422
    assert task_resp.json()["detail"]["code"] == "VALIDATION_ERROR"


def test_rerun_benchmark_task_reuses_original_configuration() -> None:
    client = TestClient(app)

    register_resp = client.post(
        "/gateways/register",
        json={
            "gateway_id": "gw-replay",
            "name": "Replay Gateway",
        },
    )
    assert register_resp.status_code == 200

    task_resp = client.post(
        "/benchmark-tasks",
        json={
            "benchmark_definition_id": "custom-suite",
            "dut_model": "Replay DUT",
            "selected_scenario_ids": [
                "town10_autonomous_demo",
                "free_drive_sensor_collection",
            ],
            "hil_config": {
                "mode": "camera_open_loop",
                "gateway_id": "gw-replay",
                "video_source": "hdmi_x1301",
                "dut_input_mode": "uvc_camera",
                "result_ingest_mode": "http_push",
            },
            "auto_start": False,
        },
    )
    assert task_resp.status_code == 200
    original_task = task_resp.json()["data"]

    rerun_resp = client.post(
        f"/benchmark-tasks/{original_task['benchmark_task_id']}/rerun",
        json={"auto_start": False},
    )
    assert rerun_resp.status_code == 200
    rerun_task = rerun_resp.json()["data"]

    assert rerun_task["benchmark_task_id"] != original_task["benchmark_task_id"]
    assert rerun_task["benchmark_definition_id"] == original_task["benchmark_definition_id"]
    assert rerun_task["project_id"] == original_task["project_id"]
    assert rerun_task["dut_model"] == original_task["dut_model"]
    assert rerun_task["selected_scenario_ids"] == original_task["selected_scenario_ids"]
    assert rerun_task["planned_run_count"] == original_task["planned_run_count"]
    assert [item["scenario_id"] for item in rerun_task["scenario_matrix"]] == [
        item["scenario_id"] for item in original_task["scenario_matrix"]
    ]


def test_stop_benchmark_task_cancels_active_queue() -> None:
    settings = get_settings()
    run_store = RunStore(settings.runs_root)
    for run in run_store.list():
        if run.status not in {
            RunStatus.QUEUED,
            RunStatus.STARTING,
            RunStatus.RUNNING,
            RunStatus.PAUSED,
            RunStatus.STOPPING,
        }:
            continue

        def _close_active_run(current_run):
            current_run.status = RunStatus.CANCELED
            current_run.stop_requested = True
            current_run.cancel_requested = True
            current_run.ended_at = now_utc()
            return current_run

        run_store.update(run.run_id, _close_active_run)

    client = TestClient(app)

    task_resp = client.post(
        "/benchmark-tasks",
        json={
            "benchmark_definition_id": "custom-suite",
            "selected_scenario_ids": [
                "town10_autonomous_demo",
                "free_drive_sensor_collection",
            ],
            "auto_start": True,
        },
    )
    assert task_resp.status_code == 200
    task_payload = task_resp.json()["data"]
    assert task_payload["status"] == "RUNNING"
    assert task_payload["summary"]["counts"]["queued_runs"] == 1
    assert len(task_payload["summary"]["execution_queue"]["queued_run_ids"]) == 2
    assert task_payload["summary"]["execution_queue"]["ordered_runs"][0]["status"] == "QUEUED"
    assert task_payload["summary"]["execution_queue"]["ordered_runs"][1]["status"] == "CREATED"

    stop_resp = client.post(f"/benchmark-tasks/{task_payload['benchmark_task_id']}/stop")
    assert stop_resp.status_code == 200
    stopped_task = stop_resp.json()["data"]

    assert stopped_task["status"] == "CANCELED"
    assert stopped_task["summary"]["counts"]["canceled_runs"] == 2
    assert stopped_task["summary"]["counts"]["queued_runs"] == 0
    assert stopped_task["summary"]["execution_queue"]["queued_run_ids"] == []


def test_create_benchmark_task_for_official_runner_preset(tmp_path, monkeypatch) -> None:
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
                '    <ScenarioObject name="adversary"><Vehicle name="vehicle.tesla.model3" vehicleCategory="car"/></ScenarioObject>',
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
    task_resp = client.post(
        "/benchmark-tasks",
        json={
            "project_id": "baseline-validation",
            "benchmark_definition_id": "perception-baseline",
            "scenario_matrix": [{"scenario_id": "osc_follow_leading_vehicle"}],
            "auto_start": False,
        },
    )

    assert task_resp.status_code == 200
    task_payload = task_resp.json()["data"]
    assert task_payload["scenario_matrix"][0]["execution_backend"] == "native"
    assert task_payload["scenario_matrix"][0]["resolved_map_name"] == "Town01"

    run_id = task_payload["run_ids"][0]
    run_resp = client.get(f"/runs/{run_id}")
    assert run_resp.status_code == 200
    assert run_resp.json()["data"]["execution_backend"] == "native"
