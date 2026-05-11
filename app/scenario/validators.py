from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from app.scenario.descriptor import ScenarioDescriptor


def validate_descriptor(payload: dict[str, Any]) -> ScenarioDescriptor:
    return ScenarioDescriptor.model_validate(payload)


def load_descriptor_from_yaml(path: Path) -> ScenarioDescriptor:
    with path.open("r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle)
    if not isinstance(payload, dict):
        raise ValueError("Scenario descriptor YAML must parse to a mapping")
    return validate_descriptor(payload)
