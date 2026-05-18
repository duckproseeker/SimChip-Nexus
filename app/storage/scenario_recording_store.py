from __future__ import annotations

import json
import re
import sqlite3
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from app.core.errors import ConflictError, NotFoundError
from app.core.models import RecordingReplayRunRecord, ScenarioRecordingRecord
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


def _iso(value: Any) -> str:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _normalize_collection(values: Iterable[str] | None) -> list[str]:
    if values is None:
        return []
    normalized: list[str] = []
    seen: set[str] = set()
    for value in values:
        candidate = str(value).strip()
        if not candidate or candidate in seen:
            continue
        normalized.append(candidate)
        seen.add(candidate)
    return normalized


def build_recording_id(source_run_id: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9_-]+", "_", source_run_id.strip()).strip("_")
    return f"rec_{normalized or now_utc().strftime('%Y%m%d%H%M%S')}"


class ScenarioRecordingStore:
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
                CREATE TABLE IF NOT EXISTS scenario_recordings (
                    recording_id TEXT PRIMARY KEY,
                    name TEXT,
                    source_run_id TEXT NOT NULL UNIQUE,
                    source_run_status TEXT,
                    source_id TEXT,
                    source_provider TEXT,
                    materialization_id TEXT,
                    source_type TEXT,
                    source_ref TEXT,
                    scenario_name TEXT NOT NULL,
                    map_name TEXT NOT NULL,
                    carla_version TEXT,
                    map_version TEXT,
                    recorder_log_path TEXT NOT NULL,
                    recorder_file_size_bytes INTEGER NOT NULL DEFAULT 0,
                    recorder_file_sha256 TEXT,
                    duration_seconds REAL,
                    recommended_start_seconds REAL,
                    recommended_duration_seconds REAL,
                    tags_json TEXT NOT NULL DEFAULT '[]',
                    corner_case_labels_json TEXT NOT NULL DEFAULT '[]',
                    weather_json TEXT NOT NULL DEFAULT '{}',
                    traffic_density_json TEXT NOT NULL DEFAULT '{}',
                    sensor_profile_name TEXT,
                    determinism_level TEXT NOT NULL,
                    notes TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            self._ensure_column(connection, "scenario_recordings", "source_id", "TEXT")
            self._ensure_column(connection, "scenario_recordings", "source_provider", "TEXT")
            self._ensure_column(connection, "scenario_recordings", "materialization_id", "TEXT")
            self._ensure_column(connection, "scenario_recordings", "name", "TEXT")
            self._ensure_column(connection, "scenario_recordings", "source_type", "TEXT")
            self._ensure_column(connection, "scenario_recordings", "source_ref", "TEXT")
            self._ensure_column(connection, "scenario_recordings", "carla_version", "TEXT")
            self._ensure_column(connection, "scenario_recordings", "map_version", "TEXT")
            self._ensure_column(connection, "scenario_recordings", "recorder_file_sha256", "TEXT")
            self._ensure_column(connection, "scenario_recordings", "duration_seconds", "REAL")
            self._ensure_column(
                connection, "scenario_recordings", "recommended_start_seconds", "REAL"
            )
            self._ensure_column(
                connection, "scenario_recordings", "recommended_duration_seconds", "REAL"
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS recording_replay_runs (
                    recording_id TEXT NOT NULL,
                    run_id TEXT NOT NULL PRIMARY KEY,
                    start_seconds REAL NOT NULL,
                    duration_seconds REAL NOT NULL,
                    sensor_mode TEXT NOT NULL,
                    sensor_profile_id TEXT,
                    sensor_profile_hash TEXT,
                    sensor_profile_snapshot_json TEXT NOT NULL DEFAULT '{}',
                    preview_sensor_id TEXT,
                    preview_sensor_snapshot_json TEXT NOT NULL DEFAULT '{}',
                    fixed_delta_seconds REAL NOT NULL,
                    sensor_warmup_seconds REAL NOT NULL DEFAULT 0,
                    timebase TEXT NOT NULL DEFAULT 'synchronous_fixed_delta',
                    hil_clock_mode TEXT NOT NULL DEFAULT 'fixed_delta',
                    output_config_summary_json TEXT NOT NULL DEFAULT '{}',
                    report_config_summary_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(recording_id) REFERENCES scenario_recordings(recording_id)
                )
                """
            )
            self._ensure_column(connection, "recording_replay_runs", "sensor_profile_id", "TEXT")
            self._ensure_column(connection, "recording_replay_runs", "sensor_profile_hash", "TEXT")
            self._ensure_column(
                connection,
                "recording_replay_runs",
                "sensor_profile_snapshot_json",
                "TEXT NOT NULL DEFAULT '{}'",
            )
            self._ensure_column(connection, "recording_replay_runs", "preview_sensor_id", "TEXT")
            self._ensure_column(
                connection,
                "recording_replay_runs",
                "preview_sensor_snapshot_json",
                "TEXT NOT NULL DEFAULT '{}'",
            )
            self._ensure_column(
                connection,
                "recording_replay_runs",
                "sensor_warmup_seconds",
                "REAL NOT NULL DEFAULT 0",
            )
            self._ensure_column(
                connection,
                "recording_replay_runs",
                "timebase",
                "TEXT NOT NULL DEFAULT 'synchronous_fixed_delta'",
            )
            self._ensure_column(
                connection,
                "recording_replay_runs",
                "hil_clock_mode",
                "TEXT NOT NULL DEFAULT 'fixed_delta'",
            )
            self._ensure_column(
                connection,
                "recording_replay_runs",
                "output_config_summary_json",
                "TEXT NOT NULL DEFAULT '{}'",
            )
            self._ensure_column(
                connection,
                "recording_replay_runs",
                "report_config_summary_json",
                "TEXT NOT NULL DEFAULT '{}'",
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_scenario_recordings_map
                ON scenario_recordings(map_name)
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_scenario_recordings_determinism
                ON scenario_recordings(determinism_level)
                """
            )

    @staticmethod
    def _record_from_row(row: sqlite3.Row) -> ScenarioRecordingRecord:
        return ScenarioRecordingRecord.model_validate(
            {
                "recording_id": row["recording_id"],
                "name": row["name"],
                "source_run_id": row["source_run_id"],
                "source_run_status": row["source_run_status"],
                "source_id": row["source_id"],
                "source_provider": row["source_provider"],
                "materialization_id": row["materialization_id"],
                "source_type": row["source_type"],
                "source_ref": row["source_ref"],
                "scenario_name": row["scenario_name"],
                "map_name": row["map_name"],
                "carla_version": row["carla_version"],
                "map_version": row["map_version"],
                "recorder_log_path": row["recorder_log_path"],
                "recorder_file_size_bytes": row["recorder_file_size_bytes"],
                "recorder_file_sha256": row["recorder_file_sha256"],
                "duration_seconds": row["duration_seconds"],
                "recommended_start_seconds": row["recommended_start_seconds"],
                "recommended_duration_seconds": row["recommended_duration_seconds"],
                "tags": _json_load(row["tags_json"], []),
                "corner_case_labels": _json_load(row["corner_case_labels_json"], []),
                "weather": _json_load(row["weather_json"], {}),
                "traffic_density": _json_load(row["traffic_density_json"], {}),
                "sensor_profile_name": row["sensor_profile_name"],
                "determinism_level": row["determinism_level"],
                "notes": row["notes"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }
        )

    def create(self, recording: ScenarioRecordingRecord) -> ScenarioRecordingRecord:
        with self._connect() as connection:
            existing = connection.execute(
                "SELECT * FROM scenario_recordings WHERE source_run_id = ?",
                (recording.source_run_id,),
            ).fetchone()
            if existing is not None:
                return self._record_from_row(existing)
            try:
                connection.execute(
                    """
                    INSERT INTO scenario_recordings (
                        recording_id,
                        name,
                        source_run_id,
                        source_run_status,
                        source_id,
                        source_provider,
                        materialization_id,
                        source_type,
                        source_ref,
                        scenario_name,
                        map_name,
                        carla_version,
                        map_version,
                        recorder_log_path,
                        recorder_file_size_bytes,
                        recorder_file_sha256,
                        duration_seconds,
                        recommended_start_seconds,
                        recommended_duration_seconds,
                        tags_json,
                        corner_case_labels_json,
                        weather_json,
                        traffic_density_json,
                        sensor_profile_name,
                        determinism_level,
                        notes,
                        created_at,
                        updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        recording.recording_id,
                        recording.name,
                        recording.source_run_id,
                        recording.source_run_status,
                        recording.source_id,
                        recording.source_provider,
                        recording.materialization_id,
                        recording.source_type,
                        recording.source_ref,
                        recording.scenario_name,
                        recording.map_name,
                        recording.carla_version,
                        recording.map_version,
                        recording.recorder_log_path,
                        int(recording.recorder_file_size_bytes),
                        recording.recorder_file_sha256,
                        recording.duration_seconds,
                        recording.recommended_start_seconds,
                        recording.recommended_duration_seconds,
                        _json_dump(_normalize_collection(recording.tags)),
                        _json_dump(_normalize_collection(recording.corner_case_labels)),
                        _json_dump(recording.weather),
                        _json_dump(recording.traffic_density),
                        recording.sensor_profile_name,
                        recording.determinism_level,
                        recording.notes,
                        _iso(recording.created_at),
                        _iso(recording.updated_at),
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise ConflictError(
                    f"Scenario recording already exists: {recording.recording_id}"
                ) from exc
        return recording

    @staticmethod
    def _ensure_column(
        connection: sqlite3.Connection, table_name: str, column_name: str, definition: str
    ) -> None:
        columns = {
            str(row["name"])
            for row in connection.execute(f"PRAGMA table_info({table_name})").fetchall()
        }
        if column_name not in columns:
            connection.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}")

    def get(self, recording_id: str) -> ScenarioRecordingRecord:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM scenario_recordings WHERE recording_id = ?",
                (recording_id,),
            ).fetchone()
        if row is None:
            raise NotFoundError(f"Scenario recording not found: {recording_id}")
        return self._record_from_row(row)

    def get_by_source_run_id(self, source_run_id: str) -> ScenarioRecordingRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM scenario_recordings WHERE source_run_id = ?",
                (source_run_id,),
            ).fetchone()
        return None if row is None else self._record_from_row(row)

    def list(
        self,
        *,
        map_name: str | None = None,
        tag: str | None = None,
        corner_case_label: str | None = None,
        determinism_level: str | None = None,
    ) -> list[ScenarioRecordingRecord]:
        clauses: list[str] = []
        params: list[Any] = []
        if map_name:
            clauses.append("map_name = ?")
            params.append(map_name)
        if determinism_level:
            clauses.append("determinism_level = ?")
            params.append(determinism_level)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        query = f"SELECT * FROM scenario_recordings {where} ORDER BY created_at DESC"
        with self._connect() as connection:
            rows = connection.execute(query, tuple(params)).fetchall()

        items = [self._record_from_row(row) for row in rows]
        if tag:
            items = [item for item in items if tag in item.tags]
        if corner_case_label:
            items = [item for item in items if corner_case_label in item.corner_case_labels]
        return items

    def create_replay_run(
        self,
        replay_run: RecordingReplayRunRecord,
    ) -> RecordingReplayRunRecord:
        self.get(replay_run.recording_id)
        with self._connect() as connection:
            try:
                connection.execute(
                    """
                    INSERT INTO recording_replay_runs (
                        recording_id,
                        run_id,
                        start_seconds,
                        duration_seconds,
                        sensor_mode,
                        sensor_profile_id,
                        sensor_profile_hash,
                        sensor_profile_snapshot_json,
                        preview_sensor_id,
                        preview_sensor_snapshot_json,
                        fixed_delta_seconds,
                        sensor_warmup_seconds,
                        timebase,
                        hil_clock_mode,
                        output_config_summary_json,
                        report_config_summary_json,
                        created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        replay_run.recording_id,
                        replay_run.run_id,
                        float(replay_run.start_seconds),
                        float(replay_run.duration_seconds),
                        replay_run.sensor_mode,
                        replay_run.sensor_profile_id,
                        replay_run.sensor_profile_hash,
                        _json_dump(replay_run.sensor_profile_snapshot),
                        replay_run.preview_sensor_id,
                        _json_dump(replay_run.preview_sensor_snapshot),
                        float(replay_run.fixed_delta_seconds),
                        float(replay_run.sensor_warmup_seconds),
                        replay_run.timebase,
                        replay_run.hil_clock_mode,
                        _json_dump(replay_run.output_config_summary),
                        _json_dump(replay_run.report_config_summary),
                        _iso(replay_run.created_at),
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise ConflictError(f"Replay run already linked: {replay_run.run_id}") from exc
        return replay_run

    def list_replay_runs(self, recording_id: str) -> list[RecordingReplayRunRecord]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM recording_replay_runs
                WHERE recording_id = ?
                ORDER BY created_at DESC
                """,
                (recording_id,),
            ).fetchall()
        return [
            RecordingReplayRunRecord.model_validate(
                {
                    "recording_id": row["recording_id"],
                    "run_id": row["run_id"],
                    "start_seconds": row["start_seconds"],
                    "duration_seconds": row["duration_seconds"],
                    "sensor_mode": row["sensor_mode"],
                    "sensor_profile_id": row["sensor_profile_id"] or "",
                    "sensor_profile_hash": row["sensor_profile_hash"] or "",
                    "sensor_profile_snapshot": _json_load(row["sensor_profile_snapshot_json"], {}),
                    "preview_sensor_id": row["preview_sensor_id"] or "",
                    "preview_sensor_snapshot": _json_load(
                        row["preview_sensor_snapshot_json"],
                        {},
                    ),
                    "fixed_delta_seconds": row["fixed_delta_seconds"],
                    "sensor_warmup_seconds": row["sensor_warmup_seconds"],
                    "timebase": row["timebase"],
                    "hil_clock_mode": row["hil_clock_mode"],
                    "output_config_summary": _json_load(row["output_config_summary_json"], {}),
                    "report_config_summary": _json_load(row["report_config_summary_json"], {}),
                    "created_at": row["created_at"],
                }
            )
            for row in rows
        ]
