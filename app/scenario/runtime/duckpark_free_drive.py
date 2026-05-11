from __future__ import annotations

import time

import py_trees
from srunner.scenariomanager.scenarioatomics.atomic_behaviors import ChangeAutoPilot
from srunner.scenariomanager.scenarioatomics.atomic_criteria import CollisionTest
from srunner.scenarios.basic_scenario import BasicScenario


class WallClockTimeout(py_trees.behaviour.Behaviour):
    def __init__(self, duration_seconds: float, name: str = "WallClockTimeout"):
        super().__init__(name)
        self._duration_seconds = max(0.0, float(duration_seconds))
        self._started_at = 0.0

    def initialise(self):
        self._started_at = time.monotonic()
        super().initialise()

    def update(self):
        if time.monotonic() - self._started_at >= self._duration_seconds:
            return py_trees.common.Status.SUCCESS
        return py_trees.common.Status.RUNNING


class DuckparkFreeDrive(BasicScenario):
    """Free-drive template with the platform autopilot attached to the hero vehicle."""

    def __init__(
        self,
        world,
        ego_vehicles,
        config,
        randomize: bool = False,
        debug_mode: bool = False,
        criteria_enable: bool = True,
        timeout: float = 100000.0,
    ):
        _ = randomize
        params = config.other_parameters.get("duckpark_free_drive", {})
        self.timeout = float(params.get("timeout_seconds") or timeout or 120.0)
        target_speed_mps = float(params.get("target_speed_mps") or 10.0)
        self._autopilot_parameters = {
            # ScenarioRunner expects km/h here and internally derives the TM speed delta
            # from the vehicle's live road speed limit.
            "max_speed": target_speed_mps * 3.6,
            "distance_between_vehicles": 3.0,
            "auto_lane_change": True,
            "ignore_vehicles_percentage": 0.0,
        }
        super().__init__(
            "DuckparkFreeDrive",
            ego_vehicles,
            config,
            world,
            debug_mode,
            criteria_enable=criteria_enable,
        )

    def _setup_scenario_trigger(self, config):
        _ = config
        return None

    def _create_behavior(self):
        sequence = py_trees.composites.Sequence("DuckparkFreeDrive")
        if self.ego_vehicles:
            sequence.add_child(
                ChangeAutoPilot(
                    self.ego_vehicles[0],
                    activate=True,
                    parameters=dict(self._autopilot_parameters),
                )
            )
        sequence.add_child(WallClockTimeout(self.timeout))
        return sequence

    def _create_test_criteria(self):
        return [CollisionTest(ego_vehicle) for ego_vehicle in self.ego_vehicles]

    def __del__(self):
        self.remove_all_actors()
