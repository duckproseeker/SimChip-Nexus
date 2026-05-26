from __future__ import annotations

import uuid
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

from app.core.models import PipelineExecutionRecord, PipelineExecutionStatus


class PipelineExecutionStore:
    def __init__(self, root: Path) -> None:
        self._root = root
        self._root.mkdir(parents=True, exist_ok=True)

    def _path(self, execution_id: str) -> Path:
        return self._root / f"{execution_id}.json"

    def create(self, pipeline_id: str) -> PipelineExecutionRecord:
        now = datetime.now(timezone.utc)
        record = PipelineExecutionRecord(
            execution_id=str(uuid.uuid4()),
            pipeline_id=pipeline_id,
            status=PipelineExecutionStatus.PENDING,
            node_states={},
            created_at=now,
            updated_at=now,
        )
        self._path(record.execution_id).write_text(record.model_dump_json())
        return record

    def get(self, execution_id: str) -> PipelineExecutionRecord:
        path = self._path(execution_id)
        if not path.exists():
            raise KeyError(f"PipelineExecution not found: {execution_id}")
        return PipelineExecutionRecord.model_validate_json(path.read_text())

    def save(self, record: PipelineExecutionRecord) -> PipelineExecutionRecord:
        record.updated_at = datetime.now(timezone.utc)
        self._path(record.execution_id).write_text(record.model_dump_json())
        return record

    def list_for_pipeline(self, pipeline_id: str) -> list[PipelineExecutionRecord]:
        records = []
        for path in sorted(self._root.glob("*.json")):
            try:
                r = PipelineExecutionRecord.model_validate_json(path.read_text())
                if r.pipeline_id == pipeline_id:
                    records.append(r)
            except Exception:
                continue
        return records


@lru_cache(maxsize=1)
def get_pipeline_execution_store() -> PipelineExecutionStore:
    from app.core.config import get_settings
    return PipelineExecutionStore(get_settings().pipeline_executions_root)
