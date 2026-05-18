from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from app.core.models import EventLevel, GatewayRecord, GatewayStatus
from app.executor.hil_runtime_orchestrator import HilRuntimeOrchestrator, HilRuntimeStep
from app.storage.gateway_store import GatewayStore
from app.utils.time_utils import now_utc


def build_settings(tmp_path: Path, **overrides: object) -> SimpleNamespace:
    values = {
        "hil_orchestration_enabled": True,
        "hil_runtime_root": tmp_path,
        "hil_runtime_workdir": tmp_path,
        "project_root": tmp_path,
        "hil_platform_base_url": None,
        "api_port": 8000,
        "hil_command_timeout_seconds": 1.0,
        "hil_gateway_stale_seconds": 30.0,
        "duckpark_pi_host": "192.168.110.236",
        "duckpark_pi_user": "kavin",
        "duckpark_pi_port": 22,
        "hil_pi_start_command": "echo start-pi",
        "hil_pi_stop_command": "echo stop-pi",
        "gateways_root": tmp_path / "gateways",
        "hil_host_carla_start_command": None,
        "hil_host_carla_stop_command": None,
        "hil_host_display_start_command": None,
        "hil_host_display_stop_command": None,
        "hil_jetson_start_command": None,
        "hil_jetson_stop_command": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def save_gateway(
    settings: SimpleNamespace,
    *,
    gateway_id: str = "pi-gateway-1",
    status: GatewayStatus = GatewayStatus.READY,
    address: str = "192.168.110.236",
    current_run_id: str | None = None,
) -> GatewayRecord:
    timestamp = now_utc()
    gateway = GatewayRecord(
        gateway_id=gateway_id,
        name="Pi Gateway 1",
        status=status,
        address=address,
        current_run_id=current_run_id,
        created_at=timestamp,
        updated_at=timestamp,
        last_seen_at=timestamp,
        last_heartbeat_at=timestamp,
    )
    return GatewayStore(settings.gateways_root).save(gateway)


def test_stop_pipeline_preserves_host_carla_for_manual_stop_demo(tmp_path: Path) -> None:
    recorded_events: list[tuple[str, str]] = []

    orchestrator = HilRuntimeOrchestrator(
        build_settings(tmp_path),
        event_callback=lambda run_id, event_type, message, **kwargs: recorded_events.append(
            (event_type, message)
        ),
    )

    run = SimpleNamespace(
        hil_config={"mode": "camera_open_loop"},
        scenario_name="town10_autonomous_demo",
        map_name="Town10HD_Opt",
    )
    descriptor = SimpleNamespace(
        termination=SimpleNamespace(timeout_seconds=86400, success_condition="manual_stop"),
        sync=SimpleNamespace(fixed_delta_seconds=1.0 / 30.0),
        weather=SimpleNamespace(preset="ClearNoon"),
    )

    orchestrator.stop_pipeline(
        "run_test",
        run,
        descriptor,
        [
            HilRuntimeStep(
                step_id="host_carla",
                label="Host CARLA",
                start_command="echo start",
                stop_command="echo stop",
            )
        ],
    )

    assert recorded_events == [
        ("HIL_RUNTIME_STEP_STOP_SKIPPED", "Host CARLA 按当前演示策略保留运行态")
    ]


def test_command_env_includes_recorder_replay_context(tmp_path: Path) -> None:
    orchestrator = HilRuntimeOrchestrator(build_settings(tmp_path))
    run = SimpleNamespace(
        hil_config={"mode": "camera_open_loop", "gateway_id": "pi-gateway-1"},
        scenario_name="town10_autonomous_demo",
        map_name="Town10HD_Opt",
        scenario_source={
            "launch_mode": "carla_recorder_replay",
            "recording_id": "rec_001",
            "source_run_id": "run_source",
            "recorder_log_path": "/tmp/source.log",
            "replay_start_seconds": 3.0,
            "replay_duration_seconds": 12.0,
            "replay_fixed_delta_seconds": 0.05,
            "replay_sensor_mode": "carla_live",
            "sensor_profile_id": "front_rgb",
            "sensor_profile_hash": "hash-front-rgb",
            "sensor_profile_name": "front_rgb",
            "preview_sensor_id": "FrontRGB",
            "preview_sensor_snapshot": {
                "id": "FrontRGB",
                "type": "sensor.camera.rgb",
                "x": 1.5,
                "z": 1.7,
                "width": 1920,
                "height": 1080,
                "fov": 90.0,
            },
            "sensor_warmup_seconds": 1.5,
            "timebase": "synchronous_fixed_delta",
            "hil_clock_mode": "fixed_delta",
        },
    )
    descriptor = SimpleNamespace(
        termination=SimpleNamespace(timeout_seconds=12, success_condition="timeout"),
        sync=SimpleNamespace(fixed_delta_seconds=0.05),
        weather=SimpleNamespace(preset="ClearNoon"),
        sensors=SimpleNamespace(profile_name="fallback_profile"),
    )

    env = orchestrator._build_command_env("run_replay", run, descriptor)

    assert env["DUCKPARK_HIL_REPLAY_MODE"] == "carla_recorder_replay"
    assert env["DUCKPARK_HIL_RECORDING_ID"] == "rec_001"
    assert env["DUCKPARK_HIL_RECORDING_SOURCE_RUN_ID"] == "run_source"
    assert env["DUCKPARK_HIL_REPLAY_LOG_PATH"] == "/tmp/source.log"
    assert env["DUCKPARK_HIL_REPLAY_START_SECONDS"] == "3.0"
    assert env["DUCKPARK_HIL_REPLAY_DURATION_SECONDS"] == "12.0"
    assert env["DUCKPARK_HIL_REPLAY_FIXED_DELTA_SECONDS"] == "0.05"
    assert env["DUCKPARK_HIL_REPLAY_SENSOR_MODE"] == "carla_live"
    assert env["DUCKPARK_HIL_SENSOR_PROFILE_ID"] == "front_rgb"
    assert env["DUCKPARK_HIL_SENSOR_PROFILE_HASH"] == "hash-front-rgb"
    assert env["DUCKPARK_HIL_PREVIEW_SENSOR_ID"] == "FrontRGB"
    assert json.loads(env["DUCKPARK_HIL_PREVIEW_SENSOR_JSON"]) == {
        "id": "FrontRGB",
        "type": "sensor.camera.rgb",
        "x": 1.5,
        "z": 1.7,
        "width": 1920,
        "height": 1080,
        "fov": 90.0,
    }
    assert env["DUCKPARK_HIL_REPLAY_WARMUP_SECONDS"] == "1.5"
    assert env["DUCKPARK_HIL_REPLAY_TIMEBASE"] == "synchronous_fixed_delta"
    assert env["DUCKPARK_HIL_CLOCK_MODE"] == "fixed_delta"
    assert env["DUCKPARK_HIL_SENSOR_PROFILE_NAME"] == "front_rgb"


def test_start_pipeline_skips_all_sidecars_when_gateway_not_selected(
    monkeypatch, tmp_path: Path
) -> None:
    recorded_events: list[tuple[str, str, str, dict[str, object], EventLevel]] = []
    recorded_commands: list[tuple[str, str, str]] = []

    orchestrator = HilRuntimeOrchestrator(
        build_settings(tmp_path),
        event_callback=lambda run_id, event_type, message, **kwargs: recorded_events.append(
            (
                run_id,
                event_type,
                message,
                kwargs.get("payload", {}),
                kwargs.get("level", EventLevel.INFO),
            )
        ),
    )

    monkeypatch.setattr(
        "app.executor.hil_runtime_orchestrator.probe_pi_gateway",
        lambda settings: (_ for _ in ()).throw(AssertionError("probe should not run")),
    )
    monkeypatch.setattr(
        orchestrator,
        "_resolve_steps",
        lambda: [
            HilRuntimeStep("host_carla", "Host CARLA", "echo start-host", "echo stop-host"),
            HilRuntimeStep(
                "host_display",
                "Host OpenCV Sensor Preview",
                "echo start-display",
                "echo stop-display",
            ),
            HilRuntimeStep("pi_pipeline", "Pi HDMI RTP Pipeline", "echo start-pi", "echo stop-pi"),
        ],
    )
    monkeypatch.setattr(
        orchestrator,
        "_run_shell_command",
        lambda run_id, step, command, env, phase: recorded_commands.append(
            (step.step_id, command, phase)
        ),
    )

    run = SimpleNamespace(
        hil_config={"mode": "camera_open_loop"},
        scenario_name="town10_autonomous_demo",
        map_name="Town10HD_Opt",
    )
    descriptor = SimpleNamespace(
        termination=SimpleNamespace(timeout_seconds=86400, success_condition="manual_stop"),
        sync=SimpleNamespace(fixed_delta_seconds=1.0 / 30.0),
        weather=SimpleNamespace(preset="ClearNoon"),
    )

    started_steps = orchestrator.start_pipeline("run_test", run, descriptor)

    assert [step.step_id for step in started_steps] == ["host_carla", "host_display"]
    assert recorded_commands == [
        ("host_carla", "echo start-host", "start"),
        ("host_display", "echo start-display", "start"),
    ]
    assert recorded_events[0] == (
        "run_test",
        "HIL_RUNTIME_DEGRADED",
        "当前 run 未选择树莓派网关，已跳过 Pi 注入链路并继续启动 Host CARLA / OpenCV 预览",
        {
            "gateway_id": None,
            "hil_mode": "camera_open_loop",
            "reason_code": "gateway_not_selected",
        },
        EventLevel.INFO,
    )
    assert (
        "run_test",
        "HIL_RUNTIME_STEP_SKIPPED",
        "树莓派网关未就绪，已跳过 Pi HDMI RTP Pipeline",
        {
            "step_id": "pi_pipeline",
            "gateway_id": None,
            "hil_mode": "camera_open_loop",
            "reason_code": "gateway_not_selected",
        },
        EventLevel.INFO,
    ) in recorded_events


def test_start_pipeline_skips_host_carla_for_recorder_replay(monkeypatch, tmp_path: Path) -> None:
    recorded_events: list[tuple[str, str, str, dict[str, object], EventLevel]] = []
    recorded_commands: list[tuple[str, str, str]] = []

    orchestrator = HilRuntimeOrchestrator(
        build_settings(tmp_path),
        event_callback=lambda run_id, event_type, message, **kwargs: recorded_events.append(
            (
                run_id,
                event_type,
                message,
                kwargs.get("payload", {}),
                kwargs.get("level", EventLevel.INFO),
            )
        ),
    )
    monkeypatch.setattr(
        orchestrator,
        "_resolve_steps",
        lambda: [
            HilRuntimeStep("host_carla", "Host CARLA", "echo start-host", "echo stop-host"),
            HilRuntimeStep(
                "host_display",
                "Host OpenCV Sensor Preview",
                "echo start-display",
                "echo stop-display",
            ),
        ],
    )
    monkeypatch.setattr(
        orchestrator,
        "_run_shell_command",
        lambda run_id, step, command, env, phase: recorded_commands.append(
            (step.step_id, command, phase)
        ),
    )
    run = SimpleNamespace(
        hil_config={"mode": "camera_open_loop"},
        scenario_name="free_drive_sensor_collection",
        map_name="Town10HD_Opt",
        scenario_source={"launch_mode": "carla_recorder_replay", "sensor_profile_id": "front_rgb"},
    )
    descriptor = SimpleNamespace(
        termination=SimpleNamespace(timeout_seconds=10, success_condition="timeout"),
        sync=SimpleNamespace(fixed_delta_seconds=0.05),
        weather=SimpleNamespace(preset="ClearNoon"),
    )

    started_steps = orchestrator.start_pipeline("run_replay", run, descriptor)

    assert [step.step_id for step in started_steps] == ["host_display"]
    assert recorded_commands == [("host_display", "echo start-display", "start")]
    assert (
        "run_replay",
        "HIL_RUNTIME_STEP_SKIPPED",
        "Recorder replay 已由 native runtime 管理 CARLA，已跳过 Host CARLA 自动拉起",
        {
            "step_id": "host_carla",
            "gateway_id": None,
            "hil_mode": "camera_open_loop",
            "reason_code": "gateway_not_selected",
            "carla_host_managed_by_replay": True,
        },
        EventLevel.INFO,
    ) in recorded_events


def test_start_pipeline_skips_all_sidecars_when_gateway_unreachable(
    monkeypatch, tmp_path: Path
) -> None:
    recorded_events: list[tuple[str, str, str, dict[str, object], EventLevel]] = []
    recorded_commands: list[tuple[str, str, str]] = []
    settings = build_settings(tmp_path)
    save_gateway(settings, gateway_id="pi-gateway-1")

    orchestrator = HilRuntimeOrchestrator(
        settings,
        event_callback=lambda run_id, event_type, message, **kwargs: recorded_events.append(
            (
                run_id,
                event_type,
                message,
                kwargs.get("payload", {}),
                kwargs.get("level", EventLevel.INFO),
            )
        ),
    )

    monkeypatch.setattr(
        "app.executor.hil_runtime_orchestrator.probe_pi_gateway",
        lambda settings: {
            "status": "OFFLINE",
            "configured": True,
            "reachable": False,
            "host": "192.168.110.236",
            "user": "kavin",
            "port": 22,
            "start_command_configured": True,
            "stop_command_configured": True,
            "last_probe_at_utc": "2026-03-23T00:00:00+00:00",
            "warning": "No route to host",
        },
    )
    monkeypatch.setattr(
        orchestrator,
        "_resolve_steps",
        lambda: [
            HilRuntimeStep("host_carla", "Host CARLA", "echo start-host", "echo stop-host"),
            HilRuntimeStep(
                "host_display",
                "Host OpenCV Sensor Preview",
                "echo start-display",
                "echo stop-display",
            ),
            HilRuntimeStep("pi_pipeline", "Pi HDMI RTP Pipeline", "echo start-pi", "echo stop-pi"),
        ],
    )
    monkeypatch.setattr(
        orchestrator,
        "_run_shell_command",
        lambda run_id, step, command, env, phase: recorded_commands.append(
            (step.step_id, command, phase)
        ),
    )

    run = SimpleNamespace(
        hil_config={"mode": "camera_open_loop", "gateway_id": "pi-gateway-1"},
        scenario_name="town10_autonomous_demo",
        map_name="Town10HD_Opt",
    )
    descriptor = SimpleNamespace(
        termination=SimpleNamespace(timeout_seconds=86400, success_condition="manual_stop"),
        sync=SimpleNamespace(fixed_delta_seconds=1.0 / 30.0),
        weather=SimpleNamespace(preset="ClearNoon"),
    )

    started_steps = orchestrator.start_pipeline("run_test", run, descriptor)

    assert [step.step_id for step in started_steps] == ["host_carla", "host_display"]
    assert recorded_commands == [
        ("host_carla", "echo start-host", "start"),
        ("host_display", "echo start-display", "start"),
    ]
    run_id, event_type, message, payload, level = recorded_events[0]
    assert run_id == "run_test"
    assert event_type == "HIL_RUNTIME_DEGRADED"
    assert message == "树莓派网关当前不可达，已跳过 Pi 注入链路并继续启动 Host CARLA / OpenCV 预览"
    assert level == EventLevel.WARNING
    assert payload["gateway_id"] == "pi-gateway-1"
    assert payload["gateway_record_status"] == "READY"
    assert payload["gateway_effective_status"] == "READY"
    assert payload["configured_pi_match"] is True
    assert payload["reason_code"] == "pi_gateway_unreachable"
    assert payload["pi_gateway_status"]["reachable"] is False
    assert (
        "run_test",
        "HIL_RUNTIME_STEP_SKIPPED",
        "树莓派网关未就绪，已跳过 Pi HDMI RTP Pipeline",
        {
            "step_id": "pi_pipeline",
            **payload,
        },
        EventLevel.WARNING,
    ) in recorded_events


def test_start_pipeline_starts_sidecars_when_gateway_ready(monkeypatch, tmp_path: Path) -> None:
    settings = build_settings(tmp_path)
    save_gateway(settings, gateway_id="pi-gateway-1")
    recorded_commands: list[tuple[str, str, str]] = []

    orchestrator = HilRuntimeOrchestrator(settings)
    monkeypatch.setattr(
        "app.executor.hil_runtime_orchestrator.probe_pi_gateway",
        lambda settings: {
            "status": "READY",
            "configured": True,
            "reachable": True,
            "host": "192.168.110.236",
            "user": "kavin",
            "port": 22,
            "start_command_configured": True,
            "stop_command_configured": True,
            "last_probe_at_utc": "2026-03-23T00:00:00+00:00",
            "warning": None,
        },
    )
    monkeypatch.setattr(
        orchestrator,
        "_resolve_steps",
        lambda: [
            HilRuntimeStep("host_carla", "Host CARLA", "echo start-host", "echo stop-host"),
            HilRuntimeStep(
                "host_display",
                "Host OpenCV Sensor Preview",
                "echo start-display",
                "echo stop-display",
            ),
            HilRuntimeStep("pi_pipeline", "Pi HDMI RTP Pipeline", "echo start-pi", "echo stop-pi"),
        ],
    )
    monkeypatch.setattr(
        orchestrator,
        "_run_shell_command",
        lambda run_id, step, command, env, phase: recorded_commands.append(
            (step.step_id, command, phase)
        ),
    )

    run = SimpleNamespace(
        hil_config={"mode": "camera_open_loop", "gateway_id": "pi-gateway-1"},
        scenario_name="town10_autonomous_demo",
        map_name="Town10HD_Opt",
    )
    descriptor = SimpleNamespace(
        termination=SimpleNamespace(timeout_seconds=86400, success_condition="manual_stop"),
        sync=SimpleNamespace(fixed_delta_seconds=1.0 / 30.0),
        weather=SimpleNamespace(preset="ClearNoon"),
    )

    started_steps = orchestrator.start_pipeline("run_test", run, descriptor)

    assert [step.step_id for step in started_steps] == [
        "host_carla",
        "host_display",
        "pi_pipeline",
    ]
    assert recorded_commands == [
        ("host_carla", "echo start-host", "start"),
        ("host_display", "echo start-display", "start"),
        ("pi_pipeline", "echo start-pi", "start"),
    ]
