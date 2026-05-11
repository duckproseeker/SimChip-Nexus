from __future__ import annotations

import pytest

from app.scenario.template_registry import (
    build_template_parameter_schema,
    normalize_template_params,
)


def test_build_template_parameter_schema_applies_overrides() -> None:
    schema = build_template_parameter_schema(
        "osc_follow_leading_vehicle",
        [
            {
                "name": "leadingSpeed",
                "parameter_type": "double",
                "default_value": "2.0",
            }
        ],
    )

    assert schema == [
        {
            "field": "leadingSpeed",
            "label": "前车目标速度",
            "description": "控制前车在剧本初段维持的目标速度。",
            "type": "number",
            "parameter_type": "double",
            "required": False,
            "default": 2.0,
            "min": 0.5,
            "max": 25.0,
            "step": 0.5,
            "unit": "m/s",
            "options": [],
        }
    ]


def test_build_template_parameter_schema_for_demo_template() -> None:
    schema = build_template_parameter_schema("town10_autonomous_demo", [])

    assert schema == [
        {
            "field": "targetSpeedMps",
            "label": "自车目标速度",
            "description": "演示模板下平台自动驾驶的目标巡航速度。",
            "type": "number",
            "parameter_type": "string",
            "required": False,
            "default": 8.0,
            "min": 2.0,
            "max": 16.0,
            "step": 0.5,
            "unit": "m/s",
            "options": [],
        }
    ]


def test_build_template_parameter_schema_for_added_tm_autopilot_template() -> None:
    schema = build_template_parameter_schema("town05_rainy_commute", [])

    assert schema == [
        {
            "field": "targetSpeedMps",
            "label": "自车目标速度",
            "description": "平台内置自动驾驶的目标巡航速度。",
            "type": "number",
            "parameter_type": "string",
            "required": False,
            "default": 6.5,
            "min": 2.0,
            "max": 16.0,
            "step": 0.5,
            "unit": "m/s",
            "options": [],
        }
    ]


def test_normalize_template_params_uses_defaults_and_rejects_unknown_fields() -> None:
    schema = build_template_parameter_schema(
        "osc_follow_leading_vehicle",
        [
            {
                "name": "leadingSpeed",
                "parameter_type": "double",
                "default_value": "2.0",
            }
        ],
    )

    assert normalize_template_params(schema, None) == {"leadingSpeed": 2.0}
    assert normalize_template_params(schema, {"leadingSpeed": 4.5}) == {
        "leadingSpeed": 4.5
    }

    with pytest.raises(ValueError, match="未知模板参数"):
        normalize_template_params(schema, {"unknown": 1})
