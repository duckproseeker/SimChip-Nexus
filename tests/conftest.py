from __future__ import annotations

from pathlib import Path

import pytest

from app.api.routes_captures import get_capture_manager
from app.api.routes_gateways import get_gateway_registry
from app.api.routes_projects import get_platform_service
from app.api.routes_runs import (
    get_artifact_store,
    get_benchmark_definition_store,
    get_benchmark_task_store,
    get_control_store,
    get_project_store,
    get_run_manager,
)
from app.core.config import get_settings


@pytest.fixture(autouse=True)
def reset_settings_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    project_root = tmp_path / "project"
    (project_root / "run_data" / "runs").mkdir(parents=True, exist_ok=True)
    (project_root / "run_data" / "captures").mkdir(parents=True, exist_ok=True)
    (project_root / "run_data" / "commands").mkdir(parents=True, exist_ok=True)
    (project_root / "run_data" / "executor").mkdir(parents=True, exist_ok=True)
    (project_root / "run_data" / "controls").mkdir(parents=True, exist_ok=True)
    (project_root / "run_data" / "projects").mkdir(parents=True, exist_ok=True)
    (project_root / "run_data" / "benchmark_definitions").mkdir(
        parents=True, exist_ok=True
    )
    (project_root / "run_data" / "benchmark_tasks").mkdir(
        parents=True, exist_ok=True
    )
    (project_root / "run_data" / "reports").mkdir(parents=True, exist_ok=True)
    (project_root / "run_data" / "scenario_builds").mkdir(
        parents=True, exist_ok=True
    )
    (project_root / "configs" / "sensors").mkdir(parents=True, exist_ok=True)
    (project_root / "frontend" / "dist" / "assets").mkdir(parents=True, exist_ok=True)
    (project_root / "artifacts").mkdir(parents=True, exist_ok=True)
    (project_root / "artifacts" / "captures").mkdir(parents=True, exist_ok=True)
    (project_root / "artifacts" / "reports").mkdir(parents=True, exist_ok=True)
    (project_root / "frontend" / "dist" / "index.html").write_text(
        "<!doctype html><html><body><div id=\"root\"></div><script src=\"/assets/test.js\"></script></body></html>",
        encoding="utf-8",
    )

    monkeypatch.setenv("PROJECT_ROOT", str(project_root))
    monkeypatch.setenv("RUNS_ROOT", str(project_root / "run_data" / "runs"))
    monkeypatch.setenv("CAPTURES_ROOT", str(project_root / "run_data" / "captures"))
    monkeypatch.setenv("COMMANDS_ROOT", str(project_root / "run_data" / "commands"))
    monkeypatch.setenv("EXECUTOR_ROOT", str(project_root / "run_data" / "executor"))
    monkeypatch.setenv("CONTROLS_ROOT", str(project_root / "run_data" / "controls"))
    monkeypatch.setenv("PROJECTS_ROOT", str(project_root / "run_data" / "projects"))
    monkeypatch.setenv(
        "BENCHMARK_DEFINITIONS_ROOT",
        str(project_root / "run_data" / "benchmark_definitions"),
    )
    monkeypatch.setenv(
        "BENCHMARK_TASKS_ROOT", str(project_root / "run_data" / "benchmark_tasks")
    )
    monkeypatch.setenv("REPORTS_ROOT", str(project_root / "run_data" / "reports"))
    monkeypatch.setenv(
        "SCENARIO_BUILDS_ROOT",
        str(project_root / "run_data" / "scenario_builds"),
    )
    monkeypatch.setenv("ARTIFACTS_ROOT", str(project_root / "artifacts"))
    monkeypatch.setenv(
        "CAPTURE_ARTIFACTS_ROOT", str(project_root / "artifacts" / "captures")
    )
    monkeypatch.setenv(
        "REPORT_ARTIFACTS_ROOT", str(project_root / "artifacts" / "reports")
    )
    monkeypatch.setenv("GATEWAYS_ROOT", str(project_root / "run_data" / "gateways"))
    monkeypatch.setenv("SENSOR_PROFILES_ROOT", str(project_root / "configs" / "sensors"))

    get_settings.cache_clear()
    get_run_manager.cache_clear()
    get_artifact_store.cache_clear()
    get_project_store.cache_clear()
    get_benchmark_definition_store.cache_clear()
    get_benchmark_task_store.cache_clear()
    get_control_store.cache_clear()
    get_gateway_registry.cache_clear()
    get_capture_manager.cache_clear()
    get_platform_service.cache_clear()

    yield

    get_settings.cache_clear()
    get_run_manager.cache_clear()
    get_artifact_store.cache_clear()
    get_project_store.cache_clear()
    get_benchmark_definition_store.cache_clear()
    get_benchmark_task_store.cache_clear()
    get_control_store.cache_clear()
    get_gateway_registry.cache_clear()
    get_capture_manager.cache_clear()
    get_platform_service.cache_clear()
