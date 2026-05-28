from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.routes_pipelines import router as pipelines_router
from app.api.routes_scenario_assets import router as scenario_assets_router
from app.api.routes_datasets import router as datasets_router
from app.core.logging import setup_logging

setup_logging()

app = FastAPI(
    title="SimChip Nexus API",
    version="0.3.0",
    description="芯境智测平台 — CARLA 传感器数据离线渲染与在线注入",
)

_app_root = Path(__file__).resolve().parents[1]
_project_root = _app_root.parent
app.mount(
    "/assets",
    StaticFiles(directory=str(_project_root / "frontend" / "dist" / "assets"), check_dir=False),
    name="frontend-assets",
)

app.include_router(pipelines_router)
app.include_router(scenario_assets_router)
app.include_router(datasets_router)


@app.get("/healthz", tags=["system"])
def healthz() -> dict[str, str]:
    return {"status": "ok"}
