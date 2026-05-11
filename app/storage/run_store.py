from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

from app.core.errors import ConflictError, NotFoundError
from app.core.models import RunRecord, RunStatus
from app.orchestrator.state_machine import validate_transition
from app.utils.file_utils import ensure_dir
from app.utils.time_utils import now_utc

RunUpdater = Callable[[RunRecord], RunRecord]


class RunStore:
    """File-based persistence for run records."""

    def __init__(self, runs_root: Path) -> None:
        self._runs_root = ensure_dir(runs_root)

    def _run_path(self, run_id: str) -> Path:
        return self._runs_root / f"{run_id}.json"

    def create(self, run: RunRecord) -> RunRecord:
        path = self._run_path(run.run_id)
        if path.exists():
            raise ConflictError(f"Run already exists: {run.run_id}")

        with path.open("w", encoding="utf-8") as handle:
            json.dump(run.model_dump(mode="json"), handle, indent=2, ensure_ascii=False)
        return run

    def get(self, run_id: str) -> RunRecord:
        path = self._run_path(run_id)
        if not path.exists():
            raise NotFoundError(f"Run not found: {run_id}")

        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        return RunRecord.model_validate(payload)

    def list(self, status: RunStatus | None = None) -> list[RunRecord]:
        runs: list[RunRecord] = []
        for path in sorted(self._runs_root.glob("*.json")):
            with path.open("r", encoding="utf-8") as handle:
                payload = json.load(handle)
            run = RunRecord.model_validate(payload)
            if status is None or run.status == status:
                runs.append(run)
        return runs

    def save(self, run: RunRecord) -> RunRecord:
        path = self._run_path(run.run_id)
        if not path.exists():
            raise NotFoundError(f"Run not found: {run.run_id}")

        run.updated_at = now_utc()
        with path.open("w", encoding="utf-8") as handle:
            json.dump(run.model_dump(mode="json"), handle, indent=2, ensure_ascii=False)
        return run

    def update(self, run_id: str, updater: RunUpdater) -> RunRecord:
        run = self.get(run_id)
        updated = updater(run)
        return self.save(updated)

    def transition(
        self,
        run_id: str,
        target: RunStatus,
        error_reason: str | None = None,
        set_started_at: bool = False,
        set_ended_at: bool = False,
    ) -> RunRecord:
        def _apply_transition(run: RunRecord) -> RunRecord:
            validate_transition(run.status, target)
            run.status = target
            if set_started_at and run.started_at is None:
                run.started_at = now_utc()
            if set_ended_at:
                run.ended_at = now_utc()
            run.error_reason = error_reason
            return run

        return self.update(run_id, _apply_transition)

    def mark_stop_requested(
        self, run_id: str, cancel_requested: bool = False
    ) -> RunRecord:
        def _mark(run: RunRecord) -> RunRecord:
            run.stop_requested = True
            if cancel_requested:
                run.cancel_requested = True
            return run

        return self.update(run_id, _mark)

    def update_descriptor_sections(
        self,
        run_id: str,
        weather: dict[str, object] | None = None,
        debug: dict[str, object] | None = None,
        sensors: dict[str, object] | None = None,
    ) -> RunRecord:
        def _update(run: RunRecord) -> RunRecord:
            descriptor = dict(run.descriptor)
            if weather is not None:
                descriptor["weather"] = weather
                run.map_name = str(descriptor.get("map_name", run.map_name))
            if debug is not None:
                descriptor["debug"] = debug
            if sensors is not None:
                descriptor["sensors"] = sensors
            run.descriptor = descriptor
            return run

        return self.update(run_id, _update)
