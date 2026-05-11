from __future__ import annotations

from pathlib import Path

from app.core.config import get_settings
from app.orchestrator.queue import FileCommandQueue
from app.orchestrator.run_manager import RunManager
from app.storage.artifact_store import ArtifactStore
from app.storage.run_store import RunStore

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
    "metadata": {
        "author": "test",
        "tags": ["artifact"],
        "description": "artifact test",
    },
}


def test_artifact_layout_created() -> None:
    settings = get_settings()
    manager = RunManager(
        run_store=RunStore(settings.runs_root),
        artifact_store=ArtifactStore(settings.artifacts_root),
        command_queue=FileCommandQueue(settings.commands_root),
    )

    run = manager.create_run(descriptor_payload=VALID_DESCRIPTOR)
    run_dir = Path(run.artifact_dir)

    assert run_dir.exists()
    assert (run_dir / "config_snapshot.json").exists()
    assert (run_dir / "events.jsonl").exists()
    assert (run_dir / "run.log").exists()
    assert (run_dir / "status.json").exists()
    assert (run_dir / "recorder").exists()
    assert (run_dir / "outputs").exists()


def test_device_metrics_can_be_written_and_read() -> None:
    settings = get_settings()
    store = ArtifactStore(settings.artifacts_root)
    manager = RunManager(
        run_store=RunStore(settings.runs_root),
        artifact_store=store,
        command_queue=FileCommandQueue(settings.commands_root),
    )

    run = manager.create_run(descriptor_payload=VALID_DESCRIPTOR)
    payload = {
        "gateway_id": "gw_demo",
        "gateway_status": "READY",
        "output_fps": 16.4,
        "avg_latency_ms": 59.2,
        "processed_frames": 144,
    }

    store.write_device_metrics(run.run_id, payload)

    assert store.read_device_metrics(run.run_id) == payload
    assert (Path(run.artifact_dir) / "outputs" / "hil" / "device_metrics.json").exists()
