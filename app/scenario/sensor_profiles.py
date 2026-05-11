from __future__ import annotations

import copy
import re
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError as PydanticValidationError

from app.scenario.descriptor import SensorSpec

PROFILE_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")


def _read_text_with_fallback(path: Path) -> str:
    raw = path.read_bytes()
    for encoding in ("utf-8", "utf-8-sig", "gb18030"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise UnicodeDecodeError(
        "utf-8",
        raw,
        0,
        1,
        f"Unable to decode sensor profile {path}",
    )


def load_sensor_profiles(root: Path) -> list[dict[str, Any]]:
    profiles: list[dict[str, Any]] = []

    if not root.exists():
        return profiles

    for path in sorted(root.glob("*.yaml")):
        if path.name.startswith("._"):
            continue
        raw_text = _read_text_with_fallback(path)
        payload = yaml.safe_load(raw_text) or {}

        if not isinstance(payload, dict):
            raise ValueError(f"Invalid sensor profile YAML: {path}")

        profile_name = str(payload.get("profile_name", path.stem)).strip()
        display_name = str(payload.get("display_name", profile_name)).strip()
        description = str(payload.get("description", "")).strip()
        sensors = payload.get("sensors", [])
        metadata = payload.get("metadata", {})

        if not isinstance(sensors, list):
            raise ValueError(f"Sensor profile sensors must be a list: {path}")
        if not isinstance(metadata, dict):
            raise ValueError(f"Sensor profile metadata must be a mapping: {path}")

        profiles.append(
            {
                "profile_name": profile_name,
                "display_name": display_name,
                "description": description,
                "vehicle_model": str(metadata.get("vehicle_model") or "").strip() or None,
                "sensors": sensors,
                "raw_yaml": raw_text,
                "source_path": str(path),
                "metadata": metadata,
            }
        )

    return profiles


def get_sensor_profile(root: Path, profile_name: str) -> dict[str, Any] | None:
    normalized = str(profile_name).strip()
    if not normalized:
        return None

    for item in load_sensor_profiles(root):
        if str(item.get("profile_name") or "").strip() == normalized:
            return copy.deepcopy(item)
    return None


def build_sensor_config_from_profile(
    root: Path, profile_name: str
) -> dict[str, Any] | None:
    profile = get_sensor_profile(root, profile_name)
    if profile is None:
        return None

    return {
        "enabled": True,
        "auto_start": False,
        "profile_name": profile["profile_name"],
        "config_yaml_path": profile["source_path"],
        "sensors": copy.deepcopy(profile["sensors"]),
    }


def _normalize_profile_name(profile_name: str) -> str:
    normalized = str(profile_name).strip()
    if not normalized:
        raise ValueError("profile_name must not be empty")
    if not PROFILE_NAME_RE.fullmatch(normalized):
        raise ValueError(
            "profile_name 仅允许字母、数字、下划线和连字符，且必须以字母或数字开头"
        )
    return normalized


def _normalize_display_name(display_name: str, fallback_profile_name: str) -> str:
    normalized = str(display_name).strip()
    return normalized or fallback_profile_name


def _normalize_description(description: str | None) -> str:
    return str(description or "").strip()


def _normalize_metadata(metadata: dict[str, Any] | None) -> dict[str, Any]:
    if metadata is None:
        return {}
    if not isinstance(metadata, dict):
        raise ValueError("metadata must be a mapping")
    return copy.deepcopy(metadata)


def _normalize_vehicle_model(vehicle_model: str | None) -> str | None:
    normalized = str(vehicle_model or "").strip()
    return normalized or None


def _normalize_sensor_specs(sensors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not isinstance(sensors, list) or not sensors:
        raise ValueError("sensors must be a non-empty list")

    normalized_sensors: list[dict[str, Any]] = []
    for index, raw_sensor in enumerate(sensors):
        if not isinstance(raw_sensor, dict):
            raise ValueError(f"sensors[{index}] must be a mapping")
        try:
            sensor = SensorSpec.model_validate(raw_sensor)
        except PydanticValidationError as exc:
            raise ValueError(f"sensors[{index}] invalid: {exc}") from exc
        normalized_sensors.append(sensor.model_dump(mode="json", exclude_none=True))
    return normalized_sensors


def save_sensor_profile(
    root: Path,
    *,
    profile_name: str,
    display_name: str,
    description: str | None,
    sensors: list[dict[str, Any]],
    metadata: dict[str, Any] | None = None,
    vehicle_model: str | None = None,
) -> dict[str, Any]:
    normalized_profile_name = _normalize_profile_name(profile_name)
    normalized_display_name = _normalize_display_name(
        display_name, normalized_profile_name
    )
    normalized_description = _normalize_description(description)
    normalized_metadata = _normalize_metadata(metadata)
    normalized_vehicle_model = _normalize_vehicle_model(vehicle_model)
    normalized_sensors = _normalize_sensor_specs(sensors)

    if normalized_vehicle_model is not None:
        normalized_metadata["vehicle_model"] = normalized_vehicle_model
    else:
        normalized_metadata.pop("vehicle_model", None)

    payload = {
        "profile_name": normalized_profile_name,
        "display_name": normalized_display_name,
        "description": normalized_description,
        "metadata": normalized_metadata,
        "sensors": normalized_sensors,
    }

    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{normalized_profile_name}.yaml"
    path.write_text(
        yaml.safe_dump(
            payload,
            allow_unicode=True,
            sort_keys=False,
            default_flow_style=False,
        ),
        encoding="utf-8",
    )

    profile = get_sensor_profile(root, normalized_profile_name)
    if profile is None:
        raise ValueError(f"保存传感器模板失败: {normalized_profile_name}")
    return profile
