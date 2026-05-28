from __future__ import annotations

import json
import sqlite3
import uuid
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.core.config import get_settings
from app.core.models import ScenarioAsset
from app.utils.time_utils import now_utc


class ScenarioAssetStore:
    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._initialize()

    def _initialize(self) -> None:
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS scenario_assets (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                recorder_log_path TEXT NOT NULL,
                map_name TEXT NOT NULL DEFAULT '',
                duration_seconds REAL NOT NULL DEFAULT 0.0,
                tags_json TEXT NOT NULL DEFAULT '[]',
                description TEXT NOT NULL DEFAULT '',
                file_size_bytes INTEGER NOT NULL DEFAULT 0,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL
            )
        """)
        self._conn.commit()

    def create(
        self,
        name: str,
        recorder_log_path: str,
        map_name: str = "",
        duration_seconds: float = 0.0,
        tags: list[str] | None = None,
        description: str = "",
        file_size_bytes: int = 0,
        metadata: dict[str, Any] | None = None,
    ) -> ScenarioAsset:
        asset_id = f"scene_{uuid.uuid4().hex[:12]}"
        ts = now_utc()
        created_at = ts.isoformat() if hasattr(ts, "isoformat") else str(ts)
        self._conn.execute(
            """INSERT INTO scenario_assets
               (id, name, recorder_log_path, map_name, duration_seconds,
                tags_json, description, file_size_bytes, metadata_json, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                asset_id, name, recorder_log_path, map_name, duration_seconds,
                json.dumps(tags or [], ensure_ascii=False),
                description, file_size_bytes,
                json.dumps(metadata or {}, ensure_ascii=False),
                created_at,
            ),
        )
        self._conn.commit()
        return self.get(asset_id)

    def get(self, asset_id: str) -> ScenarioAsset:
        row = self._conn.execute(
            "SELECT * FROM scenario_assets WHERE id = ?", (asset_id,)
        ).fetchone()
        if row is None:
            raise KeyError(f"Scenario asset not found: {asset_id}")
        return self._row_to_model(row)

    def list(
        self, tag: str | None = None, map_name: str | None = None
    ) -> list[ScenarioAsset]:
        query = "SELECT * FROM scenario_assets WHERE 1=1"
        params: list[str] = []
        if map_name:
            query += " AND map_name = ?"
            params.append(map_name)
        if tag:
            query += " AND tags_json LIKE ?"
            params.append(f'%"{tag}"%')
        query += " ORDER BY created_at DESC"
        rows = self._conn.execute(query, params).fetchall()
        return [self._row_to_model(r) for r in rows]

    def update(self, asset_id: str, **kwargs: Any) -> ScenarioAsset:
        allowed = {"name", "map_name", "duration_seconds", "tags",
                   "description", "metadata"}
        sets: list[str] = []
        params: list[Any] = []
        for key, value in kwargs.items():
            if key not in allowed:
                continue
            if key == "tags":
                sets.append("tags_json = ?")
                params.append(json.dumps(value, ensure_ascii=False))
            elif key == "metadata":
                sets.append("metadata_json = ?")
                params.append(json.dumps(value, ensure_ascii=False))
            else:
                sets.append(f"{key} = ?")
                params.append(value)
        if not sets:
            return self.get(asset_id)
        params.append(asset_id)
        self._conn.execute(
            f"UPDATE scenario_assets SET {', '.join(sets)} WHERE id = ?",
            params,
        )
        self._conn.commit()
        return self.get(asset_id)

    def delete(self, asset_id: str) -> None:
        self._conn.execute(
            "DELETE FROM scenario_assets WHERE id = ?", (asset_id,)
        )
        self._conn.commit()

    def _row_to_model(self, row: sqlite3.Row) -> ScenarioAsset:
        return ScenarioAsset(
            id=row["id"],
            name=row["name"],
            recorder_log_path=row["recorder_log_path"],
            map_name=row["map_name"],
            duration_seconds=row["duration_seconds"],
            tags=json.loads(row["tags_json"]),
            description=row["description"],
            file_size_bytes=row["file_size_bytes"],
            created_at=row["created_at"],
            metadata=json.loads(row["metadata_json"]),
        )


@lru_cache(maxsize=1)
def get_scenario_asset_store() -> ScenarioAssetStore:
    settings = get_settings()
    db_path = settings.scenario_recordings_root / "scenario_assets.sqlite3"
    return ScenarioAssetStore(db_path)
