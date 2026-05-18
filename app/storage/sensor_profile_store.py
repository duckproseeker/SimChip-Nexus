from __future__ import annotations

import copy
import hashlib
import json
import re
import sqlite3
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from pydantic import ValidationError as PydanticValidationError

from app.core.errors import ConflictError, NotFoundError, ValidationError
from app.core.models import SensorProfileRecord
from app.scenario.descriptor import SensorSpec
from app.scenario.sensor_profiles import load_sensor_profiles
from app.utils.file_utils import ensure_dir
from app.utils.time_utils import now_utc

PROFILE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")


def _json_dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _json_load(value: str | None, default: Any) -> Any:
    if value is None or value == "":
        return copy.deepcopy(default)
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return copy.deepcopy(default)


def _iso(value: Any) -> str:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _normalize_required_text(value: str, *, field_name: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise ValidationError(f"{field_name} must not be empty")
    return normalized


def _normalize_profile_id(value: str) -> str:
    normalized = _normalize_required_text(value, field_name="sensor_profile_id")
    if not PROFILE_ID_RE.fullmatch(normalized):
        raise ValidationError(
            "sensor_profile_id only allows letters, numbers, underscores and dashes, "
            "and must start with a letter or number"
        )
    return normalized


def normalize_sensor_specs(sensors: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for index, raw_sensor in enumerate(sensors):
        if not isinstance(raw_sensor, dict):
            raise ValidationError(f"sensors[{index}] must be an object")
        try:
            sensor = SensorSpec.model_validate(raw_sensor)
        except PydanticValidationError as exc:
            raise ValidationError(f"sensors[{index}] invalid: {exc}") from exc
        normalized.append(sensor.model_dump(mode="json", exclude_none=True))
    if not normalized:
        raise ValidationError("sensors must contain at least one sensor")
    return normalized


def build_sensor_profile_hash(
    *,
    sensors: list[dict[str, Any]],
    fixed_delta_seconds: float,
    expected_fps: float,
    output_mode: str,
    hil_output_mode: str,
) -> str:
    payload = {
        "version": 1,
        "sensors": sensors,
        "fixed_delta_seconds": fixed_delta_seconds,
        "expected_fps": expected_fps,
        "output_mode": output_mode,
        "hil_output_mode": hil_output_mode,
    }
    return hashlib.sha256(_json_dump(payload).encode("utf-8")).hexdigest()


def normalize_sensor_profile_payload(
    *,
    sensor_profile_id: str,
    name: str,
    sensors: Iterable[dict[str, Any]],
    fixed_delta_seconds: float | None = None,
    expected_fps: float | None = None,
    output_mode: str | None = None,
    hil_output_mode: str | None = None,
    description: str | None = None,
    vehicle_model: str | None = None,
    metadata: dict[str, Any] | None = None,
    source_path: str | None = None,
    raw_yaml: str | None = None,
    created_at: Any | None = None,
    updated_at: Any | None = None,
) -> SensorProfileRecord:
    normalized_id = _normalize_profile_id(sensor_profile_id)
    normalized_name = _normalize_required_text(name, field_name="name")
    normalized_sensors = normalize_sensor_specs(sensors)
    normalized_fixed_delta = float(fixed_delta_seconds if fixed_delta_seconds is not None else 0.05)
    if normalized_fixed_delta <= 0 or normalized_fixed_delta > 0.2:
        raise ValidationError("fixed_delta_seconds must be > 0 and <= 0.2")
    normalized_expected_fps = float(
        expected_fps if expected_fps is not None else round(1.0 / normalized_fixed_delta, 6)
    )
    if normalized_expected_fps <= 0 or normalized_expected_fps > 240:
        raise ValidationError("expected_fps must be > 0 and <= 240")
    normalized_output_mode = _normalize_required_text(
        output_mode or "carla_live", field_name="output_mode"
    )
    normalized_hil_output_mode = _normalize_required_text(
        hil_output_mode or "camera_open_loop", field_name="hil_output_mode"
    )
    normalized_metadata = copy.deepcopy(metadata or {})
    if not isinstance(normalized_metadata, dict):
        raise ValidationError("metadata must be an object")
    normalized_vehicle_model = str(vehicle_model or "").strip() or None
    if normalized_vehicle_model:
        normalized_metadata["vehicle_model"] = normalized_vehicle_model
    else:
        normalized_metadata.pop("vehicle_model", None)
    profile_hash = build_sensor_profile_hash(
        sensors=normalized_sensors,
        fixed_delta_seconds=normalized_fixed_delta,
        expected_fps=normalized_expected_fps,
        output_mode=normalized_output_mode,
        hil_output_mode=normalized_hil_output_mode,
    )
    timestamp = now_utc()
    return SensorProfileRecord(
        sensor_profile_id=normalized_id,
        name=normalized_name,
        sensors=normalized_sensors,
        profile_hash=profile_hash,
        fixed_delta_seconds=normalized_fixed_delta,
        expected_fps=normalized_expected_fps,
        output_mode=normalized_output_mode,
        hil_output_mode=normalized_hil_output_mode,
        description=str(description or "").strip(),
        vehicle_model=normalized_vehicle_model,
        metadata=normalized_metadata,
        source_path=str(source_path or "").strip() or None,
        raw_yaml=str(raw_yaml or ""),
        created_at=created_at or timestamp,
        updated_at=updated_at or timestamp,
    )


class SensorProfileStore:
    def __init__(self, root: Path, *, legacy_yaml_root: Path | None = None) -> None:
        self._root = ensure_dir(root)
        self._db_path = self._root / "scenario_recordings.sqlite3"
        self._legacy_yaml_root = legacy_yaml_root
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
                CREATE TABLE IF NOT EXISTS sensor_profiles (
                    sensor_profile_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    sensors_json TEXT NOT NULL,
                    profile_hash TEXT NOT NULL,
                    fixed_delta_seconds REAL NOT NULL,
                    expected_fps REAL NOT NULL,
                    output_mode TEXT NOT NULL,
                    hil_output_mode TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    vehicle_model TEXT,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    source_path TEXT,
                    raw_yaml TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_sensor_profiles_hash
                ON sensor_profiles(profile_hash)
                """
            )

    @staticmethod
    def _record_from_row(row: sqlite3.Row) -> SensorProfileRecord:
        return SensorProfileRecord.model_validate(
            {
                "sensor_profile_id": row["sensor_profile_id"],
                "name": row["name"],
                "sensors": _json_load(row["sensors_json"], []),
                "profile_hash": row["profile_hash"],
                "fixed_delta_seconds": row["fixed_delta_seconds"],
                "expected_fps": row["expected_fps"],
                "output_mode": row["output_mode"],
                "hil_output_mode": row["hil_output_mode"],
                "description": row["description"],
                "vehicle_model": row["vehicle_model"],
                "metadata": _json_load(row["metadata_json"], {}),
                "source_path": row["source_path"],
                "raw_yaml": row["raw_yaml"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }
        )

    def import_legacy_yaml_profiles(self) -> None:
        if self._legacy_yaml_root is None:
            return
        try:
            legacy_profiles = load_sensor_profiles(self._legacy_yaml_root)
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc

        with self._connect() as connection:
            existing_ids = {
                str(row["sensor_profile_id"])
                for row in connection.execute(
                    "SELECT sensor_profile_id FROM sensor_profiles"
                ).fetchall()
            }

        for profile in legacy_profiles:
            profile_id = str(profile.get("profile_name") or "").strip()
            if not profile_id or profile_id in existing_ids:
                continue
            metadata = profile.get("metadata") if isinstance(profile.get("metadata"), dict) else {}
            fixed_delta = _metadata_float(metadata, "fixed_delta_seconds", 0.05)
            expected_fps = _metadata_float(metadata, "expected_fps", 1.0 / fixed_delta)
            record = normalize_sensor_profile_payload(
                sensor_profile_id=profile_id,
                name=str(profile.get("display_name") or profile_id),
                description=str(profile.get("description") or ""),
                vehicle_model=profile.get("vehicle_model"),
                metadata=metadata,
                sensors=profile.get("sensors") or [],
                fixed_delta_seconds=fixed_delta,
                expected_fps=expected_fps,
                output_mode=str(metadata.get("output_mode") or "carla_live"),
                hil_output_mode=str(metadata.get("hil_output_mode") or "camera_open_loop"),
                source_path=profile.get("source_path"),
                raw_yaml=str(profile.get("raw_yaml") or ""),
            )
            self.create(record)
            existing_ids.add(record.sensor_profile_id)

    def list(self) -> list[SensorProfileRecord]:
        self.import_legacy_yaml_profiles()
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM sensor_profiles ORDER BY updated_at DESC, sensor_profile_id ASC"
            ).fetchall()
        return [self._record_from_row(row) for row in rows]

    def get(self, sensor_profile_id: str) -> SensorProfileRecord:
        self.import_legacy_yaml_profiles()
        normalized_id = str(sensor_profile_id or "").strip()
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM sensor_profiles WHERE sensor_profile_id = ?",
                (normalized_id,),
            ).fetchone()
        if row is None:
            raise NotFoundError(f"Sensor profile not found: {sensor_profile_id}")
        return self._record_from_row(row)

    def create(self, profile: SensorProfileRecord) -> SensorProfileRecord:
        with self._connect() as connection:
            try:
                connection.execute(
                    """
                    INSERT INTO sensor_profiles (
                        sensor_profile_id,
                        name,
                        sensors_json,
                        profile_hash,
                        fixed_delta_seconds,
                        expected_fps,
                        output_mode,
                        hil_output_mode,
                        description,
                        vehicle_model,
                        metadata_json,
                        source_path,
                        raw_yaml,
                        created_at,
                        updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    self._record_values(profile),
                )
            except sqlite3.IntegrityError as exc:
                raise ConflictError(
                    f"Sensor profile already exists: {profile.sensor_profile_id}"
                ) from exc
        return profile

    def upsert(self, profile: SensorProfileRecord) -> SensorProfileRecord:
        now = now_utc()
        with self._connect() as connection:
            row = connection.execute(
                "SELECT created_at FROM sensor_profiles WHERE sensor_profile_id = ?",
                (profile.sensor_profile_id,),
            ).fetchone()
            created_at = row["created_at"] if row is not None else profile.created_at
            updated = profile.model_copy(update={"created_at": created_at, "updated_at": now})
            connection.execute(
                """
                INSERT INTO sensor_profiles (
                    sensor_profile_id,
                    name,
                    sensors_json,
                    profile_hash,
                    fixed_delta_seconds,
                    expected_fps,
                    output_mode,
                    hil_output_mode,
                    description,
                    vehicle_model,
                    metadata_json,
                    source_path,
                    raw_yaml,
                    created_at,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(sensor_profile_id) DO UPDATE SET
                    name = excluded.name,
                    sensors_json = excluded.sensors_json,
                    profile_hash = excluded.profile_hash,
                    fixed_delta_seconds = excluded.fixed_delta_seconds,
                    expected_fps = excluded.expected_fps,
                    output_mode = excluded.output_mode,
                    hil_output_mode = excluded.hil_output_mode,
                    description = excluded.description,
                    vehicle_model = excluded.vehicle_model,
                    metadata_json = excluded.metadata_json,
                    source_path = excluded.source_path,
                    raw_yaml = excluded.raw_yaml,
                    updated_at = excluded.updated_at
                """,
                self._record_values(updated),
            )
        return self.get(profile.sensor_profile_id)

    def duplicate(
        self,
        source_sensor_profile_id: str,
        *,
        sensor_profile_id: str,
        name: str | None = None,
    ) -> SensorProfileRecord:
        source = self.get(source_sensor_profile_id)
        next_profile = normalize_sensor_profile_payload(
            sensor_profile_id=sensor_profile_id,
            name=name or f"{source.name} Copy",
            description=source.description,
            vehicle_model=source.vehicle_model,
            metadata=source.metadata,
            sensors=source.sensors,
            fixed_delta_seconds=source.fixed_delta_seconds,
            expected_fps=source.expected_fps,
            output_mode=source.output_mode,
            hil_output_mode=source.hil_output_mode,
            source_path=None,
            raw_yaml="",
        )
        return self.create(next_profile)

    @staticmethod
    def _record_values(profile: SensorProfileRecord) -> tuple[Any, ...]:
        return (
            profile.sensor_profile_id,
            profile.name,
            _json_dump(profile.sensors),
            profile.profile_hash,
            float(profile.fixed_delta_seconds),
            float(profile.expected_fps),
            profile.output_mode,
            profile.hil_output_mode,
            profile.description,
            profile.vehicle_model,
            _json_dump(profile.metadata),
            profile.source_path,
            profile.raw_yaml,
            _iso(profile.created_at),
            _iso(profile.updated_at),
        )


def _metadata_float(metadata: dict[str, Any], key: str, default: float) -> float:
    value = metadata.get(key)
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return float(default)
    return parsed if parsed > 0 else float(default)
