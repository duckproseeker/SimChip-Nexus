from __future__ import annotations

import json
from pathlib import Path

from app.core.errors import ConflictError, NotFoundError
from app.core.models import BenchmarkTaskRecord
from app.utils.file_utils import atomic_write_json, ensure_dir
from app.utils.time_utils import now_utc


class BenchmarkTaskStore:
    def __init__(self, benchmark_tasks_root: Path) -> None:
        self._benchmark_tasks_root = ensure_dir(benchmark_tasks_root)

    def _task_path(self, benchmark_task_id: str) -> Path:
        return self._benchmark_tasks_root / f"{benchmark_task_id}.json"

    def create(self, task: BenchmarkTaskRecord) -> BenchmarkTaskRecord:
        path = self._task_path(task.benchmark_task_id)
        if path.exists():
            raise ConflictError(f"Benchmark task already exists: {task.benchmark_task_id}")
        atomic_write_json(path, task.model_dump(mode="json"))
        return task

    def save(self, task: BenchmarkTaskRecord) -> BenchmarkTaskRecord:
        path = self._task_path(task.benchmark_task_id)
        task.updated_at = now_utc()
        atomic_write_json(path, task.model_dump(mode="json"))
        return task

    def get(self, benchmark_task_id: str) -> BenchmarkTaskRecord:
        path = self._task_path(benchmark_task_id)
        if not path.exists():
            raise NotFoundError(f"Benchmark task not found: {benchmark_task_id}")
        with path.open("r", encoding="utf-8") as handle:
            return BenchmarkTaskRecord.model_validate(json.load(handle))

    def list(self) -> list[BenchmarkTaskRecord]:
        items: list[BenchmarkTaskRecord] = []
        for path in sorted(self._benchmark_tasks_root.glob("*.json")):
            with path.open("r", encoding="utf-8") as handle:
                items.append(BenchmarkTaskRecord.model_validate(json.load(handle)))
        return items
