from __future__ import annotations

from app.core.config import get_settings


def test_get_settings_loads_env_local_relative_to_project_root(
    tmp_path, monkeypatch
) -> None:
    project_root = tmp_path / "env_project"
    hil_runtime_root = tmp_path / "custom_hil_runtime"
    (project_root / "external" / "scenario_runner").mkdir(parents=True, exist_ok=True)
    hil_runtime_root.mkdir(parents=True, exist_ok=True)
    (project_root / ".env.local").write_text(
        "\n".join(
            [
                'CARLA_HOST="192.168.1.25"',
                "CARLA_PORT=2100",
                "export TRAFFIC_MANAGER_PORT=8110",
                "RUNS_ROOT=./custom/runs",
                "COMMANDS_ROOT=./custom/commands",
                "ARTIFACTS_ROOT=./custom/artifacts",
                "SCENARIO_RUNNER_ROOT=./external/scenario_runner",
                "HIL_RUNTIME_ROOT=../custom_hil_runtime",
                "HIL_COMMAND_TIMEOUT_SECONDS=123",
                "HIL_ORCHESTRATION_ENABLED=false",
                "HIL_PLATFORM_BASE_URL=http://192.168.110.151:8000",
                "HIL_PI_START_COMMAND=ssh pi start",
            ]
        ),
        encoding="utf-8",
    )

    for key in [
        "CARLA_HOST",
        "CARLA_PORT",
        "TRAFFIC_MANAGER_PORT",
        "RUNS_ROOT",
        "COMMANDS_ROOT",
        "ARTIFACTS_ROOT",
        "SCENARIO_RUNNER_ROOT",
        "HIL_RUNTIME_ROOT",
        "HIL_COMMAND_TIMEOUT_SECONDS",
        "HIL_ORCHESTRATION_ENABLED",
        "HIL_PLATFORM_BASE_URL",
        "HIL_PI_START_COMMAND",
    ]:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("PROJECT_ROOT", str(project_root))
    get_settings.cache_clear()

    settings = get_settings()

    assert settings.carla_host == "192.168.1.25"
    assert settings.carla_port == 2100
    assert settings.traffic_manager_port == 8110
    assert settings.runs_root == project_root / "custom" / "runs"
    assert settings.commands_root == project_root / "custom" / "commands"
    assert settings.artifacts_root == project_root / "custom" / "artifacts"
    assert settings.scenario_runner_root == project_root / "external" / "scenario_runner"
    assert settings.hil_runtime_root.resolve() == hil_runtime_root.resolve()
    assert settings.hil_command_timeout_seconds == 123.0
    assert settings.hil_orchestration_enabled is False
    assert settings.hil_platform_base_url == "http://192.168.110.151:8000"
    assert settings.hil_pi_start_command == "ssh pi start"
