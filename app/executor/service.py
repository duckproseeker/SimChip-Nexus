from __future__ import annotations

import logging
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from app.core.config import get_settings
from app.core.logging import setup_logging
from app.core.models import EventLevel, RunEvent, RunMetrics, RunStatus
from app.orchestrator.queue import FileCommandQueue, RunCommandType
from app.storage.artifact_store import ArtifactStore
from app.storage.executor_store import ExecutorStore
from app.storage.run_store import RunStore
from app.utils.time_utils import now_utc

logger = logging.getLogger(__name__)
INTERRUPTED_RUN_STATUSES = {
    RunStatus.QUEUED,
    RunStatus.STARTING,
    RunStatus.RUNNING,
    RunStatus.PAUSED,
    RunStatus.STOPPING,
}


class ExecutorService:
    def __init__(self) -> None:
        self._settings = get_settings()
        self._run_store = RunStore(self._settings.runs_root)
        self._artifact_store = ArtifactStore(self._settings.artifacts_root)
        self._queue = FileCommandQueue(self._settings.commands_root)
        self._executor_store = ExecutorStore(self._settings.executor_root)

    def _fail_unsupported_legacy_run(
        self, run_id: str, execution_backend: str
    ) -> None:
        run = self._run_store.get(run_id)
        timestamp = now_utc()
        failure_reason = (
            f"运行 {run_id} 使用已废弃的执行后端 {execution_backend}。"
            "当前平台仅保留 native runtime 执行链，请重新创建 native run。"
        )
        self._artifact_store.append_event(
            RunEvent(
                timestamp=timestamp,
                run_id=run_id,
                level=EventLevel.ERROR,
                event_type="LEGACY_EXECUTION_BACKEND_RETIRED",
                message=failure_reason,
                payload={"execution_backend": execution_backend},
            )
        )
        self._artifact_store.append_run_log(
            run_id,
            f"[{timestamp.isoformat()}] ERROR LEGACY_EXECUTION_BACKEND_RETIRED {failure_reason}",
        )
        failed_run = self._run_store.transition(
            run_id,
            RunStatus.FAILED,
            error_reason=failure_reason,
            set_ended_at=True,
        )
        self._artifact_store.write_status(failed_run)
        self._artifact_store.write_metrics(
            RunMetrics(
                run_id=run_id,
                scenario_name=run.scenario_name,
                map_name=run.map_name,
                start_time=run.started_at or run.created_at,
                end_time=timestamp,
                final_status=RunStatus.FAILED,
                failure_reason=failure_reason,
            )
        )

    def _write_heartbeat(
        self, status: str, active_run_id: str | None = None, last_command_run_id: str | None = None
    ) -> None:
        self._executor_store.write_heartbeat(
            {
                "status": status,
                "active_run_id": active_run_id,
                "last_command_run_id": last_command_run_id,
                "updated_at_utc": now_utc().isoformat(),
                "pending_commands": self._queue.count_pending(),
            }
        )

    def _write_running_heartbeat(self, run_id: str) -> None:
        self._write_heartbeat(
            "RUNNING",
            active_run_id=run_id,
            last_command_run_id=run_id,
        )

    def _run_worker_log_path(self, run_id: str) -> Path:
        return self._artifact_store.run_dir(run_id) / "executor_worker.log"

    def _build_run_worker_command(self, run_id: str) -> list[str]:
        return [sys.executable, "-m", "app.executor.run_worker", "--run-id", run_id]

    def _worker_log_tail(self, log_path: Path, max_lines: int = 12) -> str | None:
        if not log_path.exists():
            return None
        try:
            lines = log_path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return None
        if not lines:
            return None
        tail = " | ".join(line.strip() for line in lines[-max_lines:] if line.strip())
        return tail or None

    def _worker_failure_reason(
        self, run_id: str, return_code: int, log_path: Path
    ) -> str:
        if return_code < 0:
            try:
                signal_name = signal.Signals(-return_code).name
            except ValueError:
                signal_name = f"SIG{-return_code}"
            summary = (
                f"native runtime worker for run {run_id} exited from signal {signal_name}"
            )
        else:
            summary = (
                f"native runtime worker for run {run_id} exited with code {return_code}"
            )
        log_tail = self._worker_log_tail(log_path)
        if log_tail:
            return f"{summary}. worker_log_tail={log_tail}"
        return summary

    def _mark_run_failed_after_worker_exit(
        self, run_id: str, return_code: int, log_path: Path
    ) -> None:
        run = self._run_store.get(run_id)
        if run.status in {
            RunStatus.COMPLETED,
            RunStatus.CANCELED,
            RunStatus.FAILED,
        }:
            return

        timestamp = now_utc()
        failure_reason = self._worker_failure_reason(run_id, return_code, log_path)
        self._artifact_store.append_event(
            RunEvent(
                timestamp=timestamp,
                run_id=run_id,
                level=EventLevel.ERROR,
                event_type="RUN_WORKER_EXITED_UNEXPECTEDLY",
                message="native runtime worker 异常退出，executor 已将 run 标记为 FAILED",
                payload={
                    "return_code": return_code,
                    "log_path": str(log_path),
                    "failure_reason": failure_reason,
                },
            )
        )
        self._artifact_store.append_run_log(
            run_id,
            (
                f"[{timestamp.isoformat()}] ERROR RUN_WORKER_EXITED_UNEXPECTEDLY "
                f"{failure_reason}"
            ),
        )
        failed_run = self._run_store.transition(
            run_id,
            RunStatus.FAILED,
            error_reason=failure_reason,
            set_ended_at=True,
        )
        self._artifact_store.write_status(failed_run)

        if self._artifact_store.read_metrics(run_id) is None:
            self._artifact_store.write_metrics(
                RunMetrics(
                    run_id=run_id,
                    scenario_name=run.scenario_name,
                    map_name=run.map_name,
                    start_time=run.started_at or run.created_at,
                    end_time=timestamp,
                    final_status=RunStatus.FAILED,
                    failure_reason=failure_reason,
                )
            )

    def _execute_run_in_subprocess(self, run_id: str) -> int:
        log_path = self._run_worker_log_path(run_id)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        command = self._build_run_worker_command(run_id)
        with log_path.open("a", encoding="utf-8") as handle:
            process = subprocess.Popen(
                command,
                stdout=handle,
                stderr=subprocess.STDOUT,
                text=True,
                env={**os.environ, "PYTHONUNBUFFERED": "1"},
            )
            self._artifact_store.append_run_log(
                run_id,
                (
                    f"[{now_utc().isoformat()}] INFO RUN_WORKER_STARTED "
                    f"pid={process.pid} command={' '.join(command)}"
                ),
            )
            heartbeat_interval = max(
                0.2, min(self._settings.command_poll_interval_seconds, 1.0)
            )
            while True:
                return_code = process.poll()
                if return_code is not None:
                    return return_code
                self._write_running_heartbeat(run_id)
                time.sleep(heartbeat_interval)

    def _recover_interrupted_runs(self) -> None:
        interrupted_runs = [
            run for run in self._run_store.list() if run.status in INTERRUPTED_RUN_STATUSES
        ]
        if not interrupted_runs:
            return

        for run in interrupted_runs:
            timestamp = now_utc()
            failure_reason = (
                "executor 服务重启时运行未完成，平台已将该 run 标记为 FAILED 以释放 CARLA。"
            )
            self._artifact_store.append_event(
                RunEvent(
                    timestamp=timestamp,
                    run_id=run.run_id,
                    level=EventLevel.WARNING,
                    event_type="RUN_RECOVERED_AFTER_EXECUTOR_RESTART",
                    message=failure_reason,
                    payload={"previous_status": run.status.value},
                )
            )
            self._artifact_store.append_run_log(
                run.run_id,
                (
                    f"[{timestamp.isoformat()}] WARNING "
                    "RUN_RECOVERED_AFTER_EXECUTOR_RESTART "
                    f"{failure_reason} previous_status={run.status.value}"
                ),
            )
            failed_run = self._run_store.transition(
                run.run_id,
                RunStatus.FAILED,
                error_reason=failure_reason,
                set_ended_at=True,
            )
            self._artifact_store.write_status(failed_run)
            self._artifact_store.write_metrics(
                RunMetrics(
                    run_id=run.run_id,
                    scenario_name=run.scenario_name,
                    map_name=run.map_name,
                    start_time=run.started_at or run.created_at,
                    end_time=timestamp,
                    final_status=RunStatus.FAILED,
                    failure_reason=failure_reason,
                )
            )
        logger.warning(
            "Recovered %s interrupted runs after executor restart",
            len(interrupted_runs),
        )

    def run_forever(self) -> None:
        logger.info("Executor service started")
        self._recover_interrupted_runs()
        self._write_heartbeat("READY")
        while True:
            self._write_heartbeat("READY")
            command = self._queue.pop_next()
            if command is None:
                time.sleep(self._settings.command_poll_interval_seconds)
                continue

            logger.info(
                "Received command %s for run %s", command.command_type, command.run_id
            )
            if command.command_type == RunCommandType.START:
                self._write_heartbeat(
                    "RUNNING",
                    active_run_id=command.run_id,
                    last_command_run_id=command.run_id,
                )
                try:
                    run = self._run_store.get(command.run_id)
                    if run.execution_backend == "native":
                        return_code = self._execute_run_in_subprocess(command.run_id)
                        if return_code != 0:
                            self._mark_run_failed_after_worker_exit(
                                command.run_id,
                                return_code,
                                self._run_worker_log_path(command.run_id),
                            )
                        else:
                            latest_run = self._run_store.get(command.run_id)
                            if latest_run.status in INTERRUPTED_RUN_STATUSES:
                                self._mark_run_failed_after_worker_exit(
                                    command.run_id,
                                    return_code,
                                    self._run_worker_log_path(command.run_id),
                                )
                    else:
                        self._fail_unsupported_legacy_run(
                            command.run_id, run.execution_backend
                        )
                finally:
                    self._write_heartbeat(
                        "READY", last_command_run_id=command.run_id
                    )


def main() -> None:
    setup_logging()
    service = ExecutorService()
    service.run_forever()


if __name__ == "__main__":
    main()
