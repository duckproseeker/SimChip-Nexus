from __future__ import annotations

import random
import time
from typing import Any

from agents.navigation.basic_agent import BasicAgent
from srunner.scenariomanager.actorcontrols.basic_control import BasicControl


class DuckparkAutopilot(BasicControl):
    """Platform default hero controller backed by CARLA's BasicAgent."""

    def __init__(self, actor: Any, args: dict[str, Any] | None = None):
        super().__init__(actor)
        raw_args = args or {}
        self._target_speed_mps = self._coerce_float(
            raw_args.get("target_speed_mps"),
            fallback=10.0,
        )
        self._roaming_seed = self._coerce_int(raw_args.get("roaming_seed"), fallback=0)
        self._rng = random.Random(self._roaming_seed)
        self._agent = BasicAgent(
            actor,
            target_speed=self._target_speed_mps * 3.6,
            opt_dict={
                "ignore_stop_signs": False,
                "ignore_traffic_lights": False,
                "ignore_vehicles": False,
            },
        )
        self._destination_initialized = False
        self._last_progress_location: Any | None = None
        self._last_progress_at = time.monotonic()
        self._last_replan_at = 0.0

    def update_target_speed(self, speed: float) -> None:
        super().update_target_speed(speed)
        self._target_speed_mps = self._coerce_float(speed, fallback=self._target_speed_mps)
        self._agent.set_target_speed(self._target_speed_mps * 3.6)

    def reset(self) -> None:
        if self._actor is None or not getattr(self._actor, "is_alive", False):
            return
        try:
            control = self._actor.get_control()
            control.throttle = 0.0
            control.brake = 1.0
            control.hand_brake = False
            self._actor.apply_control(control)
        except RuntimeError:
            return

    def run_step(self) -> None:
        if self._actor is None or not getattr(self._actor, "is_alive", False):
            return

        now = time.monotonic()
        speed_mps = self._current_speed_mps()
        current_location = self._actor.get_location()
        if (
            self._last_progress_location is None
            or current_location.distance(self._last_progress_location) >= 3.0
            or speed_mps >= 1.0
        ):
            self._last_progress_location = current_location
            self._last_progress_at = now

        if (
            not self._destination_initialized
            or self._agent.done()
            or self._is_stuck(now, speed_mps)
        ):
            self._agent.set_destination(self._pick_roaming_destination())
            self._destination_initialized = True
            self._last_replan_at = now
            self._last_progress_location = current_location
            self._last_progress_at = now

        control = self._agent.run_step()
        control.manual_gear_shift = False
        self._actor.apply_control(control)

    def _pick_roaming_destination(self) -> Any:
        world = self._actor.get_world()
        spawn_points = list(world.get_map().get_spawn_points())
        current_location = self._actor.get_location()
        if spawn_points:
            ordered = sorted(
                spawn_points,
                key=lambda transform: current_location.distance(transform.location),
                reverse=True,
            )
            candidate_count = max(1, min(len(ordered), 12))
            return self._rng.choice(ordered[:candidate_count]).location
        return self._pick_forward_destination()

    def _pick_forward_destination(self) -> Any:
        world = self._actor.get_world()
        current_waypoint = world.get_map().get_waypoint(
            self._actor.get_location(),
            project_to_road=True,
        )
        if current_waypoint is None:
            return self._actor.get_location()

        waypoint = current_waypoint
        for _ in range(30):
            next_waypoints = waypoint.next(2.0)
            if not next_waypoints:
                break
            waypoint = next_waypoints[0]
        return waypoint.transform.location

    def _current_speed_mps(self) -> float:
        velocity = self._actor.get_velocity()
        return (
            float(velocity.x) ** 2 + float(velocity.y) ** 2 + float(velocity.z) ** 2
        ) ** 0.5

    def _is_stuck(self, now: float, speed_mps: float) -> bool:
        if speed_mps >= 0.5:
            return False
        if now - self._last_progress_at < 4.0:
            return False
        if now - self._last_replan_at < 2.0:
            return False
        return True

    @staticmethod
    def _coerce_float(value: Any, *, fallback: float) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return fallback

    @staticmethod
    def _coerce_int(value: Any, *, fallback: int) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return fallback
