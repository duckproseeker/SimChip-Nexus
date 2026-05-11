from __future__ import annotations

import logging
import random
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.scenario.maps import choose_preferred_available_map, map_family_key, normalize_map_tail

logger = logging.getLogger(__name__)


@dataclass
class CarlaTickResult:
    frame: int
    sim_time: float


@dataclass
class EgoSpawnResult:
    actor: Any
    resolved_spawn_point: dict[str, float]
    source: str
    requested_spawn_point: dict[str, float]
    distance_to_requested_m: float | None = None
    fallback_index: int | None = None


@dataclass
class SpawnCandidate:
    transform: Any
    source: str
    distance_to_requested_m: float | None = None
    fallback_index: int | None = None


class CarlaClientError(RuntimeError):
    """CARLA client wrapper error."""


class CarlaClient:
    """Thin wrapper around CARLA Python API.

    The executor keeps exclusive world tick authority and uses this class only
    from the execution thread/process.
    """

    def __init__(
        self, host: str, port: int, timeout_seconds: float, traffic_manager_port: int
    ) -> None:
        self._host = host
        self._port = port
        self._timeout_seconds = timeout_seconds
        self._traffic_manager_port = traffic_manager_port

        self._carla: Any = None
        self._client: Any = None
        self._world: Any = None
        self._tm: Any = None
        self._tm_unavailable_reason: str | None = None
        self._original_sync_mode: bool | None = None
        self._original_fixed_delta: float | None = None
        self._spawned_actors: list[Any] = []
        self._tm_sync_enabled = False

    @property
    def spawned_actors(self) -> list[Any]:
        return self._spawned_actors

    def connect(self, *, connect_traffic_manager: bool = True) -> None:
        try:
            import carla  # type: ignore
        except ImportError as exc:
            raise CarlaClientError("carla Python API not found in executor environment") from exc

        self._carla = carla
        self._client = carla.Client(self._host, self._port)
        self._client.set_timeout(self._timeout_seconds)
        self._world = self._client.get_world()
        if not connect_traffic_manager:
            self._tm = None
            self._tm_unavailable_reason = "traffic manager connection disabled by caller"
            return
        self.connect_traffic_manager()

    def connect_traffic_manager(self, *, startup_timeout_seconds: float | None = None) -> None:
        if self._client is None:
            raise CarlaClientError("CARLA client is not connected")
        self._wait_for_traffic_manager_ready(
            startup_timeout_seconds=startup_timeout_seconds
        )
        try:
            self._tm = self._client.get_trafficmanager(self._traffic_manager_port)
            self._tm_unavailable_reason = None
        except Exception as exc:
            # specifically catch bind errors or timeouts during TM handshake
            self._tm = None
            self._tm_unavailable_reason = str(exc)
            logger.warning(
                "Traffic Manager unavailable at %s:%s (this process may not be the primary TM owner): %s",
                self._host,
                self._traffic_manager_port,
                exc,
            )

    def _wait_for_traffic_manager_ready(self, *, startup_timeout_seconds: float | None) -> None:
        deadline = time.monotonic() + max(
            self._timeout_seconds,
            1.0 if startup_timeout_seconds is None else startup_timeout_seconds,
        )
        last_failure: str | None = None

        while time.monotonic() < deadline:
            remaining = max(1.0, deadline - time.monotonic())
            command = [
                sys.executable,
                "-m",
                "app.executor.traffic_manager_probe",
                "--host",
                self._host,
                "--port",
                str(self._port),
                "--traffic-manager-port",
                str(self._traffic_manager_port),
                "--timeout-seconds",
                str(min(self._timeout_seconds, remaining)),
            ]
            try:
                completed = subprocess.run(
                    command,
                    capture_output=True,
                    text=True,
                    timeout=min(max(self._timeout_seconds, 1.0), remaining + 1.0),
                )
            except subprocess.TimeoutExpired as exc:
                last_failure = (
                    "traffic manager probe timed out while waiting for readiness"
                )
                time.sleep(1.0)
                continue

            if completed.returncode == 0:
                return

            stderr = (completed.stderr or "").strip()
            stdout = (completed.stdout or "").strip()
            last_failure = stderr or stdout or "traffic manager probe failed"
            time.sleep(1.0)

        raise CarlaClientError(
            last_failure
            or (
                "Traffic Manager did not become ready within "
                f"{max(self._timeout_seconds, startup_timeout_seconds or 1.0):.1f}s"
            )
        )

    @staticmethod
    def _is_tm_bind_error(exc: Exception) -> bool:
        message = str(exc).lower()
        return "bind error" in message and "traffic manager" in message

    def _mark_tm_unavailable(self, exc: Exception, *, context: str, actor_id: int | None = None) -> bool:
        if not self._is_tm_bind_error(exc):
            return False
        self._tm = None
        self._tm_unavailable_reason = str(exc)
        actor_label = "-" if actor_id is None else str(actor_id)
        logger.warning(
            "Traffic Manager bind failed during %s for actor %s: %s",
            context,
            actor_label,
            exc,
        )
        return True

    @staticmethod
    def _destroy_actor_best_effort(actor: Any) -> None:
        destroy = getattr(actor, "destroy", None)
        if callable(destroy):
            try:
                destroy()
            except Exception:
                pass

    def apply_traffic_seed(self, seed: int | None) -> None:
        if seed is None or self._tm is None:
            return
        setter = getattr(self._tm, "set_random_device_seed", None)
        if callable(setter):
            setter(int(seed))

    def _normalize_map_name(self, map_name: str) -> str:
        return normalize_map_tail(map_name)

    def resolve_map_name(self, requested_map_name: str) -> str:
        if self._client is None:
            raise CarlaClientError("CARLA client is not connected")

        available_maps = self.get_available_maps()
        requested_raw = str(requested_map_name).strip().rstrip("/")
        requested_tail = self._normalize_map_name(requested_raw).lower()

        for candidate in available_maps:
            candidate_raw = str(candidate).strip().rstrip("/")
            candidate_tail = self._normalize_map_name(candidate_raw).lower()
            if candidate_raw == requested_raw or candidate_tail == requested_tail:
                return candidate_raw

        family_candidates = [
            str(candidate).strip().rstrip("/")
            for candidate in available_maps
            if map_family_key(candidate) == map_family_key(requested_raw)
        ]
        if family_candidates:
            return choose_preferred_available_map(family_candidates)

        raise CarlaClientError(f"Map '{requested_map_name}' not found")

    def load_map(self, map_name: str) -> str:
        if self._client is None or self._world is None:
            raise CarlaClientError("CARLA client is not connected")
        resolved_map_name = self.resolve_map_name(map_name)
        current_map_name = str(self._world.get_map().name).strip().rstrip("/")
        current_map_tail = self._normalize_map_name(current_map_name).lower()
        resolved_map_tail = self._normalize_map_name(resolved_map_name).lower()
        if current_map_name == resolved_map_name or current_map_tail == resolved_map_tail:
            return current_map_name or resolved_map_name
        self._world = self._client.load_world(resolved_map_name)
        return resolved_map_name

    def get_available_maps(self) -> list[str]:
        if self._client is None:
            raise CarlaClientError("CARLA client is not connected")
        return [str(name) for name in self._client.get_available_maps()]

    def set_weather(self, preset_name: str, overrides: dict[str, Any] | None = None) -> None:
        if self._world is None or self._carla is None:
            raise CarlaClientError("CARLA world is not ready")

        weather = getattr(self._carla.WeatherParameters, preset_name, None)
        if weather is None:
            raise CarlaClientError(f"Unsupported weather preset: {preset_name}")

        runtime_weather = self._carla.WeatherParameters(
            cloudiness=float(weather.cloudiness),
            precipitation=float(weather.precipitation),
            precipitation_deposits=float(weather.precipitation_deposits),
            wind_intensity=float(weather.wind_intensity),
            sun_azimuth_angle=float(weather.sun_azimuth_angle),
            sun_altitude_angle=float(weather.sun_altitude_angle),
            fog_density=float(weather.fog_density),
            wetness=float(weather.wetness),
        )

        if overrides:
            for key, value in overrides.items():
                if key == "preset" or value is None:
                    continue
                if not hasattr(runtime_weather, key):
                    raise CarlaClientError(f"Unsupported weather field: {key}")
                setattr(runtime_weather, key, float(value))

        self._world.set_weather(runtime_weather)

    def configure_world_sync(self, enabled: bool, fixed_delta_seconds: float) -> None:
        if self._world is None:
            raise CarlaClientError("CARLA world is not ready")

        settings = self._world.get_settings()
        if self._original_sync_mode is None:
            self._original_sync_mode = bool(settings.synchronous_mode)
        if self._original_fixed_delta is None:
            self._original_fixed_delta = settings.fixed_delta_seconds

        settings.synchronous_mode = enabled
        settings.fixed_delta_seconds = fixed_delta_seconds
        self._world.apply_settings(settings)

    def configure_tm_sync(self, enabled: bool) -> None:
        if self._tm is None:
            logger.warning(
                "Skipping Traffic Manager sync change because TM is unavailable: %s",
                self._tm_unavailable_reason or "unknown reason",
            )
            return
        self._tm.set_synchronous_mode(enabled)
        self._tm_sync_enabled = enabled

    def _build_transform(self, spawn_point: dict[str, float]) -> Any:
        if self._carla is None:
            raise CarlaClientError("CARLA module is not loaded")
        return self._carla.Transform(
            self._carla.Location(
                x=spawn_point["x"],
                y=spawn_point["y"],
                z=spawn_point["z"],
            ),
            self._carla.Rotation(
                roll=spawn_point.get("roll", 0.0),
                pitch=spawn_point.get("pitch", 0.0),
                yaw=spawn_point.get("yaw", 0.0),
            ),
        )

    def _transform_to_dict(self, transform: Any) -> dict[str, float]:
        return {
            "x": float(transform.location.x),
            "y": float(transform.location.y),
            "z": float(transform.location.z),
            "roll": float(transform.rotation.roll),
            "pitch": float(transform.rotation.pitch),
            "yaw": float(transform.rotation.yaw),
        }

    def _transform_key(self, transform: Any) -> tuple[float, float, float, float, float, float]:
        payload = self._transform_to_dict(transform)
        return (
            round(payload["x"], 3),
            round(payload["y"], 3),
            round(payload["z"], 3),
            round(payload["roll"], 3),
            round(payload["pitch"], 3),
            round(payload["yaw"], 3),
        )

    def _project_to_driving_lane(self, requested_transform: Any) -> tuple[Any | None, float | None]:
        if self._world is None or self._carla is None:
            raise CarlaClientError("CARLA world is not ready")

        waypoint = self._world.get_map().get_waypoint(
            requested_transform.location,
            project_to_road=True,
            lane_type=self._carla.LaneType.Driving,
        )
        if waypoint is None:
            return None, None

        waypoint_transform = waypoint.transform
        resolved_transform = self._carla.Transform(
            self._carla.Location(
                x=float(waypoint_transform.location.x),
                y=float(waypoint_transform.location.y),
                z=max(
                    float(waypoint_transform.location.z) + 0.3,
                    float(requested_transform.location.z),
                ),
            ),
            self._carla.Rotation(
                roll=float(waypoint_transform.rotation.roll),
                pitch=float(waypoint_transform.rotation.pitch),
                yaw=float(waypoint_transform.rotation.yaw),
            ),
        )
        distance_to_requested = float(
            requested_transform.location.distance(waypoint_transform.location)
        )
        return resolved_transform, distance_to_requested

    def _build_ego_spawn_candidates(
        self,
        requested_spawn_point: dict[str, float],
        max_projection_distance_m: float = 8.0,
    ) -> list[SpawnCandidate]:
        if self._world is None:
            raise CarlaClientError("CARLA world is not ready")

        requested_transform = self._build_transform(requested_spawn_point)
        map_obj = self._world.get_map()
        spawn_points = list(map_obj.get_spawn_points())
        ordered_spawn_points = sorted(
            spawn_points,
            key=lambda transform: requested_transform.location.distance(transform.location),
        )

        candidates: list[SpawnCandidate] = []
        seen_keys: set[tuple[float, float, float, float, float, float]] = set()
        deferred_projection_candidate: SpawnCandidate | None = None

        projected_transform, distance_to_requested = self._project_to_driving_lane(
            requested_transform
        )
        if projected_transform is not None and (
            distance_to_requested is None
            or distance_to_requested <= max_projection_distance_m
            or not ordered_spawn_points
        ):
            projected_key = self._transform_key(projected_transform)
            seen_keys.add(projected_key)
            candidates.append(
                SpawnCandidate(
                    transform=projected_transform,
                    source="projected_to_driving_lane",
                    distance_to_requested_m=distance_to_requested,
                )
            )
        elif projected_transform is not None:
            deferred_projection_candidate = SpawnCandidate(
                transform=projected_transform,
                source="projected_to_driving_lane_fallback",
                distance_to_requested_m=distance_to_requested,
            )

        for index, transform in enumerate(ordered_spawn_points):
            transform_key = self._transform_key(transform)
            if transform_key in seen_keys:
                continue

            candidates.append(
                SpawnCandidate(
                    transform=transform,
                    source="map_spawn_point_fallback",
                    distance_to_requested_m=float(
                        requested_transform.location.distance(transform.location)
                    ),
                    fallback_index=index,
                )
            )
            seen_keys.add(transform_key)

        if deferred_projection_candidate is not None:
            deferred_key = self._transform_key(deferred_projection_candidate.transform)
            if deferred_key not in seen_keys:
                candidates.append(deferred_projection_candidate)

        return candidates

    def spawn_ego_vehicle(
        self,
        blueprint: str,
        spawn_point: dict[str, float],
        role_name: str = "ego_vehicle",
    ) -> EgoSpawnResult:
        if self._world is None:
            raise CarlaClientError("CARLA world is not ready")

        blueprint_library = self._world.get_blueprint_library()
        blueprint_obj = blueprint_library.find(blueprint)
        if blueprint_obj.has_attribute("role_name"):
            blueprint_obj.set_attribute("role_name", role_name)

        candidates = self._build_ego_spawn_candidates(spawn_point)
        if not candidates:
            raise CarlaClientError("Failed to resolve any valid ego spawn point")

        for candidate in candidates:
            actor = self._world.try_spawn_actor(blueprint_obj, candidate.transform)
            if actor is None:
                continue

            self._spawned_actors.append(actor)
            return EgoSpawnResult(
                actor=actor,
                resolved_spawn_point=self._transform_to_dict(candidate.transform),
                source=candidate.source,
                requested_spawn_point=dict(spawn_point),
                distance_to_requested_m=candidate.distance_to_requested_m,
                fallback_index=candidate.fallback_index,
            )

        raise CarlaClientError(
            f"Failed to spawn ego vehicle after trying {len(candidates)} candidate spawn points"
        )

    def spawn_actor(
        self,
        blueprint: str,
        spawn_point: dict[str, float],
        *,
        role_name: str,
        actor_kind: str = "vehicle",
    ) -> Any:
        if self._world is None:
            raise CarlaClientError("CARLA world is not ready")

        blueprint_library = self._world.get_blueprint_library()
        blueprint_obj = blueprint_library.find(blueprint)
        if blueprint_obj.has_attribute("role_name"):
            blueprint_obj.set_attribute("role_name", role_name)
        if actor_kind == "walker" and blueprint_obj.has_attribute("is_invincible"):
            blueprint_obj.set_attribute("is_invincible", "false")

        actor = self._world.try_spawn_actor(blueprint_obj, self._build_transform(spawn_point))
        if actor is None:
            raise CarlaClientError(
                f"Failed to spawn actor role={role_name} blueprint={blueprint}"
            )
        self._spawned_actors.append(actor)
        return actor

    def set_vehicle_autopilot(self, vehicle: Any, enabled: bool) -> bool:
        if vehicle is None:
            return False
        try:
            vehicle.set_autopilot(enabled, self._traffic_manager_port)
        except Exception as exc:
            logger.error("Failed to set autopilot for vehicle %s: %s", vehicle.id, exc)
            if self._mark_tm_unavailable(
                exc,
                context="vehicle.set_autopilot",
                actor_id=int(getattr(vehicle, "id", 0) or 0),
            ):
                return False
            raise CarlaClientError(
                f"Failed to set autopilot for vehicle {getattr(vehicle, 'id', 'unknown')}: {exc}"
            ) from exc
        return True

    def configure_tm_autopilot(
        self,
        vehicle: Any,
        *,
        enabled: bool,
        target_speed_mps: float | None = None,
        auto_lane_change: bool | None = None,
        distance_between_vehicles: float | None = None,
        ignore_vehicles_percentage: float | None = None,
    ) -> None:
        if vehicle is None:
            return

        autopilot_applied = self.set_vehicle_autopilot(vehicle, enabled)
        if not enabled:
            disable_constant_velocity = getattr(vehicle, "disable_constant_velocity", None)
            if callable(disable_constant_velocity):
                disable_constant_velocity()
            return
        if not autopilot_applied:
            return

        if self._tm is not None:
            try:
                if auto_lane_change is not None and hasattr(self._tm, "auto_lane_change"):
                    self._tm.auto_lane_change(vehicle, bool(auto_lane_change))
                if (
                    distance_between_vehicles is not None
                    and hasattr(self._tm, "distance_to_leading_vehicle")
                ):
                    self._tm.distance_to_leading_vehicle(vehicle, float(distance_between_vehicles))
                if (
                    ignore_vehicles_percentage is not None
                    and hasattr(self._tm, "ignore_vehicles_percentage")
                ):
                    self._tm.ignore_vehicles_percentage(
                        vehicle, float(ignore_vehicles_percentage)
                    )
                if (
                    target_speed_mps is not None
                    and hasattr(self._tm, "vehicle_percentage_speed_difference")
                ):
                    speed_limit_kmh = max(
                        float(getattr(vehicle, "get_speed_limit", lambda: 0.0)()),
                        1.0,
                    )
                    target_speed_kmh = max(0.0, float(target_speed_mps) * 3.6)
                    percentage = ((speed_limit_kmh - target_speed_kmh) / speed_limit_kmh) * 100.0
                    self._tm.vehicle_percentage_speed_difference(
                        vehicle,
                        max(-100.0, min(100.0, percentage)),
                    )
            except Exception as exc:
                if self._mark_tm_unavailable(
                    exc,
                    context="configure_tm_autopilot",
                    actor_id=int(getattr(vehicle, "id", 0) or 0),
                ):
                    return
                raise CarlaClientError(
                    f"Failed to configure Traffic Manager autopilot for vehicle {getattr(vehicle, 'id', 'unknown')}: {exc}"
                ) from exc
            return

        if target_speed_mps is None or self._carla is None:
            return
        forward = vehicle.get_transform().get_forward_vector()
        vector3d = getattr(self._carla, "Vector3D", None)
        if vector3d is None:
            return
        vehicle.set_target_velocity(
            vector3d(
                x=float(forward.x) * float(target_speed_mps),
                y=float(forward.y) * float(target_speed_mps),
                z=float(forward.z) * float(target_speed_mps),
            )
        )

    def find_actor_by_role_name(self, role_name: str) -> Any | None:
        if self._world is None:
            raise CarlaClientError("CARLA world is not ready")

        normalized = role_name.strip()
        if not normalized:
            return None

        actors = self._world.get_actors()
        for actor in actors:
            actor_role_name = str(actor.attributes.get("role_name") or "").strip()
            if actor_role_name == normalized:
                return actor
        return None

    def actor_transform_to_dict(self, actor: Any) -> dict[str, float]:
        return self._transform_to_dict(actor.get_transform())

    @staticmethod
    def _deadline_exceeded(deadline_monotonic: float | None) -> bool:
        return deadline_monotonic is not None and time.monotonic() >= deadline_monotonic

    @staticmethod
    def _abort_requested(should_abort: Callable[[], bool] | None) -> bool:
        return bool(should_abort is not None and should_abort())

    def spawn_fixed_traffic_vehicles(
        self,
        count: int,
        *,
        anchor_spawn_point: dict[str, float] | None = None,
        autopilot: bool = True,
        min_distance_from_anchor_m: float = 8.0,
    ) -> list[Any]:
        if self._world is None:
            raise CarlaClientError("CARLA world is not ready")

        blueprint_library = sorted(
            self._world.get_blueprint_library().filter("vehicle.*"),
            key=lambda blueprint: blueprint.id,
        )
        spawn_points = list(self._world.get_map().get_spawn_points())
        anchor_transform = (
            self._build_transform(anchor_spawn_point) if anchor_spawn_point is not None else None
        )

        if anchor_transform is not None:
            spawn_points.sort(
                key=lambda transform: anchor_transform.location.distance(transform.location)
            )
        else:
            spawn_points.sort(
                key=lambda transform: (
                    round(float(transform.location.x), 3),
                    round(float(transform.location.y), 3),
                    round(float(transform.rotation.yaw), 3),
                )
            )

        spawned: list[Any] = []
        for index, spawn_point in enumerate(spawn_points):
            if len(spawned) >= count:
                break
            if anchor_transform is not None:
                distance = float(anchor_transform.location.distance(spawn_point.location))
                if distance < min_distance_from_anchor_m:
                    continue

            blueprint_obj = blueprint_library[index % len(blueprint_library)]
            if blueprint_obj.has_attribute("role_name"):
                blueprint_obj.set_attribute("role_name", f"scenario_npc_{index}")
            actor = self._world.try_spawn_actor(blueprint_obj, spawn_point)
            if actor is None:
                continue
            if autopilot and not self.set_vehicle_autopilot(actor, True):
                self._destroy_actor_best_effort(actor)
                continue
            self._spawned_actors.append(actor)
            spawned.append(actor)

        return spawned

    def spawn_traffic_vehicles(
        self,
        count: int,
        autopilot: bool = True,
        *,
        seed: int | None = None,
        anchor_spawn_point: dict[str, float] | None = None,
        min_distance_from_anchor_m: float = 12.0,
        deadline_monotonic: float | None = None,
        should_abort: Callable[[], bool] | None = None,
    ) -> list[Any]:
        if self._world is None:
            raise CarlaClientError("CARLA world is not ready")

        blueprint_library = sorted(
            self._world.get_blueprint_library().filter("vehicle.*"),
            key=lambda blueprint: blueprint.id,
        )
        spawn_points = list(self._world.get_map().get_spawn_points())
        rng = random.Random(seed) if seed is not None else random
        anchor_transform = (
            self._build_transform(anchor_spawn_point) if anchor_spawn_point is not None else None
        )
        if anchor_transform is not None:
            spawn_points = [
                spawn_point
                for spawn_point in spawn_points
                if float(anchor_transform.location.distance(spawn_point.location))
                >= min_distance_from_anchor_m
            ]
            spawn_points.sort(
                key=lambda spawn_point: (
                    float(anchor_transform.location.distance(spawn_point.location)),
                    round(float(spawn_point.location.x), 3),
                    round(float(spawn_point.location.y), 3),
                    round(float(spawn_point.rotation.yaw), 3),
                )
            )
            preferred_count = max(count * 4, count + 8)
            preferred_points = spawn_points[:preferred_count]
            remaining_points = spawn_points[preferred_count:]
            if len(preferred_points) > 1:
                rng.shuffle(preferred_points)
            spawn_points = preferred_points + remaining_points
        else:
            rng.shuffle(spawn_points)

        spawned: list[Any] = []
        for index, spawn_point in enumerate(spawn_points):
            if self._abort_requested(should_abort) or self._deadline_exceeded(deadline_monotonic):
                break
            if len(spawned) >= count:
                break
            blueprint_obj = blueprint_library[index % len(blueprint_library)]
            if seed is not None and blueprint_library:
                blueprint_obj = blueprint_library[rng.randrange(len(blueprint_library))]
            if blueprint_obj.has_attribute("role_name"):
                blueprint_obj.set_attribute("role_name", f"scenario_npc_{index}")
            actor = self._world.try_spawn_actor(blueprint_obj, spawn_point)
            if actor is None:
                continue
            if autopilot and not self.set_vehicle_autopilot(actor, True):
                self._destroy_actor_best_effort(actor)
                continue
            self._spawned_actors.append(actor)
            spawned.append(actor)

        return spawned

    def spawn_traffic_walkers(
        self,
        count: int,
        *,
        seed: int | None = None,
        anchor_location: Any | None = None,
        max_radius_m: float | None = None,
        deadline_monotonic: float | None = None,
        should_abort: Callable[[], bool] | None = None,
    ) -> list[Any]:
        if self._world is None or self._carla is None:
            raise CarlaClientError("CARLA world is not ready")

        walker_blueprints = sorted(
            self._world.get_blueprint_library().filter("walker.pedestrian.*"),
            key=lambda blueprint: blueprint.id,
        )
        controller_blueprints = list(
            self._world.get_blueprint_library().filter("controller.ai.walker")
        )
        if not walker_blueprints:
            raise CarlaClientError("No walker blueprints available")

        rng = random.Random(seed) if seed is not None else random
        spawn_points: list[Any] = []
        search_radii = (
            [max_radius_m, max_radius_m * 1.5 if max_radius_m is not None else None, None]
            if anchor_location is not None
            else [None]
        )
        for radius in search_radii:
            if self._abort_requested(should_abort) or self._deadline_exceeded(deadline_monotonic):
                break
            if len(spawn_points) >= count:
                break
            max_attempts = max(count * 10, count + 10)
            for _ in range(max_attempts):
                if self._abort_requested(should_abort) or self._deadline_exceeded(
                    deadline_monotonic
                ):
                    break
                location = self._world.get_random_location_from_navigation()
                if location is None:
                    continue
                if (
                    anchor_location is not None
                    and radius is not None
                    and float(location.distance(anchor_location)) > float(radius)
                ):
                    continue
                spawn_points.append(self._carla.Transform(location))
                if len(spawn_points) >= count:
                    break

        spawned_walkers: list[Any] = []
        controller_blueprint = controller_blueprints[0] if controller_blueprints else None
        for index, spawn_point in enumerate(spawn_points):
            if self._abort_requested(should_abort) or self._deadline_exceeded(deadline_monotonic):
                break
            walker_blueprint = walker_blueprints[index % len(walker_blueprints)]
            if seed is not None and walker_blueprints:
                walker_blueprint = walker_blueprints[rng.randrange(len(walker_blueprints))]
            if walker_blueprint.has_attribute("is_invincible"):
                walker_blueprint.set_attribute("is_invincible", "false")
            if walker_blueprint.has_attribute("role_name"):
                walker_blueprint.set_attribute("role_name", f"scenario_walker_{index}")

            walker_actor = self._world.try_spawn_actor(walker_blueprint, spawn_point)
            if walker_actor is None:
                continue

            self._spawned_actors.append(walker_actor)
            spawned_walkers.append(walker_actor)

            if controller_blueprint is None:
                continue

            controller_actor = self._world.try_spawn_actor(
                controller_blueprint,
                self._carla.Transform(),
                walker_actor,
            )
            if controller_actor is None:
                continue

            self._spawned_actors.append(controller_actor)
            controller_actor.start()
            destination = self._world.get_random_location_from_navigation()
            if destination is not None:
                controller_actor.go_to_location(destination)

            max_speed = 1.4
            if walker_blueprint.has_attribute("speed"):
                recommended_values = walker_blueprint.get_attribute("speed").recommended_values
                numeric_values: list[float] = []
                for value in recommended_values:
                    try:
                        numeric_values.append(float(value))
                    except (TypeError, ValueError):
                        continue
                if numeric_values:
                    max_speed = numeric_values[1] if len(numeric_values) > 1 else numeric_values[0]
            controller_actor.set_max_speed(max_speed)

        return spawned_walkers

    def spawn_event_actor_ahead(
        self,
        ego_vehicle: Any,
        *,
        actor_kind: str = "walker",
        distance_m: float = 18.0,
        lateral_offset_m: float = 2.8,
        role_name: str = "scenario_event_actor",
    ) -> Any | None:
        if self._world is None or self._carla is None:
            raise CarlaClientError("CARLA world is not ready")

        ego_transform = ego_vehicle.get_transform()
        anchor_transform = ego_transform
        waypoint = self._world.get_map().get_waypoint(
            ego_transform.location,
            project_to_road=True,
            lane_type=self._carla.LaneType.Driving,
        )
        if waypoint is not None:
            next_waypoints = waypoint.next(distance_m)
            if next_waypoints:
                anchor_transform = next_waypoints[0].transform

        forward = anchor_transform.get_forward_vector()
        lateral = self._carla.Location(
            x=-forward.y * lateral_offset_m,
            y=forward.x * lateral_offset_m,
            z=0.0,
        )
        blocker_location = anchor_transform.location + lateral
        blocker_location.z = float(blocker_location.z) + 0.8
        blocker_rotation = self._carla.Rotation(
            pitch=0.0,
            yaw=anchor_transform.rotation.yaw + 90.0,
            roll=0.0,
        )
        blocker_transform = self._carla.Transform(blocker_location, blocker_rotation)

        if actor_kind == "vehicle":
            blueprints = self._world.get_blueprint_library().filter("vehicle.*")
        elif actor_kind == "barrier":
            blueprints = self._world.get_blueprint_library().filter("static.prop.streetbarrier")
        else:
            blueprints = self._world.get_blueprint_library().filter("walker.pedestrian.*")
        if not blueprints and actor_kind != "barrier":
            blueprints = self._world.get_blueprint_library().filter("static.prop.streetbarrier")
        if not blueprints:
            blueprints = self._world.get_blueprint_library().filter("vehicle.*")
        if not blueprints:
            return None

        blueprint = sorted(blueprints, key=lambda item: item.id)[0]
        if blueprint.has_attribute("role_name"):
            blueprint.set_attribute("role_name", role_name)
        actor = self._world.try_spawn_actor(blueprint, blocker_transform)
        if actor is not None:
            if actor_kind == "vehicle":
                actor.set_autopilot(False, self._traffic_manager_port)
            self._spawned_actors.append(actor)
        return actor

    def spawn_crossing_actor_ahead(
        self, ego_vehicle: Any, distance_m: float = 18.0, lateral_offset_m: float = 2.8
    ) -> Any | None:
        return self.spawn_event_actor_ahead(
            ego_vehicle,
            actor_kind="walker",
            distance_m=distance_m,
            lateral_offset_m=lateral_offset_m,
        )

    def tick(self) -> CarlaTickResult:
        if self._world is None:
            raise CarlaClientError("CARLA world is not ready")

        frame = self._world.tick()
        snapshot = self._world.get_snapshot()
        sim_time = float(snapshot.timestamp.elapsed_seconds)
        return CarlaTickResult(frame=frame, sim_time=sim_time)

    def wait_for_tick(self, *, timeout_seconds: float | None = None) -> CarlaTickResult:
        if self._world is None:
            raise CarlaClientError("CARLA world is not ready")

        snapshot = self._world.wait_for_tick(seconds=timeout_seconds)
        timestamp = snapshot.timestamp
        return CarlaTickResult(
            frame=int(timestamp.frame),
            sim_time=float(timestamp.elapsed_seconds),
        )

    def start_recorder(self, recorder_path: Path) -> None:
        if self._client is None:
            raise CarlaClientError("CARLA client is not connected")
        self._client.start_recorder(str(recorder_path))

    def stop_recorder(self) -> None:
        if self._client is None:
            return
        self._client.stop_recorder()

    def cleanup(self) -> None:
        self._destroy_spawned_actors()
        self._restore_world_settings()

    def _destroy_spawned_actors(self) -> None:
        if not self._spawned_actors:
            return
        if self._client is None or self._carla is None:
            return

        commands = [self._carla.command.DestroyActor(actor.id) for actor in self._spawned_actors]
        self._client.apply_batch(commands)
        self._spawned_actors.clear()

    def _restore_world_settings(self) -> None:
        if self._world is None:
            return

        settings = self._world.get_settings()
        if self._original_sync_mode is not None:
            settings.synchronous_mode = self._original_sync_mode
        if self._original_fixed_delta is not None:
            settings.fixed_delta_seconds = self._original_fixed_delta
        self._world.apply_settings(settings)

        if self._tm is not None and self._tm_sync_enabled:
            self._tm.set_synchronous_mode(False)

    def spawned_actor_count(self) -> int:
        return len(self._spawned_actors)
