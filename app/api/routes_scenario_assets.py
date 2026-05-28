from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.storage.scenario_asset_store import get_scenario_asset_store

router = APIRouter(prefix="/scenario-assets", tags=["场景库"])


class CreateScenarioRequest(BaseModel):
    name: str
    recorder_log_path: str
    map_name: str = ""
    duration_seconds: float = 0.0
    tags: list[str] = []
    description: str = ""
    file_size_bytes: int = 0
    metadata: dict = {}


class UpdateScenarioRequest(BaseModel):
    name: str | None = None
    map_name: str | None = None
    duration_seconds: float | None = None
    tags: list[str] | None = None
    description: str | None = None
    metadata: dict | None = None


@router.post("", status_code=201)
def create_scenario(body: CreateScenarioRequest):
    store = get_scenario_asset_store()
    asset = store.create(**body.model_dump())
    return asset.model_dump()


@router.get("")
def list_scenarios(
    tag: str | None = Query(None),
    map_name: str | None = Query(None),
):
    store = get_scenario_asset_store()
    assets = store.list(tag=tag, map_name=map_name)
    return [a.model_dump() for a in assets]


@router.get("/{scenario_id}")
def get_scenario(scenario_id: str):
    store = get_scenario_asset_store()
    try:
        asset = store.get(scenario_id)
    except KeyError:
        raise HTTPException(404, f"Scenario not found: {scenario_id}")
    return asset.model_dump()


@router.patch("/{scenario_id}")
def update_scenario(scenario_id: str, body: UpdateScenarioRequest):
    store = get_scenario_asset_store()
    try:
        kwargs = {k: v for k, v in body.model_dump().items() if v is not None}
        asset = store.update(scenario_id, **kwargs)
    except KeyError:
        raise HTTPException(404, f"Scenario not found: {scenario_id}")
    return asset.model_dump()


@router.delete("/{scenario_id}", status_code=204)
def delete_scenario(scenario_id: str):
    store = get_scenario_asset_store()
    try:
        store.get(scenario_id)
    except KeyError:
        raise HTTPException(404, f"Scenario not found: {scenario_id}")
    store.delete(scenario_id)
