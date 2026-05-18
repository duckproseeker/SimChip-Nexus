from __future__ import annotations

from dataclasses import dataclass

import pytest

from app.core.config import get_settings
from app.core.models import RunRecord, RunStatus
from app.executor.native_runtime_controller import NativeRuntimeController
from app.storage.artifact_store import ArtifactStore
from app.storage.run_store import RunStore
from app.utils.time_utils import now_utc

VALID_DESCRIPTOR = {
    "version": 1,
    "scenario_name": "town10_autonomous_demo",
    "map_name": "Town10HD_Opt",
    "weather": {"preset": "ClearNoon"},
    "sync": {"enabled": False, "fixed_delta_seconds": 0.1},
    "ego_vehicle": {
        "blueprint": "vehicle.lincoln.mkz_2017",
        "spawn_point": {
            "x": 10.0,
            "y": 20.0,
            "z": 0.5,
            "roll": 0.0,
            "pitch": 0.0,
            "yaw": 90.0,
        },
    },
    "traffic": {"enabled": False, "num_vehicles": 0, "num_walkers": 0},
    "sensors": {"enabled": False},
    "termination": {"timeout_seconds": 1, "success_condition": "timeout"},
    "recorder": {"enabled": False},
    "metadata": {"author": "test", "tags": ["native"], "description": "native controller"},
}


class FakeLocation:
    def __init__(self, x: float, y: float, z: float) -> None:
        self.x = x
        self.y = y
        self.z = z

    def distance(self, other: FakeLocation) -> float:
        return ((self.x - other.x) ** 2 + (self.y - other.y) ** 2 + (self.z - other.z) ** 2) ** 0.5


class FakeForwardVector:
    def __init__(self, x: float, y: float, z: float = 0.0) -> None:
        self.x = x
        self.y = y
        self.z = z


class FakeTransform:
    def __init__(self, location: FakeLocation) -> None:
        self.location = location

    def get_forward_vector(self) -> FakeForwardVector:
        return FakeForwardVector(1.0, 0.0, 0.0)


class FakeActor:
    _next_id = 1

    def __init__(self, x: float, y: float, z: float, *, role_name: str = "hero") -> None:
        self.id = FakeActor._next_id
        FakeActor._next_id += 1
        self._location = FakeLocation(x, y, z)
        self.attributes = {"role_name": role_name}
        self.autopilot_payloads: list[dict[str, float | bool | None]] = []

    def get_location(self) -> FakeLocation:
        return self._location

    def get_transform(self) -> FakeTransform:
        return FakeTransform(self._location)


@dataclass
class FakeSpawnResult:
    actor: FakeActor
    source: str
    requested_spawn_point: dict[str, float]
    resolved_spawn_point: dict[str, float]


class FakeTickResult:
    def __init__(self, frame: int, sim_time: float) -> None:
        self.frame = frame
        self.sim_time = sim_time


class FakeCarlaClient:
    def __init__(
        self, host: str, port: int, timeout_seconds: float, traffic_manager_port: int
    ) -> None:
        self.loaded_map_name: str | None = None
        self.weather_updates: list[dict[str, object]] = []
        self.sync_updates: list[tuple[bool, float]] = []
        self.tm_sync_updates: list[bool] = []
        self.actors: list[FakeActor] = []
        self.current_frame = 0
        self.current_sim_time = 0.0

    def connect(self, *, connect_traffic_manager: bool = True) -> None:
        _ = connect_traffic_manager

    def connect_traffic_manager(self, *, startup_timeout_seconds: float | None = None) -> None:
        _ = startup_timeout_seconds

    def apply_traffic_seed(self, seed: int | None) -> None:
        _ = seed

    def load_map(self, map_name: str) -> str:
        self.loaded_map_name = map_name
        return map_name

    def set_weather(self, preset_name: str, overrides=None) -> None:
        self.weather_updates.append({"preset": preset_name, "overrides": overrides})

    def configure_world_sync(self, enabled: bool, fixed_delta_seconds: float) -> None:
        self.sync_updates.append((enabled, fixed_delta_seconds))

    def configure_tm_sync(self, enabled: bool) -> None:
        self.tm_sync_updates.append(enabled)

    def spawn_ego_vehicle(
        self, blueprint: str, spawn_point: dict[str, float], role_name: str = "hero"
    ) -> FakeSpawnResult:
        _ = blueprint
        _ = role_name
        actor = FakeActor(spawn_point["x"], spawn_point["y"], spawn_point["z"], role_name=role_name)
        self.actors.append(actor)
        return FakeSpawnResult(
            actor=actor,
            source="projected_to_driving_lane",
            requested_spawn_point=dict(spawn_point),
            resolved_spawn_point=dict(spawn_point),
        )

    def spawn_actor(
        self,
        blueprint: str,
        spawn_point: dict[str, float],
        *,
        role_name: str,
        actor_kind: str = "vehicle",
    ) -> FakeActor:
        _ = blueprint
        _ = role_name
        _ = actor_kind
        actor = FakeActor(spawn_point["x"], spawn_point["y"], spawn_point["z"], role_name=role_name)
        self.actors.append(actor)
        return actor

    def configure_tm_autopilot(
        self,
        vehicle: FakeActor,
        *,
        enabled: bool,
        target_speed_mps: float | None = None,
        auto_lane_change: bool | None = None,
        distance_between_vehicles: float | None = None,
        ignore_vehicles_percentage: float | None = None,
    ) -> None:
        vehicle.autopilot_payloads.append(
            {
                "enabled": enabled,
                "target_speed_mps": target_speed_mps,
                "auto_lane_change": auto_lane_change,
                "distance_between_vehicles": distance_between_vehicles,
                "ignore_vehicles_percentage": ignore_vehicles_percentage,
            }
        )

    def actor_transform_to_dict(self, actor: FakeActor) -> dict[str, float]:
        location = actor.get_location()
        return {
            "x": location.x,
            "y": location.y,
            "z": location.z,
            "roll": 0.0,
            "pitch": 0.0,
            "yaw": 0.0,
        }

    def find_vehicle_actor_for_sensor_attachment(
        self, preferred_role_name: str = "hero"
    ) -> FakeActor | None:
        for actor in self.actors:
            if actor.attributes.get("role_name") == preferred_role_name:
                return actor
        return self.actors[0] if self.actors else None

    def spawn_traffic_vehicles(self, count: int, **kwargs) -> list[FakeActor]:
        _ = count
        _ = kwargs
        return []

    def spawn_traffic_walkers(self, count: int, **kwargs) -> list[FakeActor]:
        _ = count
        _ = kwargs
        return []

    def tick(self) -> FakeTickResult:
        self.current_frame += 1
        self.current_sim_time += 0.1
        return FakeTickResult(self.current_frame, self.current_sim_time)

    def wait_for_tick(self, *, timeout_seconds: float | None = None) -> FakeTickResult:
        _ = timeout_seconds
        return self.tick()

    def spawned_actor_count(self) -> int:
        return len(self.actors)

    def cleanup(self) -> None:
        return


class OffsetSimTimeCarlaClient(FakeCarlaClient):
    def __init__(
        self, host: str, port: int, timeout_seconds: float, traffic_manager_port: int
    ) -> None:
        super().__init__(host, port, timeout_seconds, traffic_manager_port)
        self.current_sim_time = 120.0


class ReplayCarlaClient(FakeCarlaClient):
    instances: list[ReplayCarlaClient] = []

    def __init__(
        self, host: str, port: int, timeout_seconds: float, traffic_manager_port: int
    ) -> None:
        super().__init__(host, port, timeout_seconds, traffic_manager_port)
        self.replay_requests: list[dict[str, object]] = []
        self.spawn_plan_attempted = False
        ReplayCarlaClient.instances.append(self)

    def replay_file(
        self,
        recorder_path,
        *,
        start_seconds: float,
        duration_seconds: float,
        follow_id: int = 0,
        replay_sensors: bool = False,
    ) -> str:
        self.replay_requests.append(
            {
                "recorder_path": str(recorder_path),
                "start_seconds": start_seconds,
                "duration_seconds": duration_seconds,
                "follow_id": follow_id,
                "replay_sensors": replay_sensors,
            }
        )
        self.actors.append(FakeActor(0.0, 0.0, 0.5, role_name="hero"))
        return "ok"

    def spawn_ego_vehicle(self, *args, **kwargs):
        self.spawn_plan_attempted = True
        raise AssertionError("replay runs must not spawn native descriptor actors")


def test_native_runtime_controller_executes_native_descriptor_run() -> None:
    settings = get_settings()
    run_store = RunStore(settings.runs_root)
    artifact_store = ArtifactStore(settings.artifacts_root)

    run_id = f"run_native_descriptor_success_{now_utc().strftime('%Y%m%d%H%M%S%f')}"
    run_dir = artifact_store.init_run(run_id)
    run = RunRecord(
        run_id=run_id,
        status=RunStatus.QUEUED,
        created_at=now_utc(),
        updated_at=now_utc(),
        scenario_name="town10_autonomous_demo",
        map_name="Town10HD_Opt",
        descriptor=VALID_DESCRIPTOR,
        artifact_dir=str(run_dir),
        execution_backend="native",
        scenario_source={
            "provider": "native",
            "launch_mode": "native_descriptor",
            "template_params": {"targetSpeedMps": 6.5},
        },
    )
    run_store.create(run)
    artifact_store.write_status(run)

    controller = NativeRuntimeController(
        settings=settings,
        run_store=run_store,
        artifact_store=artifact_store,
        client_factory=FakeCarlaClient,
    )
    controller.execute_run(run_id)

    run_after = run_store.get(run_id)
    assert run_after.status == RunStatus.COMPLETED
    metrics = artifact_store.read_metrics(run_id)
    assert metrics is not None
    assert metrics["final_status"] == "COMPLETED"
    assert metrics["executed_tick_count"] >= 1

    events = artifact_store.read_events(run_id)
    event_types = {event["event_type"] for event in events}
    assert "SCENARIO_STARTED" in event_types
    assert "EGO_SPAWNED" in event_types
    assert "CLEANUP_FINISHED" in event_types


def test_native_runtime_controller_uses_relative_sim_time_for_timeout() -> None:
    settings = get_settings()
    run_store = RunStore(settings.runs_root)
    artifact_store = ArtifactStore(settings.artifacts_root)

    run_id = f"run_native_descriptor_relative_time_{now_utc().strftime('%Y%m%d%H%M%S%f')}"
    run_dir = artifact_store.init_run(run_id)
    run = RunRecord(
        run_id=run_id,
        status=RunStatus.QUEUED,
        created_at=now_utc(),
        updated_at=now_utc(),
        scenario_name="town10_autonomous_demo",
        map_name="Town10HD_Opt",
        descriptor=VALID_DESCRIPTOR,
        artifact_dir=str(run_dir),
        execution_backend="native",
        scenario_source={
            "provider": "native",
            "launch_mode": "native_descriptor",
            "template_params": {"targetSpeedMps": 6.5},
        },
    )
    run_store.create(run)
    artifact_store.write_status(run)

    controller = NativeRuntimeController(
        settings=settings,
        run_store=run_store,
        artifact_store=artifact_store,
        client_factory=OffsetSimTimeCarlaClient,
    )
    controller.execute_run(run_id)

    run_after = run_store.get(run_id)
    assert run_after.status == RunStatus.COMPLETED
    metrics = artifact_store.read_metrics(run_id)
    assert metrics is not None
    assert metrics["final_status"] == "COMPLETED"
    assert metrics["executed_tick_count"] >= 10
    assert metrics["sim_elapsed_seconds"] >= 1.0


def test_native_runtime_controller_replay_run_calls_replay_file_without_spawn_plan() -> None:
    settings = get_settings()
    run_store = RunStore(settings.runs_root)
    artifact_store = ArtifactStore(settings.artifacts_root)

    run_id = f"run_recorder_replay_{now_utc().strftime('%Y%m%d%H%M%S%f')}"
    run_dir = artifact_store.init_run(run_id)
    recorder_path = run_dir / "recorder" / "source.log"
    recorder_path.parent.mkdir(parents=True, exist_ok=True)
    recorder_path.write_bytes(b"recorder")

    descriptor = {
        **VALID_DESCRIPTOR,
        "sync": {"enabled": True, "fixed_delta_seconds": 0.1},
        "termination": {"timeout_seconds": 1, "success_condition": "timeout"},
        "traffic": {"enabled": False, "num_vehicles": 0, "num_walkers": 0},
        "recorder": {"enabled": False},
    }
    run = RunRecord(
        run_id=run_id,
        status=RunStatus.QUEUED,
        created_at=now_utc(),
        updated_at=now_utc(),
        scenario_name="town10_autonomous_demo",
        map_name="Town10HD_Opt",
        descriptor=descriptor,
        artifact_dir=str(run_dir),
        execution_backend="native",
        scenario_source={
            "provider": "carla_recorder",
            "launch_mode": "carla_recorder_replay",
            "recording_id": "rec_source",
            "source_run_id": "run_source",
            "recorder_log_path": str(recorder_path),
            "replay_start_seconds": 1.5,
            "replay_duration_seconds": 0.2,
            "replay_fixed_delta_seconds": 0.1,
            "replay_sensor_mode": "carla_live",
            "replay_sensors": False,
            "sensor_warmup_seconds": 0.4,
        },
    )
    run_store.create(run)
    artifact_store.write_status(run)
    ReplayCarlaClient.instances.clear()

    controller = NativeRuntimeController(
        settings=settings,
        run_store=run_store,
        artifact_store=artifact_store,
        client_factory=ReplayCarlaClient,
    )
    controller.execute_run(run_id)

    run_after = run_store.get(run_id)
    assert run_after.status == RunStatus.COMPLETED
    replay_client = ReplayCarlaClient.instances[0]
    assert replay_client.replay_requests[0]["recorder_path"] == str(recorder_path)
    assert replay_client.replay_requests[0]["start_seconds"] == 1.1
    assert replay_client.replay_requests[0]["duration_seconds"] == pytest.approx(0.6)
    assert replay_client.replay_requests[0]["follow_id"] == 0
    assert replay_client.replay_requests[0]["replay_sensors"] is False
    assert replay_client.spawn_plan_attempted is False

    events = artifact_store.read_events(run_id)
    event_types = {event["event_type"] for event in events}
    assert "RECORDER_REPLAY_STARTED" in event_types
    assert "RECORDER_REPLAY_EGO_READY" in event_types
    assert "RECORDER_REPLAY_WARMUP_STARTED" in event_types
    assert "RECORDER_REPLAY_WARMUP_COMPLETED" in event_types
    assert "SENSOR_RECORDING_READY" not in event_types
    assert "SENSOR_RECORDING_FAILED" not in event_types
    assert "EGO_SPAWNED" not in event_types
