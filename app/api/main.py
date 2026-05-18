from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.routes_benchmarks import router as benchmarks_router
from app.api.routes_captures import router as captures_router
from app.api.routes_carla import router as carla_router
from app.api.routes_devices import router as devices_router
from app.api.routes_gateways import router as gateways_router
from app.api.routes_projects import router as projects_router
from app.api.routes_reports import router as reports_router
from app.api.routes_runs import router as runs_router
from app.api.routes_scenario_recordings import router as scenario_recordings_router
from app.api.routes_scenario_sources import router as scenario_sources_router
from app.api.routes_scenarios import router as scenarios_router
from app.api.routes_sensor_profiles import router as sensor_profiles_router
from app.api.routes_system import router as system_router
from app.api.routes_ui import router as ui_router
from app.core.logging import setup_logging

setup_logging()

app = FastAPI(
    title="SimChip Nexus API",
    version="0.2.0",
    description=(
        "SimChip Nexus 芯境智测平台提供 CARLA 场景仿真、硬件在环测试、设备接入和评测报告服务。"
        "\n\n"
        "- `/docs`：接口文档"
        "\n"
        "- `/`：平台展示页"
        "\n"
        "- `/ui`：Web 测评控制台"
    ),
)

_app_root = Path(__file__).resolve().parents[1]
_project_root = _app_root.parent
app.mount(
    "/assets",
    StaticFiles(directory=str(_project_root / "frontend" / "dist" / "assets"), check_dir=False),
    name="frontend-assets",
)
app.mount(
    "/media",
    StaticFiles(directory=str(_project_root / "frontend" / "dist" / "media"), check_dir=False),
    name="frontend-media",
)

app.include_router(runs_router)
app.include_router(projects_router)
app.include_router(benchmarks_router)
app.include_router(scenarios_router)
app.include_router(sensor_profiles_router)
app.include_router(scenario_recordings_router)
app.include_router(scenario_sources_router)
app.include_router(gateways_router)
app.include_router(devices_router)
app.include_router(captures_router)
app.include_router(reports_router)
app.include_router(system_router)
app.include_router(carla_router)
app.include_router(ui_router)


@app.get("/healthz", tags=["系统"])
def healthz() -> dict[str, str]:
    return {"status": "ok"}
