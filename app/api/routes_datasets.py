"""REST API for sensor datasets (offline-rendered frame sequences)."""
from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.core.models import DatasetRecord, DatasetStatus, SensorConfig
from app.executor.offline_renderer import start_render
from app.storage.dataset_store import get_dataset_store

router = APIRouter(prefix="/datasets", tags=["datasets"])


class GenerateRequest(BaseModel):
    scenario_id: str
    name: str = ""
    pipeline_id: str = ""
    sensor_configs: list[SensorConfig]
    delta_seconds: float = 0.05
    duration: float = 0.0
    start_time: float = 0.0


class GenerateResponse(BaseModel):
    dataset_id: str
    status: str


@router.post("/generate", response_model=GenerateResponse)
def generate_dataset(req: GenerateRequest):
    """Trigger offline rendering of sensor data from a scenario."""
    from app.storage.scenario_asset_store import get_scenario_asset_store

    # Validate scenario exists
    scenario_store = get_scenario_asset_store()
    try:
        scenario = scenario_store.get(req.scenario_id)
    except KeyError:
        raise HTTPException(404, f"Scenario '{req.scenario_id}' not found")

    if not req.sensor_configs:
        raise HTTPException(422, "At least one sensor_config is required")

    # Create dataset record
    store = get_dataset_store()
    dataset_id = f"ds_{uuid.uuid4().hex[:12]}"
    output_dir = f"/ros2_ws/datasets/{dataset_id}"

    record = DatasetRecord(
        dataset_id=dataset_id,
        scenario_id=req.scenario_id,
        pipeline_id=req.pipeline_id,
        name=req.name or f"{scenario.name} render",
        status=DatasetStatus.PENDING,
        sensor_configs=req.sensor_configs,
        delta_seconds=req.delta_seconds,
        duration_seconds=req.duration or scenario.duration_seconds,
        output_dir=output_dir,
    )
    store.create(record)

    # Start background rendering
    start_render(
        dataset_id=dataset_id,
        scenario_log_path=scenario.recorder_log_path,
        sensor_configs=req.sensor_configs,
        output_dir=output_dir,
        delta_seconds=req.delta_seconds,
        duration=req.duration,
        start_time=req.start_time,
    )

    return GenerateResponse(dataset_id=dataset_id, status="PENDING")


@router.get("", response_model=list[dict[str, Any]])
def list_datasets(scenario_id: str | None = None):
    """List all datasets, optionally filtered by scenario."""
    store = get_dataset_store()
    records = store.list(scenario_id=scenario_id)
    results = []
    for r in records:
        d = r.model_dump()
        if r.status == DatasetStatus.RENDERING and r.output_dir:
            d["rendered_frames"] = _count_rendered_frames(r.output_dir)
        results.append(d)
    return results


def _count_rendered_frames(output_dir: str) -> int:
    """Count rendered frames on disk for live progress (count first sensor dir only)."""
    import subprocess
    host_dir = output_dir.replace("/ros2_ws/datasets", "/home/du/ros2-humble/datasets")
    try:
        result = subprocess.run(
            ["ls", host_dir], capture_output=True, text=True, timeout=3,
        )
        if not result.stdout.strip():
            return 0
        first_sensor = result.stdout.strip().split('\n')[0]
        sensor_dir = f"{host_dir}/{first_sensor}"
        result2 = subprocess.run(
            ["find", sensor_dir, "-name", "*.jpg", "-o", "-name", "*.bin"],
            capture_output=True, text=True, timeout=3,
        )
        return len(result2.stdout.strip().split('\n')) if result2.stdout.strip() else 0
    except Exception:
        return 0


@router.get("/{dataset_id}")
def get_dataset(dataset_id: str):
    """Get dataset details including render progress."""
    store = get_dataset_store()
    try:
        record = store.get(dataset_id)
    except KeyError:
        raise HTTPException(404, "Dataset not found")
    return record.model_dump()


@router.delete("/{dataset_id}")
def delete_dataset(dataset_id: str):
    """Delete a dataset and its files."""
    import subprocess

    store = get_dataset_store()
    try:
        record = store.get(dataset_id)
    except KeyError:
        raise HTTPException(404, "Dataset not found")

    # Delete files from host
    if record.output_dir:
        host_dir = record.output_dir.replace("/ros2_ws/datasets", "/home/du/ros2-humble/datasets")
        subprocess.run(["rm", "-rf", host_dir], capture_output=True)

    store.delete(dataset_id)
    return {"deleted": dataset_id}


@router.post("/{dataset_id}/play")
def play_dataset(dataset_id: str):
    """Start fullscreen playback of a dataset on the host display."""
    from app.executor.online_player import start_playback, get_session

    store = get_dataset_store()
    try:
        record = store.get(dataset_id)
    except KeyError:
        raise HTTPException(404, "Dataset not found")

    if record.status != DatasetStatus.COMPLETED:
        raise HTTPException(400, "Dataset not ready for playback")

    existing = get_session(dataset_id)
    if existing and existing.running:
        return {"status": "already_playing", "dataset_id": dataset_id}

    # Pick first camera sensor
    sensor_id = ""
    for sc in record.sensor_configs:
        if "camera" in sc.sensor_type:
            sensor_id = sc.sensor_id
            break
    if not sensor_id:
        raise HTTPException(400, "No camera sensor in this dataset")

    session = start_playback(
        dataset_id=dataset_id,
        output_dir=record.output_dir,
        sensor_id=sensor_id,
        target_fps=20.0,
        mode="display",
    )
    return {"status": "playing", "dataset_id": dataset_id, "sensor_id": sensor_id}


@router.post("/{dataset_id}/stop")
def stop_dataset_playback(dataset_id: str):
    """Stop a running playback."""
    from app.executor.online_player import stop_playback
    stopped = stop_playback(dataset_id)
    return {"stopped": stopped}
