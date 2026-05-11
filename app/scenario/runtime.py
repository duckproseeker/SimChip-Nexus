from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.scenario.descriptor import ScenarioDescriptor


@dataclass
class ScenarioRuntimeContext:
    run_id: str
    descriptor: ScenarioDescriptor
    carla_client: Any
    ego_vehicle: Any
    npc_vehicles: list[Any] = field(default_factory=list)
    state: dict[str, Any] = field(default_factory=dict)
