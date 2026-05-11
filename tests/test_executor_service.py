from __future__ import annotations

from pathlib import Path

from app.core.config import get_settings
from app.core.models import RunMetrics, RunRecord, RunStatus
from app.executor.service import ExecutorService
from app.storage.artifact_store import ArtifactStore
from app.storage.run_store import RunStore
from app.utils.time_utils import now_utc


VALID_DESCRIPTOR = {
    "version": 1,
    "scenario_name": "town10_autonomous_demo",
    "map_name": "Town10HD_Opt",
    "weather": {"preset": "ClearNoon"},
    "sync": {"enabled": False, "fixed_delta_seconds": 0.1},
    "ego_vehicle": {
        "blueprint": "vehicle.lincoln.mkz_2017",
        "spawn_point": {
            "x": 10.0,
            "y": 20.0,
            "z": 0.5,
            "roll": 0.0,
            "pitch": 0.0,
            "yaw": 90.0,
        },
    },
    "traffic": {"enabled": False, "num_vehicles": 0, "num_walkers": 0},
    "sensors": {"enabled": False},
    "termination": {"timeout_seconds": 30, "success_condition": "manual_stop"},
    "recorder": {"enabled": False},
    "metadata": {"author": "test", "tags": ["executor"], "description": "executor test"},
}


def test_executor_service_recovers_interrupted_runs_on_startup() -> None:
    settings = get_settings()
    run_store = RunStore(settings.runs_root)
    artifact_store = ArtifactStore(settings.artifacts_root)

    interrupted_run_id = f"run_executor_recover_{now_utc().strftime('%Y%m%d%H%M%S%f')}"
    interrupted_run_dir = artifact_store.init_run(interrupted_run_id)
    interrupted_run = RunRecord(
        run_id=interrupted_run_id,
        status=RunStatus.RUNNING,
        created_at=now_utc(),
        updated_at=now_utc(),
        started_at=now_utc(),
        scenario_name="town10_autonomous_demo",
        map_name="Town10HD_Opt",
        descriptor=VALID_DESCRIPTOR,
        artifact_dir=str(interrupted_run_dir),
        execution_backend="native",
        scenario_source={"provider": "native", "launch_mode": "native_descriptor"},
    )
    run_store.create(interrupted_run)
    artifact_store.write_status(interrupted_run)

    completed_run_id = f"run_executor_keep_{now_utc().strftime('%Y%m%d%H%M%S%f')}"
    completed_run_dir = artifact_store.init_run(completed_run_id)
    completed_run = RunRecord(
        run_id=completed_run_id,
        status=RunStatus.COMPLETED,
        created_at=now_utc(),
        updated_at=now_utc(),
        started_at=now_utc(),
        ended_at=now_utc(),
        scenario_name="town10_autonomous_demo",
        map_name="Town10HD_Opt",
        descriptor=VALID_DESCRIPTOR,
        artifact_dir=str(completed_run_dir),
        execution_backend="native",
        scenario_source={"provider": "native", "launch_mode": "native_descriptor"},
    )
    run_store.create(completed_run)
    artifact_store.write_status(completed_run)

    service = ExecutorService()
    service._recover_interrupted_runs()

    interrupted_after = run_store.get(interrupted_run_id)
    assert interrupted_after.status == RunStatus.FAILED
    assert "executor 服务重启" in (interrupted_after.error_reason or "")

    metrics = artifact_store.read_metrics(interrupted_run_id)
    assert metrics is not None
    assert metrics["final_status"] == "FAILED"

    events = artifact_store.read_events(interrupted_run_id)
    event_types = {event["event_type"] for event in events}
    assert "RUN_RECOVERED_AFTER_EXECUTOR_RESTART" in event_types

    completed_after = run_store.get(completed_run_id)
    assert completed_after.status == RunStatus.COMPLETED


def test_executor_service_marks_run_failed_after_worker_exit() -> None:
    settings = get_settings()
    run_store = RunStore(settings.runs_root)
    artifact_store = ArtifactStore(settings.artifacts_root)

    run_id = f"run_executor_worker_exit_{now_utc().strftime('%Y%m%d%H%M%S%f')}"
    run_dir = artifact_store.init_run(run_id)
    run = RunRecord(
        run_id=run_id,
        status=RunStatus.STARTING,
        created_at=now_utc(),
        updated_at=now_utc(),
        started_at=now_utc(),
        scenario_name="town10_autonomous_demo",
        map_name="Town10HD_Opt",
        descriptor=VALID_DESCRIPTOR,
        artifact_dir=str(run_dir),
        execution_backend="native",
        scenario_source={"provider": "native", "launch_mode": "native_descriptor"},
    )
    run_store.create(run)
    artifact_store.write_status(run)

    service = ExecutorService()
    log_path = run_dir / "executor_worker.log"
    log_path.write_text("terminate called after throwing TimeoutException\n", encoding="utf-8")

    service._mark_run_failed_after_worker_exit(run_id, -6, log_path)

    failed_run = run_store.get(run_id)
    assert failed_run.status == RunStatus.FAILED
    assert "signal SIGABRT" in (failed_run.error_reason or "")

    metrics = artifact_store.read_metrics(run_id)
    assert metrics is not None
    assert metrics["final_status"] == "FAILED"

    events = artifact_store.read_events(run_id)
    assert any(event["event_type"] == "RUN_WORKER_EXITED_UNEXPECTEDLY" for event in events)


def test_executor_service_preserves_terminal_run_after_worker_exit() -> None:
    settings = get_settings()
    run_store = RunStore(settings.runs_root)
    artifact_store = ArtifactStore(settings.artifacts_root)

    run_id = f"run_executor_worker_terminal_{now_utc().strftime('%Y%m%d%H%M%S%f')}"
    run_dir = artifact_store.init_run(run_id)
    run = RunRecord(
        run_id=run_id,
        status=RunStatus.COMPLETED,
        created_at=now_utc(),
        updated_at=now_utc(),
        started_at=now_utc(),
        ended_at=now_utc(),
        scenario_name="town10_autonomous_demo",
        map_name="Town10HD_Opt",
        descriptor=VALID_DESCRIPTOR,
        artifact_dir=str(run_dir),
        execution_backend="native",
        scenario_source={"provider": "native", "launch_mode": "native_descriptor"},
    )
    run_store.create(run)
    artifact_store.write_status(run)
    artifact_store.write_metrics(
        RunMetrics(
            run_id=run_id,
            scenario_name=run.scenario_name,
            map_name=run.map_name,
            start_time=run.started_at or run.created_at,
            end_time=run.ended_at or run.updated_at,
            final_status=RunStatus.COMPLETED,
            failure_reason=None,
        )
    )

    service = ExecutorService()
    log_path = Path(run.artifact_dir) / "executor_worker.log"
    log_path.write_text("worker exited after completion\n", encoding="utf-8")

    service._mark_run_failed_after_worker_exit(run_id, 1, log_path)

    completed_run = run_store.get(run_id)
    assert completed_run.status == RunStatus.COMPLETED

    metrics = artifact_store.read_metrics(run_id)
    assert metrics is not None
    assert metrics["final_status"] == "COMPLETED"
