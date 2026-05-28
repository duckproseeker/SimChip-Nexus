from __future__ import annotations

import json
import sqlite3
import uuid
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.core.models import DatasetRecord, DatasetStatus, SensorConfig
from app.utils.time_utils import now_utc


class DatasetStore:
    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._initialize()

    def _initialize(self) -> None:
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS datasets (
                dataset_id TEXT PRIMARY KEY,
                scenario_id TEXT NOT NULL,
                pipeline_id TEXT NOT NULL DEFAULT '',
                name TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'PENDING',
                sensor_configs_json TEXT NOT NULL DEFAULT '[]',
                total_frames INTEGER NOT NULL DEFAULT 0,
                rendered_frames INTEGER NOT NULL DEFAULT 0,
                delta_seconds REAL NOT NULL DEFAULT 0.05,
                duration_seconds REAL NOT NULL DEFAULT 0.0,
                output_dir TEXT NOT NULL DEFAULT '',
                error_message TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        self._conn.commit()

    def create(self, record: DatasetRecord) -> DatasetRecord:
        ts = now_utc().isoformat()
        if not record.dataset_id:
            record.dataset_id = f"ds_{uuid.uuid4().hex[:12]}"
        if not record.created_at:
            record.created_at = ts
        if not record.updated_at:
            record.updated_at = ts
        sensor_configs_json = json.dumps(
            [sc.model_dump() for sc in record.sensor_configs], ensure_ascii=False
        )
        self._conn.execute(
            """INSERT INTO datasets
               (dataset_id, scenario_id, pipeline_id, name, status,
                sensor_configs_json, total_frames, rendered_frames,
                delta_seconds, duration_seconds, output_dir,
                error_message, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                record.dataset_id, record.scenario_id, record.pipeline_id,
                record.name, record.status.value, sensor_configs_json,
                record.total_frames, record.rendered_frames,
                record.delta_seconds, record.duration_seconds,
                record.output_dir, record.error_message,
                record.created_at, record.updated_at,
            ),
        )
        self._conn.commit()
        return self.get(record.dataset_id)

    def get(self, dataset_id: str) -> DatasetRecord:
        row = self._conn.execute(
            "SELECT * FROM datasets WHERE dataset_id = ?", (dataset_id,)
        ).fetchone()
        if row is None:
            raise KeyError(f"Dataset not found: {dataset_id}")
        return self._row_to_model(row)

    def list(self, scenario_id: str | None = None) -> list[DatasetRecord]:
        query = "SELECT * FROM datasets WHERE 1=1"
        params: list[str] = []
        if scenario_id:
            query += " AND scenario_id = ?"
            params.append(scenario_id)
        query += " ORDER BY created_at DESC"
        rows = self._conn.execute(query, params).fetchall()
        return [self._row_to_model(r) for r in rows]

    def update(self, dataset_id: str, **kwargs: Any) -> DatasetRecord:
        allowed = {
            "name", "status", "sensor_configs", "total_frames",
            "rendered_frames", "delta_seconds", "duration_seconds",
            "output_dir", "error_message", "pipeline_id",
        }
        sets: list[str] = []
        params: list[Any] = []
        for key, value in kwargs.items():
            if key not in allowed:
                continue
            if key == "sensor_configs":
                sets.append("sensor_configs_json = ?")
                params.append(json.dumps(
                    [sc.model_dump() if isinstance(sc, SensorConfig) else sc
                     for sc in value],
                    ensure_ascii=False,
                ))
            elif key == "status":
                sets.append("status = ?")
                v = value.value if isinstance(value, DatasetStatus) else value
                params.append(v)
            else:
                sets.append(f"{key} = ?")
                params.append(value)
        if not sets:
            return self.get(dataset_id)
        sets.append("updated_at = ?")
        params.append(now_utc().isoformat())
        params.append(dataset_id)
        self._conn.execute(
            f"UPDATE datasets SET {', '.join(sets)} WHERE dataset_id = ?",
            params,
        )
        self._conn.commit()
        return self.get(dataset_id)

    def delete(self, dataset_id: str) -> None:
        self._conn.execute(
            "DELETE FROM datasets WHERE dataset_id = ?", (dataset_id,)
        )
        self._conn.commit()

    def _row_to_model(self, row: sqlite3.Row) -> DatasetRecord:
        sensor_configs_raw = json.loads(row["sensor_configs_json"])
        return DatasetRecord(
            dataset_id=row["dataset_id"],
            scenario_id=row["scenario_id"],
            pipeline_id=row["pipeline_id"],
            name=row["name"],
            status=DatasetStatus(row["status"]),
            sensor_configs=[SensorConfig(**sc) for sc in sensor_configs_raw],
            total_frames=row["total_frames"],
            rendered_frames=row["rendered_frames"],
            delta_seconds=row["delta_seconds"],
            duration_seconds=row["duration_seconds"],
            output_dir=row["output_dir"],
            error_message=row["error_message"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


@lru_cache(maxsize=1)
def get_dataset_store() -> DatasetStore:
    from app.core.config import get_settings
    settings = get_settings()
    db_path = Path(settings.scenario_recordings_root) / "datasets.sqlite3"
    return DatasetStore(db_path)