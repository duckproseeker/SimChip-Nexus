from __future__ import annotations

import uuid
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

from app.core.models import PipelineRecord


class PipelineStore:
    def __init__(self, root: Path) -> None:
        self._root = root
        self._root.mkdir(parents=True, exist_ok=True)

    def _path(self, pipeline_id: str) -> Path:
        return self._root / f"{pipeline_id}.json"

    def create(self, name: str, description: str = "") -> PipelineRecord:
        now = datetime.now(timezone.utc)
        record = PipelineRecord(
            pipeline_id=str(uuid.uuid4()),
            name=name,
            description=description,
            nodes=[],
            edges=[],
            created_at=now,
            updated_at=now,
        )
        self._path(record.pipeline_id).write_text(record.model_dump_json())
        return record

    def get(self, pipeline_id: str) -> PipelineRecord:
        path = self._path(pipeline_id)
        if not path.exists():
            raise KeyError(f"Pipeline not found: {pipeline_id}")
        return PipelineRecord.model_validate_json(path.read_text())

    def save(self, record: PipelineRecord) -> PipelineRecord:
        record.updated_at = datetime.now(timezone.utc)
        self._path(record.pipeline_id).write_text(record.model_dump_json())
        return record

    def delete(self, pipeline_id: str) -> None:
        path = self._path(pipeline_id)
        if not path.exists():
            raise KeyError(f"Pipeline not found: {pipeline_id}")
        path.unlink()

    def list(self) -> list[PipelineRecord]:
        records = []
        for path in sorted(self._root.glob("*.json")):
            try:
                records.append(PipelineRecord.model_validate_json(path.read_text()))
            except Exception:
                continue
        return records


@lru_cache(maxsize=1)
def get_pipeline_store() -> PipelineStore:
    from app.core.config import get_settings
    return PipelineStore(get_settings().pipelines_root)
