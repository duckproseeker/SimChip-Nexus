from __future__ import annotations

import logging
import time
import traceback
from collections.abc import Callable
from pathlib import Path
from typing import Any

from app.core.config import Settings
from app.core.models import EventLevel, RunEvent, RunStatus
from app.executor.carla_client import CarlaClient, CarlaTickResult
from app.executor.hil_runtime_orchestrator import HilRuntimeOrchestrator, HilRuntimeStep
from app.executor.recorder import RecorderManager
from app.executor.sensor_recorder import SensorRecorderProcess, SensorRecorderResult
from app.executor.telemetry import TelemetryCollector
from app.scenario.native_xosc import (
    NativeCondition,
    NativeEntityAction,
    NativeScenarioEntity,
    NativeScenarioEvent,
    NativeScenarioPlan,
    NativeTrigger,
    build_native_descriptor_plan,
    load_native_xosc_plan,
)
from app.scenario.validators import validate_descriptor
from app.storage.artifact_store import ArtifactStore
from app.storage.run_control_store import (
    RECORDER_STATUS_ERROR,
    RECORDER_STATUS_RUNNING,
    RECORDER_STATUS_STARTING,
    RECORDER_STATUS_STOPPED,
    SENSOR_CAPTURE_STATUS_ERROR,
    SENSOR_CAPTURE_STATUS_RUNNING,
    SENSOR_CAPTURE_STATUS_STARTING,
    SENSOR_CAPTURE_STATUS_STOPPED,
    RunControlStore,
    build_default_recorder_control,
    build_default_sensor_capture_control,
)
from app.storage.run_store import RunStore
from app.utils.time_utils import now_utc

logger = logging.getLogger(__name__)


class NativeRuntimeController:
    """Lightweight native runtime for descriptor-based and XOSC-backed runs."""

    def __init__(
        self,
        settings: Settings,
        run_store: RunStore,
        artifact_store: ArtifactStore,
        heartbeat_callback: Callable[[str], None] | None = None,
        client_factory: Callable[[str, int, float, int], CarlaClient] = CarlaClient,
    ) -> None:
        self._settings = settings
        self._run_store = run_store
        self._artifact_store = artifact_store
        self._control_store = RunControlStore(settings.controls_root)
        self._heartbeat_callback = heartbeat_callback
        self._client_factory = client_factory
        self._hil_runtime_orchestrator = HilRuntimeOrchestrator(
            settings,
            event_callback=self._emit_event,
            log_callback=self._artifact_store.append_run_log,
        )

    def execute_run(self, run_id: str) -> None:
        run = self._run_store.get(run_id)
        descriptor = validate_descriptor(run.descriptor)

        if run.status != RunStatus.QUEUED:
            logger.warning("Skip run %s because status=%s", run_id, run.status)
            return

        if run.cancel_requested:
            self._transition(run_id, RunStatus.CANCELED, set_ended_at=True)
            self._emit_event(run_id, "SCENARIO_COMPLETED", "运行在执行前被取消")
            return

        telemetry = TelemetryCollector(run_id, descriptor.scenario_name, descriptor.map_name)
        client: CarlaClient | None = None
        sensor_recorder: SensorRecorderProcess | None = None
        sensor_recording_result: SensorRecorderResult | None = None
        recorder_manager: RecorderManager | None = None
        recorder_client: CarlaClient | None = None
        hil_started_steps: list[HilRuntimeStep] = []
        background_actor_count = 0
        spawned_actor_count = 0
        failure_reason: str | None = None
        final_status = RunStatus.COMPLETED
        last_environment_signature: dict[str, Any] | None = None
        scenario_start_sim_time: float | None = None

        try:
            self._transition(run_id, RunStatus.STARTING)
            self._emit_event(run_id, "RUN_STARTING", "native runtime 开始启动运行")
            self._initialize_runtime_control(run_id, descriptor)

            plan = self._resolve_plan(run, descriptor)
            for warning in plan.warnings:
                self._emit_event(
                    run_id,
                    "NATIVE_XOSC_WARNING",
                    warning,
                    level=EventLevel.WARNING,
                )

            hil_started_steps = self._hil_runtime_orchestrator.start_pipeline(
                run_id,
                run,
                descriptor,
            )

            client = self._client_factory(
                self._settings.carla_host,
                self._settings.carla_port,
                self._settings.carla_timeout_seconds,
                self._settings.traffic_manager_port,
            )
            self._emit_event(run_id, "CARLA_CONNECTING", "正在建立 CARLA client 连接")
            client.connect(connect_traffic_manager=False)
            self._emit_event(run_id, "CARLA_CONNECTED", "已连接 CARLA")

            self._emit_event(
                run_id,
                "TRAFFIC_MANAGER_CONNECTING",
                "正在等待 Traffic Manager 就绪",
                payload={"traffic_manager_port": self._settings.traffic_manager_port},
            )
            client.connect_traffic_manager(
                startup_timeout_seconds=max(
                    self._settings.carla_timeout_seconds,
                    15.0,
                )
            )
            client.apply_traffic_seed(getattr(descriptor.traffic, "seed", None))
            self._emit_event(run_id, "TRAFFIC_MANAGER_READY", "Traffic Manager 已就绪")

            self._emit_event(
                run_id,
                "MAP_LOADING",
                "正在加载目标地图",
                payload={"requested_map_name": plan.map_name or descriptor.map_name},
            )
            resolved_map_name = client.load_map(plan.map_name or descriptor.map_name)
            self._emit_event(
                run_id,
                "MAP_LOADED",
                "地图加载完成",
                payload={
                    "requested_map_name": plan.map_name or descriptor.map_name,
                    "resolved_map_name": resolved_map_name,
                },
            )

            self._emit_event(
                run_id,
                "WEATHER_APPLYING",
                "正在应用场景天气参数",
                payload={"preset": descriptor.weather.preset},
            )
            client.set_weather(
                descriptor.weather.preset,
                overrides=descriptor.weather.to_runtime_payload(),
            )
            self._emit_event(
                run_id,
                "WORLD_CONFIGURING",
                "正在应用 world 同步配置",
                payload={"sync_enabled": descriptor.sync.enabled},
            )
            client.configure_world_sync(descriptor.sync.enabled, descriptor.sync.fixed_delta_seconds)
            if descriptor.sync.enabled:
                client.configure_tm_sync(True)
                self._emit_event(
                    run_id,
                    "WORLD_SYNC_ENABLED",
                    "World 已按 native runtime 配置同步模式",
                    payload={"fixed_delta_seconds": descriptor.sync.fixed_delta_seconds},
                )
            else:
                self._emit_event(
                    run_id,
                    "WORLD_ASYNC_ENABLED",
                    "World 保持异步运行，native runtime 只监听 tick",
                    payload={"fixed_delta_seconds": descriptor.sync.fixed_delta_seconds},
                )

            self._emit_event(run_id, "PLAN_ENTITIES_SPAWNING", "正在生成场景实体")
            actors = self._spawn_plan_entities(run_id, client, descriptor, plan)
            hero_actor = next(
                (
                    actor
                    for entity_ref, actor in actors.items()
                    if self._entity_role_name(plan, entity_ref) == "hero"
                ),
                None,
            )
            if hero_actor is None:
                raise RuntimeError("native runtime 未能生成 hero actor")

            self._apply_entity_init_actions(run_id, client, actors, plan)
            background_actor_count = self._spawn_background_traffic(
                run_id,
                client,
                descriptor,
                hero_actor,
            )

            recorder_manager, recorder_client = self._start_simulation_recorder(
                run_id,
                descriptor,
            )
            sensor_recorder, sensor_recording_result = self._start_sensor_recording_if_requested(
                run_id,
                descriptor,
            )

            self._transition(run_id, RunStatus.RUNNING, set_started_at=True)
            self._emit_event(
                run_id,
                "SCENARIO_STARTED",
                "native runtime 场景执行开始",
                payload={
                    "launch_mode": str((run.scenario_source or {}).get("launch_mode") or ""),
                    "execution_backend": run.execution_backend,
                    "background_actor_count": background_actor_count,
                    "sensor_recording_started": sensor_recording_result is not None,
                },
            )

            viewer_friendly_sleep = (
                max(0.0, min(descriptor.sync.fixed_delta_seconds * 0.5, 0.05))
                if bool(descriptor.debug.viewer_friendly)
                else 0.0
            )
            traveled_distances: dict[str, float] = {entity_ref: 0.0 for entity_ref in actors}
            last_positions: dict[str, Any] = {
                entity_ref: self._actor_location(actor) for entity_ref, actor in actors.items()
            }
            fired_events: set[str] = set()

            while True:
                latest = self._run_store.get(run_id)
                if latest.stop_requested or latest.cancel_requested:
                    self._transition(run_id, RunStatus.STOPPING)
                    self._emit_event(run_id, "RUN_STOPPING", "native runtime 收到停止请求")
                    break

                control_state = self._control_store.get(run_id)
                if control_state and control_state != last_environment_signature:
                    self._apply_environment_update(run_id, client, control_state)
                    last_environment_signature = control_state

                tick_result = self._wait_for_runtime_tick(client, descriptor)
                telemetry.on_tick(tick_result.frame, tick_result.sim_time)
                if scenario_start_sim_time is None:
                    scenario_start_sim_time = tick_result.sim_time
                scenario_elapsed_sim_time = max(
                    0.0,
                    float(tick_result.sim_time) - float(scenario_start_sim_time),
                )
                self._notify_running_heartbeat(run_id)
                self._update_traveled_distances(actors, traveled_distances, last_positions)
                self._fire_due_events(
                    run_id,
                    client,
                    plan,
                    actors,
                    scenario_elapsed_sim_time,
                    traveled_distances,
                    fired_events,
                )

                if self._trigger_satisfied(
                    plan.stop_trigger,
                    actors,
                    scenario_elapsed_sim_time,
                    traveled_distances,
                ):
                    self._emit_event(
                        run_id,
                        "SCENARIO_COMPLETED",
                        "场景触发停止条件，native runtime 正常结束",
                    )
                    break

                if viewer_friendly_sleep > 0.0:
                    time.sleep(viewer_friendly_sleep)

            latest = self._run_store.get(run_id)
            if latest.cancel_requested:
                final_status = RunStatus.CANCELED
            else:
                final_status = RunStatus.COMPLETED
        except Exception as exc:  # noqa: BLE001
            failure_reason = str(exc)
            final_status = RunStatus.FAILED
            logger.error("Run %s failed:\n%s", run_id, traceback.format_exc())
            self._emit_event(
                run_id,
                "RUN_FAILED",
                "native runtime 因异常失败",
                payload={"error": failure_reason},
                level=EventLevel.ERROR,
            )
        finally:
            self._emit_event(run_id, "CLEANUP_STARTED", "native runtime 开始清理资源")

            if sensor_recorder is not None:
                self._stop_sensor_recording(run_id, sensor_recorder)
            self._stop_simulation_recorder(run_id, recorder_manager, recorder_client)

            if client is not None:
                try:
                    spawned_actor_count = client.spawned_actor_count()
                    client.cleanup()
                except Exception as exc:  # noqa: BLE001
                    logger.warning("CARLA cleanup failed for run %s: %s", run_id, exc)

            try:
                run = self._run_store.get(run_id)
                self._hil_runtime_orchestrator.stop_pipeline(
                    run_id,
                    run,
                    descriptor,
                    hil_started_steps,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("HIL pipeline cleanup failed for run %s: %s", run_id, exc)

            self._emit_event(run_id, "CLEANUP_FINISHED", "native runtime 资源清理完成")

            metrics = telemetry.finalize(
                final_status=final_status,
                failure_reason=failure_reason,
                spawned_actors_count=spawned_actor_count,
            )
            self._artifact_store.write_metrics(metrics)

            run_after = self._run_store.get(run_id)
            if run_after.status in {
                RunStatus.COMPLETED,
                RunStatus.CANCELED,
                RunStatus.FAILED,
            }:
                self._artifact_store.write_status(run_after)
            elif final_status == RunStatus.FAILED:
                self._transition(
                    run_id,
                    RunStatus.FAILED,
                    error_reason=failure_reason,
                    set_ended_at=True,
                )
            else:
                self._transition(run_id, final_status, set_ended_at=True)

    def _resolve_plan(self, run: Any, descriptor: Any) -> NativeScenarioPlan:
        scenario_source = run.scenario_source or {}
        launch_mode = str(scenario_source.get("launch_mode") or "native_descriptor").strip()
        if launch_mode == "openscenario":
            xosc_path = self._resolve_runtime_xosc_path(scenario_source)
            return load_native_xosc_plan(
                xosc_path,
                fallback_timeout_seconds=int(descriptor.termination.timeout_seconds),
            )

        target_speed_mps = self._resolve_target_speed_mps(scenario_source)
        return build_native_descriptor_plan(
            descriptor,
            target_speed_mps=target_speed_mps,
        )

    def _resolve_target_speed_mps(self, scenario_source: dict[str, Any]) -> float | None:
        template_params = scenario_source.get("template_params")
        if not isinstance(template_params, dict):
            return None
        raw_value = template_params.get("targetSpeedMps")
        if raw_value is None:
            return None
        return float(raw_value)

    def _resolve_runtime_xosc_path(self, scenario_source: dict[str, Any]) -> Path:
        for key in ("generated_xosc_path", "resolved_xosc_path", "xosc_path"):
            candidate = str(scenario_source.get(key) or "").strip()
            if candidate:
                path = Path(candidate)
                if path.exists():
                    return path
        raise RuntimeError("native runtime 缺少可读取的 OpenSCENARIO 文件")

    def _spawn_plan_entities(
        self,
        run_id: str,
        client: CarlaClient,
        descriptor: Any,
        plan: NativeScenarioPlan,
    ) -> dict[str, Any]:
        actors: dict[str, Any] = {}
        entities = sorted(
            plan.entities,
            key=lambda item: (not item.is_ego, item.entity_ref),
        )
        fallback_hero_spawn = descriptor.ego_vehicle.spawn_point.model_dump(mode="python")

        for entity in entities:
            spawn_point = entity.spawn_point or (fallback_hero_spawn if entity.is_ego else None)
            if spawn_point is None:
                self._emit_event(
                    run_id,
                    "NATIVE_ENTITY_SKIPPED",
                    f"实体 {entity.entity_ref} 缺少可解析出生点，已跳过",
                    level=EventLevel.WARNING,
                )
                continue

            if entity.is_ego:
                spawn_result = client.spawn_ego_vehicle(
                    entity.blueprint,
                    spawn_point,
                    role_name=entity.role_name,
                )
                actor = spawn_result.actor
                self._emit_event(
                    run_id,
                    "EGO_SPAWNED",
                    "hero 车辆生成成功",
                    payload={
                        "entity_ref": entity.entity_ref,
                        "actor_id": int(actor.id),
                        "role_name": entity.role_name,
                        "blueprint": entity.blueprint,
                        "spawn_source": spawn_result.source,
                        "requested_spawn_point": spawn_result.requested_spawn_point,
                        "resolved_spawn_point": spawn_result.resolved_spawn_point,
                    },
                )
            else:
                actor = client.spawn_actor(
                    entity.blueprint,
                    spawn_point,
                    role_name=entity.role_name,
                    actor_kind=entity.actor_kind,
                )
                self._emit_event(
                    run_id,
                    "SCENARIO_ENTITY_SPAWNED",
                    f"实体 {entity.entity_ref} 生成成功",
                    payload={
                        "entity_ref": entity.entity_ref,
                        "actor_id": int(actor.id),
                        "role_name": entity.role_name,
                        "actor_kind": entity.actor_kind,
                        "blueprint": entity.blueprint,
                        "spawn_point": spawn_point,
                    },
                )
            actors[entity.entity_ref] = actor

        return actors

    def _apply_entity_init_actions(
        self,
        run_id: str,
        client: CarlaClient,
        actors: dict[str, Any],
        plan: NativeScenarioPlan,
    ) -> None:
        for entity in plan.entities:
            actor = actors.get(entity.entity_ref)
            if actor is None:
                continue
            for action in entity.init_actions:
                self._apply_action(run_id, client, action, actors, event_name="init")

    def _spawn_background_traffic(
        self,
        run_id: str,
        client: CarlaClient,
        descriptor: Any,
        hero_actor: Any,
    ) -> int:
        requested_vehicle_count = max(0, int(descriptor.traffic.num_vehicles))
        requested_walker_count = max(0, int(descriptor.traffic.num_walkers))
        if requested_vehicle_count == 0 and requested_walker_count == 0:
            return 0

        anchor_spawn_point = client.actor_transform_to_dict(hero_actor)
        anchor_location = self._actor_location(hero_actor)
        spawned_vehicle_count = len(
            client.spawn_traffic_vehicles(
                requested_vehicle_count,
                autopilot=True,
                seed=getattr(descriptor.traffic, "seed", None),
                anchor_spawn_point=anchor_spawn_point,
            )
        )
        spawned_walker_count = len(
            client.spawn_traffic_walkers(
                requested_walker_count,
                seed=(
                    getattr(descriptor.traffic, "seed", None) + 1
                    if getattr(descriptor.traffic, "seed", None) is not None
                    else None
                ),
                anchor_location=anchor_location,
                max_radius_m=80.0,
            )
        )
        self._emit_event(
            run_id,
            "BACKGROUND_TRAFFIC_READY",
            "native runtime 已注入背景交通参与者",
            payload={
                "requested_vehicle_count": requested_vehicle_count,
                "spawned_vehicle_count": spawned_vehicle_count,
                "requested_walker_count": requested_walker_count,
                "spawned_walker_count": spawned_walker_count,
            },
        )
        return spawned_vehicle_count + spawned_walker_count

    def _fire_due_events(
        self,
        run_id: str,
        client: CarlaClient,
        plan: NativeScenarioPlan,
        actors: dict[str, Any],
        sim_time: float,
        traveled_distances: dict[str, float],
        fired_events: set[str],
    ) -> None:
        for event in plan.events:
            if event.name in fired_events:
                continue
            if not self._trigger_satisfied(
                event.start_trigger,
                actors,
                sim_time,
                traveled_distances,
                default_actor_refs=event.actor_refs,
            ):
                continue

            for action in event.actions:
                self._apply_action(run_id, client, action, actors, event_name=event.name)
            fired_events.add(event.name)
            self._emit_event(
                run_id,
                "NATIVE_EVENT_FIRED",
                f"事件 {event.name} 已触发",
                payload={"event_name": event.name, "actor_refs": list(event.actor_refs)},
            )

    def _apply_action(
        self,
        run_id: str,
        client: CarlaClient,
        action: NativeEntityAction,
        actors: dict[str, Any],
        *,
        event_name: str,
    ) -> None:
        actor = actors.get(action.entity_ref)
        if actor is None:
            self._emit_event(
                run_id,
                "NATIVE_ACTION_SKIPPED",
                f"动作目标实体不存在: {action.entity_ref}",
                payload={"event_name": event_name},
                level=EventLevel.WARNING,
            )
            return

        if action.kind in {"autopilot", "keep_velocity"}:
            client.configure_tm_autopilot(
                actor,
                enabled=True if action.enabled is None else bool(action.enabled),
                target_speed_mps=action.target_speed_mps,
                auto_lane_change=action.auto_lane_change,
                distance_between_vehicles=action.distance_between_vehicles,
                ignore_vehicles_percentage=action.ignore_vehicles_percentage,
            )
            self._emit_event(
                run_id,
                "NATIVE_ACTION_APPLIED",
                f"{event_name} -> {action.entity_ref} 已应用 {action.kind}",
                payload={
                    "event_name": event_name,
                    "entity_ref": action.entity_ref,
                    "action_kind": action.kind,
                    "target_speed_mps": action.target_speed_mps,
                },
            )
            return

        self._emit_event(
            run_id,
            "NATIVE_ACTION_SKIPPED",
            f"native runtime 暂不支持动作类型 {action.kind}",
            payload={"event_name": event_name, "entity_ref": action.entity_ref},
            level=EventLevel.WARNING,
        )

    def _wait_for_runtime_tick(self, client: CarlaClient, descriptor: Any) -> CarlaTickResult:
        if descriptor.sync.enabled:
            return client.tick()
        return client.wait_for_tick(
            timeout_seconds=max(0.2, min(float(self._settings.carla_timeout_seconds), 2.0))
        )

    def _update_traveled_distances(
        self,
        actors: dict[str, Any],
        traveled_distances: dict[str, float],
        last_positions: dict[str, Any],
    ) -> None:
        for entity_ref, actor in actors.items():
            current = self._actor_location(actor)
            previous = last_positions.get(entity_ref)
            if current is not None and previous is not None and hasattr(current, "distance"):
                traveled_distances[entity_ref] = traveled_distances.get(entity_ref, 0.0) + float(
                    current.distance(previous)
                )
            last_positions[entity_ref] = current

    def _trigger_satisfied(
        self,
        trigger: NativeTrigger,
        actors: dict[str, Any],
        sim_time: float,
        traveled_distances: dict[str, float],
        *,
        default_actor_refs: tuple[str, ...] = (),
    ) -> bool:
        if trigger.is_empty:
            return False
        return any(
            all(
                self._condition_satisfied(
                    condition,
                    actors,
                    sim_time,
                    traveled_distances,
                    default_actor_refs=default_actor_refs,
                )
                for condition in group
            )
            for group in trigger.condition_groups
        )

    def _condition_satisfied(
        self,
        condition: NativeCondition,
        actors: dict[str, Any],
        sim_time: float,
        traveled_distances: dict[str, float],
        *,
        default_actor_refs: tuple[str, ...] = (),
    ) -> bool:
        if condition.kind == "simulation_time":
            return self._compare(sim_time, condition.value, condition.rule)

        actor_refs = condition.triggering_entity_refs or default_actor_refs
        if not actor_refs:
            return False

        results: list[bool] = []
        for actor_ref in actor_refs:
            actor = actors.get(actor_ref)
            if actor is None:
                continue

            if condition.kind == "traveled_distance":
                actual_value = traveled_distances.get(actor_ref, 0.0)
                results.append(self._compare(actual_value, condition.value, condition.rule))
                continue

            if condition.kind == "relative_distance":
                target_actor = actors.get(condition.target_entity_ref or "")
                if target_actor is None:
                    continue
                actor_location = self._actor_location(actor)
                target_location = self._actor_location(target_actor)
                if actor_location is None or target_location is None:
                    continue
                actual_value = float(actor_location.distance(target_location))
                results.append(self._compare(actual_value, condition.value, condition.rule))

        if not results:
            return False
        if condition.triggering_entities_rule == "all":
            return all(results)
        return any(results)

    @staticmethod
    def _compare(actual: float, expected: float, rule: str) -> bool:
        normalized = (rule or "greaterThan").strip()
        if normalized == "lessThan":
            return actual < expected
        if normalized == "lessOrEqual":
            return actual <= expected
        if normalized == "equalTo":
            return abs(actual - expected) <= 1e-6
        if normalized == "greaterOrEqual":
            return actual >= expected
        return actual > expected

    @staticmethod
    def _actor_location(actor: Any) -> Any | None:
        get_location = getattr(actor, "get_location", None)
        if callable(get_location):
            return get_location()
        get_transform = getattr(actor, "get_transform", None)
        if callable(get_transform):
            transform = get_transform()
            return getattr(transform, "location", None)
        return None

    def _apply_environment_update(
        self,
        run_id: str,
        carla_client: CarlaClient,
        environment_state: dict[str, Any],
    ) -> bool:
        weather_payload = environment_state.get("weather")
        if not isinstance(weather_payload, dict):
            return False

        preset_name = str(weather_payload.get("preset", "")).strip()
        if not preset_name:
            return False

        carla_client.set_weather(preset_name, overrides=weather_payload)
        self._emit_event(
            run_id,
            "ENVIRONMENT_UPDATED",
            "运行环境参数已更新",
            payload=environment_state,
        )
        return True

    def _initialize_runtime_control(self, run_id: str, descriptor: Any) -> None:
        descriptor_payload = descriptor.to_dict() if hasattr(descriptor, "to_dict") else {}
        self._control_store.update(
            run_id,
            {
                "sensor_capture": build_default_sensor_capture_control(
                    descriptor_payload,
                    output_root=self._artifact_store.run_dir(run_id) / "outputs" / "sensors",
                ),
                "recorder": build_default_recorder_control(
                    run_id,
                    descriptor_payload,
                    recorder_path=self._artifact_store.run_dir(run_id)
                    / "recorder"
                    / f"{run_id}.log",
                ),
            },
        )

    def _start_sensor_recording_if_requested(
        self,
        run_id: str,
        descriptor: Any,
    ) -> tuple[SensorRecorderProcess | None, SensorRecorderResult | None]:
        if not getattr(descriptor.sensors, "enabled", False) or not descriptor.sensors.sensors:
            return None, None
        if not bool(getattr(descriptor.sensors, "auto_start", False)):
            return None, None

        self._control_store.update(
            run_id,
            {
                "sensor_capture": {
                    "status": SENSOR_CAPTURE_STATUS_STARTING,
                    "active": False,
                    "last_error": None,
                }
            },
        )
        recorder = SensorRecorderProcess(
            host=self._settings.carla_host,
            port=self._settings.carla_port,
            timeout_seconds=self._settings.carla_timeout_seconds,
            output_root=self._artifact_store.run_dir(run_id) / "outputs" / "sensors",
        )
        try:
            result = recorder.start(descriptor)
        except Exception as exc:  # noqa: BLE001
            self._control_store.update(
                run_id,
                {
                    "sensor_capture": {
                        "status": SENSOR_CAPTURE_STATUS_ERROR,
                        "active": False,
                        "last_error": str(exc),
                    }
                },
            )
            self._emit_event(
                run_id,
                "SENSOR_RECORDING_FAILED",
                "native runtime 传感器采集启动失败",
                payload={"error": str(exc)},
                level=EventLevel.WARNING,
            )
            return None, None

        self._control_store.update(
            run_id,
            {
                "sensor_capture": {
                    "status": SENSOR_CAPTURE_STATUS_RUNNING,
                    "active": True,
                    "last_error": None,
                }
            },
        )
        self._emit_event(
            run_id,
            "SENSOR_RECORDING_READY",
            "native runtime 传感器采集已开始",
            payload={
                "profile_name": result.profile_name,
                "sensor_count": result.sensor_count,
                "output_root": str(result.output_root),
            },
        )
        return recorder, result

    def _stop_sensor_recording(
        self,
        run_id: str,
        sensor_recorder: SensorRecorderProcess,
    ) -> None:
        try:
            sensor_recorder.stop()
        except Exception as exc:  # noqa: BLE001
            self._control_store.update(
                run_id,
                {
                    "sensor_capture": {
                        "status": SENSOR_CAPTURE_STATUS_ERROR,
                        "active": False,
                        "last_error": str(exc),
                    }
                },
            )
            return

        self._control_store.update(
            run_id,
            {
                "sensor_capture": {
                    "status": SENSOR_CAPTURE_STATUS_STOPPED,
                    "active": False,
                    "last_error": None,
                }
            },
        )

    def _start_simulation_recorder(
        self,
        run_id: str,
        descriptor: Any,
    ) -> tuple[RecorderManager | None, CarlaClient | None]:
        if not getattr(descriptor.recorder, "enabled", False):
            return None, None

        self._control_store.update(
            run_id,
            {
                "recorder": {
                    "status": RECORDER_STATUS_STARTING,
                    "active": False,
                    "last_error": None,
                }
            },
        )
        recorder_client = self._client_factory(
            self._settings.carla_host,
            self._settings.carla_port,
            self._settings.carla_timeout_seconds,
            self._settings.traffic_manager_port,
        )
        recorder = RecorderManager()
        try:
            recorder_client.connect(connect_traffic_manager=False)
            recorder.start(
                run_id,
                descriptor,
                recorder_client,
                self._artifact_store.run_dir(run_id),
            )
        except Exception as exc:  # noqa: BLE001
            self._control_store.update(
                run_id,
                {
                    "recorder": {
                        "status": RECORDER_STATUS_ERROR,
                        "active": False,
                        "last_error": str(exc),
                    }
                },
            )
            self._emit_event(
                run_id,
                "SIMULATION_RECORDER_FAILED",
                "CARLA recorder 启动失败，run 将继续执行",
                payload={"error": str(exc)},
                level=EventLevel.WARNING,
            )
            recorder_client.cleanup()
            return None, None

        self._control_store.update(
            run_id,
            {
                "recorder": {
                    "status": RECORDER_STATUS_RUNNING,
                    "active": True,
                    "output_path": (
                        str(recorder.output_path) if recorder.output_path is not None else None
                    ),
                    "last_error": None,
                }
            },
        )
        return recorder, recorder_client

    def _stop_simulation_recorder(
        self,
        run_id: str,
        recorder: RecorderManager | None,
        recorder_client: CarlaClient | None,
    ) -> None:
        if recorder is None or recorder_client is None:
            return
        try:
            recorder.stop(recorder_client)
            self._control_store.update(
                run_id,
                {
                    "recorder": {
                        "status": RECORDER_STATUS_STOPPED,
                        "active": False,
                        "last_error": None,
                    }
                },
            )
        except Exception as exc:  # noqa: BLE001
            self._control_store.update(
                run_id,
                {
                    "recorder": {
                        "status": RECORDER_STATUS_ERROR,
                        "active": False,
                        "last_error": str(exc),
                    }
                },
            )
        finally:
            recorder_client.cleanup()

    def _entity_role_name(self, plan: NativeScenarioPlan, entity_ref: str) -> str:
        for entity in plan.entities:
            if entity.entity_ref == entity_ref:
                return entity.role_name
        return entity_ref

    def _emit_event(
        self,
        run_id: str,
        event_type: str,
        message: str,
        payload: dict[str, Any] | None = None,
        level: EventLevel = EventLevel.INFO,
    ) -> None:
        event = RunEvent(
            timestamp=now_utc(),
            run_id=run_id,
            level=level,
            event_type=event_type,
            message=message,
            payload=payload or {},
        )
        self._artifact_store.append_event(event)
        self._artifact_store.append_run_log(
            run_id,
            f"[{event.timestamp.isoformat()}] {event.level.value} {event.event_type} {event.message}",
        )

    def _transition(
        self,
        run_id: str,
        target: RunStatus,
        error_reason: str | None = None,
        set_started_at: bool = False,
        set_ended_at: bool = False,
    ) -> None:
        run = self._run_store.transition(
            run_id,
            target,
            error_reason=error_reason,
            set_started_at=set_started_at,
            set_ended_at=set_ended_at,
        )
        self._artifact_store.write_status(run)

    def _notify_running_heartbeat(self, run_id: str) -> None:
        if self._heartbeat_callback is not None:
            self._heartbeat_callback(run_id)
