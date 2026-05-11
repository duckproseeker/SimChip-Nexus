from __future__ import annotations

import re
from typing import Any

ScenarioTemplateScalar = str | int | float | bool

_INTEGER_PARAMETER_TYPES = {
    "int",
    "integer",
    "long",
    "short",
    "unsignedint",
    "unsignedinteger",
    "unsignedlong",
    "unsignedshort",
}
_FLOAT_PARAMETER_TYPES = {"double", "float"}
_BOOLEAN_PARAMETER_TYPES = {"bool", "boolean"}

_SCENARIO_TEMPLATE_OVERRIDES: dict[str, dict[str, Any]] = {
    "town10_autonomous_demo": {
        "category": "demo",
        "parameters": {
            "targetSpeedMps": {
                "label": "自车目标速度",
                "description": "演示模板下平台自动驾驶的目标巡航速度。",
                "type": "number",
                "default": 8.0,
                "min": 2.0,
                "max": 16.0,
                "step": 0.5,
                "unit": "m/s",
            }
        },
    },
    "town01_urban_loop": {
        "category": "urban",
        "parameters": {
            "targetSpeedMps": {
                "label": "自车目标速度",
                "description": "平台内置自动驾驶的目标巡航速度。",
                "type": "number",
                "default": 8.0,
                "min": 2.0,
                "max": 16.0,
                "step": 0.5,
                "unit": "m/s",
            }
        },
    },
    "town02_suburb_cruise": {
        "category": "suburb",
        "parameters": {
            "targetSpeedMps": {
                "label": "自车目标速度",
                "description": "平台内置自动驾驶的目标巡航速度。",
                "type": "number",
                "default": 8.5,
                "min": 2.0,
                "max": 16.0,
                "step": 0.5,
                "unit": "m/s",
            }
        },
    },
    "town03_intersection_sweep": {
        "category": "intersection",
        "parameters": {
            "targetSpeedMps": {
                "label": "自车目标速度",
                "description": "平台内置自动驾驶的目标巡航速度。",
                "type": "number",
                "default": 7.5,
                "min": 2.0,
                "max": 16.0,
                "step": 0.5,
                "unit": "m/s",
            }
        },
    },
    "town03_rush_hour": {
        "category": "dense_traffic",
        "parameters": {
            "targetSpeedMps": {
                "label": "自车目标速度",
                "description": "平台内置自动驾驶的目标巡航速度。",
                "type": "number",
                "default": 6.5,
                "min": 2.0,
                "max": 16.0,
                "step": 0.5,
                "unit": "m/s",
            }
        },
    },
    "town04_night_cruise": {
        "category": "night",
        "parameters": {
            "targetSpeedMps": {
                "label": "自车目标速度",
                "description": "平台内置自动驾驶的目标巡航速度。",
                "type": "number",
                "default": 7.0,
                "min": 2.0,
                "max": 16.0,
                "step": 0.5,
                "unit": "m/s",
            }
        },
    },
    "town05_rainy_commute": {
        "category": "weather",
        "parameters": {
            "targetSpeedMps": {
                "label": "自车目标速度",
                "description": "平台内置自动驾驶的目标巡航速度。",
                "type": "number",
                "default": 6.5,
                "min": 2.0,
                "max": 16.0,
                "step": 0.5,
                "unit": "m/s",
            }
        },
    },
    "town06_long_route": {
        "category": "long_route",
        "parameters": {
            "targetSpeedMps": {
                "label": "自车目标速度",
                "description": "平台内置自动驾驶的目标巡航速度。",
                "type": "number",
                "default": 9.0,
                "min": 2.0,
                "max": 18.0,
                "step": 0.5,
                "unit": "m/s",
            }
        },
    },
    "town07_hillside_patrol": {
        "category": "maneuver",
        "parameters": {
            "targetSpeedMps": {
                "label": "自车目标速度",
                "description": "平台内置自动驾驶的目标巡航速度。",
                "type": "number",
                "default": 7.0,
                "min": 2.0,
                "max": 16.0,
                "step": 0.5,
                "unit": "m/s",
            }
        },
    },
    "town10_dense_flow": {
        "category": "dense_traffic",
        "parameters": {
            "targetSpeedMps": {
                "label": "自车目标速度",
                "description": "平台内置自动驾驶的目标巡航速度。",
                "type": "number",
                "default": 7.5,
                "min": 2.0,
                "max": 16.0,
                "step": 0.5,
                "unit": "m/s",
            }
        },
    },
    "free_drive_sensor_collection": {
        "category": "data_collection",
        "parameters": {
            "targetSpeedMps": {
                "label": "自车目标速度",
                "description": "平台内置自动驾驶的目标巡航速度。",
                "type": "number",
                "default": 10.0,
                "min": 2.0,
                "max": 18.0,
                "step": 0.5,
                "unit": "m/s",
            }
        },
    },
    "osc_follow_leading_vehicle": {
        "category": "vehicle_following",
        "parameters": {
            "leadingSpeed": {
                "label": "前车目标速度",
                "description": "控制前车在剧本初段维持的目标速度。",
                "type": "number",
                "min": 0.5,
                "max": 25.0,
                "step": 0.5,
                "unit": "m/s",
            }
        },
    },
    "osc_lane_change_simple": {
        "category": "lane_change",
    },
    "osc_sync_arrival_intersection": {
        "category": "intersection",
    },
    "osc_intersection_collision_avoidance": {
        "category": "intersection",
    },
    "osc_pedestrian_crossing_front": {
        "category": "pedestrian",
    },
    "osc_cyclist_crossing": {
        "category": "cyclist",
    },
    "osc_slalom": {
        "category": "maneuver",
    },
    "osc_changing_weather": {
        "category": "weather",
    },
}


def get_template_category(scenario_id: str) -> str:
    override = _SCENARIO_TEMPLATE_OVERRIDES.get(scenario_id, {})
    category = str(override.get("category") or "").strip()
    return category or "general"


def build_template_parameter_schema(
    scenario_id: str,
    parameter_declarations: list[dict[str, str]],
) -> list[dict[str, Any]]:
    override = _SCENARIO_TEMPLATE_OVERRIDES.get(scenario_id, {})
    parameter_overrides = override.get("parameters", {})
    items: list[dict[str, Any]] = []
    seen_fields: set[str] = set()

    for declaration in parameter_declarations:
        field = str(declaration.get("name") or "").strip()
        if not field:
            continue
        seen_fields.add(field)
        items.append(
            _build_parameter_schema_item(
                field=field,
                declaration=declaration,
                override=parameter_overrides.get(field, {}),
            )
        )

    for field, parameter_override in parameter_overrides.items():
        if field in seen_fields:
            continue
        items.append(
            _build_parameter_schema_item(
                field=field,
                declaration=None,
                override=parameter_override,
            )
        )

    return items


def normalize_template_params(
    parameter_schema: list[dict[str, Any]],
    raw_params: dict[str, Any] | None,
) -> dict[str, ScenarioTemplateScalar]:
    requested_params = raw_params if isinstance(raw_params, dict) else {}
    schema_by_field = {
        str(item.get("field") or "").strip(): item
        for item in parameter_schema
        if str(item.get("field") or "").strip()
    }
    unknown_fields = sorted(
        field
        for field in requested_params
        if str(field).strip() and str(field).strip() not in schema_by_field
    )
    if unknown_fields:
        raise ValueError(
            "未知模板参数: " + ", ".join(unknown_fields)
        )

    normalized: dict[str, ScenarioTemplateScalar] = {}
    for field, item in schema_by_field.items():
        has_explicit_value = field in requested_params
        if has_explicit_value:
            candidate = requested_params[field]
        else:
            candidate = item.get("default")

        if candidate is None:
            if bool(item.get("required")):
                raise ValueError(f"缺少必填模板参数: {field}")
            continue

        normalized[field] = _coerce_parameter_value(item, candidate)
    return normalized


def format_template_param_value(value: ScenarioTemplateScalar) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return format(value, "g")
    return str(value)


def _build_parameter_schema_item(
    *,
    field: str,
    declaration: dict[str, str] | None,
    override: dict[str, Any] | None,
) -> dict[str, Any]:
    override = override or {}
    parameter_type = str(
        override.get("parameter_type")
        or (declaration or {}).get("parameter_type")
        or "string"
    ).strip()
    item_type = _resolve_item_type(parameter_type, override)
    default_value = override.get("default")
    if default_value is None:
        default_value = _parse_default_value(
            raw_value=str((declaration or {}).get("default_value") or ""),
            parameter_type=parameter_type,
            item_type=item_type,
        )
    else:
        default_value = _coerce_parameter_value(
            {
                "field": field,
                "type": item_type,
                "parameter_type": parameter_type,
                "min": override.get("min"),
                "max": override.get("max"),
                "options": override.get("options", []),
            },
            default_value,
        )

    return {
        "field": field,
        "label": str(override.get("label") or _humanize_field(field)).strip(),
        "description": str(override.get("description") or "").strip() or None,
        "type": item_type,
        "parameter_type": parameter_type or None,
        "required": bool(override.get("required", False)),
        "default": default_value,
        "min": override.get("min"),
        "max": override.get("max"),
        "step": override.get("step"),
        "unit": str(override.get("unit") or "").strip() or None,
        "options": [
            str(option).strip()
            for option in override.get("options", [])
            if str(option).strip()
        ],
    }


def _resolve_item_type(parameter_type: str, override: dict[str, Any]) -> str:
    normalized_parameter_type = parameter_type.lower()
    declared_type = str(override.get("type") or "").strip().lower()
    if declared_type in {"number", "boolean", "text", "enum"}:
        return declared_type
    if override.get("options"):
        return "enum"
    if (
        normalized_parameter_type in _INTEGER_PARAMETER_TYPES
        or normalized_parameter_type in _FLOAT_PARAMETER_TYPES
    ):
        return "number"
    if normalized_parameter_type in _BOOLEAN_PARAMETER_TYPES:
        return "boolean"
    return "text"


def _parse_default_value(
    *,
    raw_value: str,
    parameter_type: str,
    item_type: str,
) -> ScenarioTemplateScalar | None:
    normalized_parameter_type = parameter_type.lower()
    value = raw_value.strip()
    if not value:
        return None
    if item_type == "boolean":
        lowered = value.lower()
        if lowered in {"true", "1", "yes", "on"}:
            return True
        if lowered in {"false", "0", "no", "off"}:
            return False
        return None
    if item_type == "number":
        try:
            if normalized_parameter_type in _INTEGER_PARAMETER_TYPES:
                return int(float(value))
            return float(value)
        except ValueError:
            return None
    return value


def _coerce_parameter_value(
    item: dict[str, Any],
    raw_value: Any,
) -> ScenarioTemplateScalar:
    item_type = str(item.get("type") or "text").strip().lower()
    field = str(item.get("field") or "template_param").strip()

    if item_type == "boolean":
        value = _coerce_boolean_value(field, raw_value)
    elif item_type == "number":
        value = _coerce_numeric_value(item, raw_value)
    else:
        value = str(raw_value).strip()
        if not value:
            raise ValueError(f"模板参数 {field} 不能为空")

    options = [
        str(option).strip()
        for option in item.get("options", [])
        if str(option).strip()
    ]
    if options and str(value) not in options:
        raise ValueError(
            f"模板参数 {field} 必须是 {options} 中的一个"
        )
    return value


def _coerce_boolean_value(field: str, raw_value: Any) -> bool:
    if isinstance(raw_value, bool):
        return raw_value
    if isinstance(raw_value, int | float) and raw_value in {0, 1}:
        return bool(raw_value)
    lowered = str(raw_value).strip().lower()
    if lowered in {"true", "1", "yes", "on"}:
        return True
    if lowered in {"false", "0", "no", "off"}:
        return False
    raise ValueError(f"模板参数 {field} 需要布尔值")


def _coerce_numeric_value(
    item: dict[str, Any],
    raw_value: Any,
) -> int | float:
    field = str(item.get("field") or "template_param").strip()
    parameter_type = str(item.get("parameter_type") or "").strip().lower()
    try:
        numeric_value = float(raw_value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"模板参数 {field} 需要数值") from exc

    minimum = item.get("min")
    if minimum is not None and numeric_value < float(minimum):
        raise ValueError(f"模板参数 {field} 不能小于 {minimum}")

    maximum = item.get("max")
    if maximum is not None and numeric_value > float(maximum):
        raise ValueError(f"模板参数 {field} 不能大于 {maximum}")

    if parameter_type in _INTEGER_PARAMETER_TYPES:
        if not numeric_value.is_integer():
            raise ValueError(f"模板参数 {field} 需要整数值")
        return int(numeric_value)
    return numeric_value


def _humanize_field(field: str) -> str:
    spaced = re.sub(r"(?<!^)([A-Z])", r" \1", field).replace("_", " ")
    normalized = " ".join(spaced.split()).strip()
    return normalized or field
