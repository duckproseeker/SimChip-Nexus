from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from app.core.errors import ConflictError, NotFoundError
from app.core.models import ScenarioSourceMaterializationRecord, ScenarioSourceRecord
from app.utils.file_utils import ensure_dir
from app.utils.time_utils import now_utc


def _json_dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _json_load(value: str | None, default: Any) -> Any:
    if value is None or value == "":
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


class ScenarioSourceStore:
    def __init__(self, root: Path) -> None:
        self._root = ensure_dir(root)
        self._db_path = self._root / "scenario_recordings.sqlite3"
        self._initialize()

    @property
    def db_path(self) -> Path:
        return self._db_path

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS scenario_sources (
                    source_id TEXT PRIMARY KEY,
                    provider TEXT NOT NULL,
                    provider_version_json TEXT NOT NULL DEFAULT '{}',
                    source_path TEXT NOT NULL,
                    source_hash TEXT NOT NULL,
                    route_id TEXT,
                    scenario_type TEXT,
                    map_name TEXT NOT NULL,
                    weather_json TEXT NOT NULL DEFAULT '{}',
                    recommended_duration_seconds REAL,
                    corner_case_labels_json TEXT NOT NULL DEFAULT '[]',
                    compatibility_status TEXT NOT NULL,
                    compatibility_message TEXT,
                    parsed_metadata_json TEXT NOT NULL DEFAULT '{}',
                    discovered_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS scenario_source_materializations (
                    materialization_id TEXT PRIMARY KEY,
                    source_id TEXT NOT NULL,
                    run_id TEXT NOT NULL UNIQUE,
                    recording_id TEXT,
                    status TEXT NOT NULL,
                    sensor_profile_id TEXT,
                    sensor_profile_hash TEXT,
                    fixed_delta_seconds REAL NOT NULL,
                    materialization_agent_type TEXT NOT NULL,
                    materialization_agent_hash TEXT NOT NULL,
                    recorder_file_sha256 TEXT,
                    started_at TEXT,
                    completed_at TEXT,
                    error_message TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(source_id) REFERENCES scenario_sources(source_id)
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_scenario_sources_provider
                ON scenario_sources(provider)
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_scenario_sources_map
                ON scenario_sources(map_name)
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_scenario_source_materializations_source
                ON scenario_source_materializations(source_id)
                """
            )

    @staticmethod
    def _source_from_row(row: sqlite3.Row) -> ScenarioSourceRecord:
        return ScenarioSourceRecord.model_validate(
            {
                "source_id": row["source_id"],
                "provider": row["provider"],
                "provider_version": _json_load(row["provider_version_json"], {}),
                "source_path": row["source_path"],
                "source_hash": row["source_hash"],
                "route_id": row["route_id"],
                "scenario_type": row["scenario_type"],
                "map_name": row["map_name"],
                "weather": _json_load(row["weather_json"], {}),
                "recommended_duration_seconds": row["recommended_duration_seconds"],
                "corner_case_labels": _json_load(row["corner_case_labels_json"], []),
                "compatibility_status": row["compatibility_status"],
                "compatibility_message": row["compatibility_message"],
                "parsed_metadata": _json_load(row["parsed_metadata_json"], {}),
                "discovered_at": row["discovered_at"],
                "updated_at": row["updated_at"],
            }
        )

    @staticmethod
    def _materialization_from_row(row: sqlite3.Row) -> ScenarioSourceMaterializationRecord:
        return ScenarioSourceMaterializationRecord.model_validate(
            {
                "materialization_id": row["materialization_id"],
                "source_id": row["source_id"],
                "run_id": row["run_id"],
                "recording_id": row["recording_id"],
                "status": row["status"],
                "sensor_profile_id": row["sensor_profile_id"],
                "sensor_profile_hash": row["sensor_profile_hash"],
                "fixed_delta_seconds": row["fixed_delta_seconds"],
                "materialization_agent_type": row["materialization_agent_type"],
                "materialization_agent_hash": row["materialization_agent_hash"],
                "recorder_file_sha256": row["recorder_file_sha256"],
                "started_at": row["started_at"],
                "completed_at": row["completed_at"],
                "error_message": row["error_message"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }
        )

    def replace_sources(self, sources: list[ScenarioSourceRecord]) -> list[ScenarioSourceRecord]:
        with self._connect() as connection:
            for source in sources:
                existing = connection.execute(
                    "SELECT discovered_at FROM scenario_sources WHERE source_id = ?",
                    (source.source_id,),
                ).fetchone()
                discovered_at = (
                    str(existing["discovered_at"])
                    if existing is not None
                    else _iso(source.discovered_at)
                )
                connection.execute(
                    """
                    INSERT INTO scenario_sources (
                        source_id, provider, provider_version_json, source_path,
                        source_hash, route_id, scenario_type, map_name, weather_json,
                        recommended_duration_seconds, corner_case_labels_json,
                        compatibility_status, compatibility_message,
                        parsed_metadata_json, discovered_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(source_id) DO UPDATE SET
                        provider = excluded.provider,
                        provider_version_json = excluded.provider_version_json,
                        source_path = excluded.source_path,
                        source_hash = excluded.source_hash,
                        route_id = excluded.route_id,
                        scenario_type = excluded.scenario_type,
                        map_name = excluded.map_name,
                        weather_json = excluded.weather_json,
                        recommended_duration_seconds = excluded.recommended_duration_seconds,
                        corner_case_labels_json = excluded.corner_case_labels_json,
                        compatibility_status = excluded.compatibility_status,
                        compatibility_message = excluded.compatibility_message,
                        parsed_metadata_json = excluded.parsed_metadata_json,
                        updated_at = excluded.updated_at
                    """,
                    (
                        source.source_id,
                        source.provider,
                        _json_dump(source.provider_version),
                        source.source_path,
                        source.source_hash,
                        source.route_id,
                        source.scenario_type,
                        source.map_name,
                        _json_dump(source.weather),
                        source.recommended_duration_seconds,
                        _json_dump(source.corner_case_labels),
                        source.compatibility_status,
                        source.compatibility_message,
                        _json_dump(source.parsed_metadata),
                        discovered_at,
                        _iso(source.updated_at),
                    ),
                )
        return sources

    def get(self, source_id: str) -> ScenarioSourceRecord:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM scenario_sources WHERE source_id = ?",
                (source_id,),
            ).fetchone()
        if row is None:
            raise NotFoundError(f"Scenario source not found: {source_id}")
        return self._source_from_row(row)

    def list(
        self,
        *,
        provider: str | None = None,
        map_name: str | None = None,
        scenario_type: str | None = None,
        corner_case_label: str | None = None,
        compatibility_status: str | None = None,
    ) -> list[ScenarioSourceRecord]:
        clauses: list[str] = []
        params: list[Any] = []
        if provider:
            clauses.append("provider = ?")
            params.append(provider)
        if map_name:
            clauses.append("map_name = ?")
            params.append(map_name)
        if scenario_type:
            clauses.append("scenario_type = ?")
            params.append(scenario_type)
        if compatibility_status:
            clauses.append("compatibility_status = ?")
            params.append(compatibility_status)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._connect() as connection:
            rows = connection.execute(
                f"SELECT * FROM scenario_sources {where} ORDER BY provider, map_name, source_id",
                tuple(params),
            ).fetchall()
        items = [self._source_from_row(row) for row in rows]
        if corner_case_label:
            items = [
                item
                for item in items
                if corner_case_label in item.corner_case_labels
            ]
        return items

    def create_materialization(
        self, materialization: ScenarioSourceMaterializationRecord
    ) -> ScenarioSourceMaterializationRecord:
        self.get(materialization.source_id)
        with self._connect() as connection:
            try:
                connection.execute(
                    """
                    INSERT INTO scenario_source_materializations (
                        materialization_id, source_id, run_id, recording_id, status,
                        sensor_profile_id, sensor_profile_hash, fixed_delta_seconds,
                        materialization_agent_type, materialization_agent_hash,
                        recorder_file_sha256, started_at, completed_at, error_message,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        materialization.materialization_id,
                        materialization.source_id,
                        materialization.run_id,
                        materialization.recording_id,
                        materialization.status,
                        materialization.sensor_profile_id,
                        materialization.sensor_profile_hash,
                        float(materialization.fixed_delta_seconds),
                        materialization.materialization_agent_type,
                        materialization.materialization_agent_hash,
                        materialization.recorder_file_sha256,
                        _iso(materialization.started_at),
                        _iso(materialization.completed_at),
                        materialization.error_message,
                        _iso(materialization.created_at),
                        _iso(materialization.updated_at),
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise ConflictError(
                    f"Scenario source materialization already exists: {materialization.run_id}"
                ) from exc
        return materialization

    def update_materialization(
        self,
        materialization_id: str,
        *,
        status: str | None = None,
        recording_id: str | None = None,
        recorder_file_sha256: str | None = None,
        completed_at: Any | None = None,
        error_message: str | None = None,
    ) -> ScenarioSourceMaterializationRecord:
        current = self.get_materialization(materialization_id)
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE scenario_source_materializations
                SET status = ?,
                    recording_id = ?,
                    recorder_file_sha256 = ?,
                    completed_at = ?,
                    error_message = ?,
                    updated_at = ?
                WHERE materialization_id = ?
                """,
                (
                    status or current.status,
                    recording_id if recording_id is not None else current.recording_id,
                    (
                        recorder_file_sha256
                        if recorder_file_sha256 is not None
                        else current.recorder_file_sha256
                    ),
                    _iso(completed_at) if completed_at is not None else _iso(current.completed_at),
                    error_message if error_message is not None else current.error_message,
                    _iso(now_utc()),
                    materialization_id,
                ),
            )
        return self.get_materialization(materialization_id)

    def get_materialization(self, materialization_id: str) -> ScenarioSourceMaterializationRecord:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM scenario_source_materializations
                WHERE materialization_id = ?
                """,
                (materialization_id,),
            ).fetchone()
        if row is None:
            raise NotFoundError(
                f"Scenario source materialization not found: {materialization_id}"
            )
        return self._materialization_from_row(row)

    def get_materialization_by_run_id(
        self, run_id: str
    ) -> ScenarioSourceMaterializationRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM scenario_source_materializations
                WHERE run_id = ?
                """,
                (run_id,),
            ).fetchone()
        return None if row is None else self._materialization_from_row(row)

    def list_materializations(
        self, source_id: str | None = None
    ) -> list[ScenarioSourceMaterializationRecord]:
        params: tuple[Any, ...] = ()
        where = ""
        if source_id is not None:
            where = "WHERE source_id = ?"
            params = (source_id,)
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT * FROM scenario_source_materializations
                {where}
                ORDER BY created_at DESC
                """,
                params,
            ).fetchall()
        return [self._materialization_from_row(row) for row in rows]
