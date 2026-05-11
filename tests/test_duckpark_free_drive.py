from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace


class _FakeSequence:
    def __init__(self, name: str) -> None:
        self.name = name
        self.children: list[object] = []

    def add_child(self, child: object) -> None:
        self.children.append(child)


class _FakeBehavior:
    def __init__(self, name: str = "Behavior") -> None:
        self.name = name

    def initialise(self) -> None:
        return None


class _FakeChangeAutoPilot:
    def __init__(self, actor, activate, parameters=None, name="ChangeAutoPilot") -> None:
        self.actor = actor
        self.activate = activate
        self.parameters = parameters
        self.name = name


class _FakeCollisionTest:
    def __init__(self, ego_vehicle) -> None:
        self.ego_vehicle = ego_vehicle


class _FakeBasicScenario:
    def __init__(
        self,
        name,
        ego_vehicles,
        config,
        world,
        debug_mode,
        criteria_enable=True,
    ) -> None:
        self.name = name
        self.ego_vehicles = ego_vehicles
        self.config = config
        self.world = world
        self.debug_mode = debug_mode
        self.criteria_enable = criteria_enable

    def remove_all_actors(self) -> None:
        return None


def _load_module_with_fakes(module_path: Path):
    fake_py_trees = ModuleType("py_trees")
    fake_py_trees.behaviour = SimpleNamespace(Behaviour=_FakeBehavior)
    fake_py_trees.common = SimpleNamespace(
        Status=SimpleNamespace(SUCCESS="SUCCESS", RUNNING="RUNNING")
    )
    fake_py_trees.composites = SimpleNamespace(Sequence=_FakeSequence)

    fake_atomic_behaviors = ModuleType(
        "srunner.scenariomanager.scenarioatomics.atomic_behaviors"
    )
    fake_atomic_behaviors.ChangeAutoPilot = _FakeChangeAutoPilot

    fake_atomic_criteria = ModuleType(
        "srunner.scenariomanager.scenarioatomics.atomic_criteria"
    )
    fake_atomic_criteria.CollisionTest = _FakeCollisionTest

    fake_basic_scenario = ModuleType("srunner.scenarios.basic_scenario")
    fake_basic_scenario.BasicScenario = _FakeBasicScenario

    sys.modules["py_trees"] = fake_py_trees
    sys.modules[
        "srunner.scenariomanager.scenarioatomics.atomic_behaviors"
    ] = fake_atomic_behaviors
    sys.modules[
        "srunner.scenariomanager.scenarioatomics.atomic_criteria"
    ] = fake_atomic_criteria
    sys.modules["srunner.scenarios.basic_scenario"] = fake_basic_scenario

    spec = importlib.util.spec_from_file_location("test_duckpark_free_drive_runtime", module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_duckpark_free_drive_uses_tm_autopilot() -> None:
    module_path = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "scenario"
        / "runtime"
        / "duckpark_free_drive.py"
    )
    module = _load_module_with_fakes(module_path)

    hero_vehicle = object()
    config = SimpleNamespace(
        other_parameters={
            "duckpark_free_drive": {
                "target_speed_mps": "8.0",
                "traffic_manager_port": "8010",
                "controller_module": "unused",
            }
        }
    )

    scenario = module.DuckparkFreeDrive(
        world=object(),
        ego_vehicles=[hero_vehicle],
        config=config,
    )

    behavior = scenario._create_behavior()

    assert isinstance(behavior, _FakeSequence)
    assert len(behavior.children) == 2

    autopilot = behavior.children[0]
    assert isinstance(autopilot, _FakeChangeAutoPilot)
    assert autopilot.actor is hero_vehicle
    assert autopilot.activate is True
    assert autopilot.parameters == {
        "max_speed": 28.8,
        "distance_between_vehicles": 3.0,
        "auto_lane_change": True,
        "ignore_vehicles_percentage": 0.0,
    }
