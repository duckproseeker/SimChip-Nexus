from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from xml.etree import ElementTree


@dataclass(frozen=True)
class NativeCondition:
    kind: str
    value: float
    rule: str = "greaterThan"
    entity_ref: str | None = None
    target_entity_ref: str | None = None
    triggering_entity_refs: tuple[str, ...] = ()
    triggering_entities_rule: str = "any"
    relative_distance_type: str | None = None


@dataclass(frozen=True)
class NativeTrigger:
    condition_groups: tuple[tuple[NativeCondition, ...], ...] = ()

    @property
    def is_empty(self) -> bool:
        return not self.condition_groups


@dataclass(frozen=True)
class NativeEntityAction:
    kind: str
    entity_ref: str
    target_speed_mps: float | None = None
    enabled: bool | None = None
    auto_lane_change: bool | None = None
    distance_between_vehicles: float | None = None
    ignore_vehicles_percentage: float | None = None


@dataclass(frozen=True)
class NativeScenarioEntity:
    entity_ref: str
    actor_kind: str
    blueprint: str
    role_name: str
    spawn_point: dict[str, float] | None = None
    is_ego: bool = False
    init_actions: tuple[NativeEntityAction, ...] = ()


@dataclass(frozen=True)
class NativeScenarioEvent:
    name: str
    actor_refs: tuple[str, ...]
    start_trigger: NativeTrigger
    actions: tuple[NativeEntityAction, ...]


@dataclass(frozen=True)
class NativeScenarioPlan:
    map_name: str
    weather: dict[str, Any] | None = None
    entities: tuple[NativeScenarioEntity, ...] = ()
    events: tuple[NativeScenarioEvent, ...] = ()
    stop_trigger: NativeTrigger = field(default_factory=NativeTrigger)
    warnings: tuple[str, ...] = ()


def build_native_descriptor_plan(
    descriptor: Any,
    *,
    target_speed_mps: float | None = None,
) -> NativeScenarioPlan:
    spawn_point = descriptor.ego_vehicle.spawn_point.model_dump(mode="python")
    init_actions: list[NativeEntityAction] = [
        NativeEntityAction(
            kind="autopilot",
            entity_ref="hero",
            enabled=True,
            target_speed_mps=target_speed_mps,
            auto_lane_change=True,
            distance_between_vehicles=3.0,
            ignore_vehicles_percentage=0.0,
        )
    ]
    success_condition = str(getattr(descriptor.termination, "success_condition", "") or "").strip()
    normalized_success_condition = success_condition.lower()
    stop_trigger = NativeTrigger()
    if normalized_success_condition not in {"manual_stop", "manual_stop_only", "user_stop"}:
        timeout_seconds = float(descriptor.termination.timeout_seconds)
        stop_trigger = NativeTrigger(
            condition_groups=(
                (
                    NativeCondition(
                        kind="simulation_time",
                        value=timeout_seconds,
                        rule="greaterThan",
                    ),
                ),
            )
        )
    return NativeScenarioPlan(
        map_name=str(descriptor.map_name),
        weather=descriptor.weather.to_runtime_payload(),
        entities=(
            NativeScenarioEntity(
                entity_ref="hero",
                actor_kind="vehicle",
                blueprint=str(descriptor.ego_vehicle.blueprint),
                role_name="hero",
                spawn_point=spawn_point,
                is_ego=True,
                init_actions=tuple(init_actions),
            ),
        ),
        stop_trigger=stop_trigger,
    )


def load_native_xosc_plan(
    xosc_path: Path,
    *,
    fallback_timeout_seconds: int | None = None,
) -> NativeScenarioPlan:
    root = ElementTree.parse(xosc_path).getroot()
    warnings: list[str] = []

    entity_index = _parse_entities(root, warnings)
    _apply_init_actions(root, entity_index, warnings)
    events = _parse_events(root, warnings)
    stop_trigger = _parse_stop_trigger(root, warnings)
    if stop_trigger.is_empty and fallback_timeout_seconds is not None:
        stop_trigger = NativeTrigger(
            condition_groups=(
                (
                    NativeCondition(
                        kind="simulation_time",
                        value=float(fallback_timeout_seconds),
                        rule="greaterThan",
                    ),
                ),
            )
        )

    return NativeScenarioPlan(
        map_name=_extract_map_name(root),
        weather=_extract_weather(root),
        entities=tuple(entity_index.values()),
        events=tuple(events),
        stop_trigger=stop_trigger,
        warnings=tuple(warnings),
    )


def _parse_entities(
    root: ElementTree.Element,
    warnings: list[str],
) -> dict[str, NativeScenarioEntity]:
    entity_index: dict[str, NativeScenarioEntity] = {}
    for scenario_object in root.findall("./Entities/ScenarioObject"):
        entity_ref = str(scenario_object.attrib.get("name") or "").strip()
        if not entity_ref:
            continue

        actor_kind = "vehicle"
        blueprint = "vehicle.lincoln.mkz_2017"
        child = next(iter(list(scenario_object)), None)
        if child is not None:
            if child.tag == "Vehicle":
                actor_kind = "vehicle"
                blueprint = str(child.attrib.get("name") or blueprint).strip() or blueprint
            elif child.tag == "Pedestrian":
                actor_kind = "walker"
                blueprint = (
                    str(child.attrib.get("name") or "walker.pedestrian.0001").strip()
                    or "walker.pedestrian.0001"
                )
            elif child.tag == "MiscObject":
                actor_kind = "misc"
                blueprint = (
                    str(child.attrib.get("name") or "static.prop.streetbarrier").strip()
                    or "static.prop.streetbarrier"
                )
            elif child.tag == "CatalogReference":
                catalog_name = str(child.attrib.get("catalogName") or "").strip()
                entry_name = str(child.attrib.get("entryName") or "").strip()
                if "pedestrian" in catalog_name.lower():
                    actor_kind = "walker"
                    blueprint = entry_name or "walker.pedestrian.0001"
                elif "misc" in catalog_name.lower():
                    actor_kind = "misc"
                    blueprint = entry_name or "static.prop.streetbarrier"
                else:
                    actor_kind = "vehicle"
                    blueprint = entry_name or blueprint
            else:
                warnings.append(f"未识别的 ScenarioObject 子节点: {child.tag}")

        role_name = "hero" if entity_ref.lower() in {"hero", "ego", "ego_vehicle"} else entity_ref
        entity_index[entity_ref] = NativeScenarioEntity(
            entity_ref=entity_ref,
            actor_kind=actor_kind,
            blueprint=blueprint,
            role_name=role_name,
            is_ego=role_name == "hero",
        )
    return entity_index


def _apply_init_actions(
    root: ElementTree.Element,
    entity_index: dict[str, NativeScenarioEntity],
    warnings: list[str],
) -> None:
    actions_root = root.find("./Storyboard/Init/Actions")
    if actions_root is None:
        return

    for private in actions_root.findall("./Private"):
        entity_ref = str(private.attrib.get("entityRef") or "").strip()
        if not entity_ref or entity_ref not in entity_index:
            continue

        entity = entity_index[entity_ref]
        init_actions = list(entity.init_actions)
        spawn_point = entity.spawn_point

        teleport = private.find("./PrivateAction/TeleportAction/Position/WorldPosition")
        if teleport is not None:
            parsed_spawn = _parse_world_position(teleport)
            if parsed_spawn is not None:
                spawn_point = parsed_spawn

        controller_properties = _extract_controller_properties(private)
        if controller_properties:
            init_actions.append(_build_autopilot_action(entity_ref, controller_properties))

        speed_value = _extract_speed_action_target(private)
        if speed_value is not None:
            init_actions.append(
                NativeEntityAction(
                    kind="keep_velocity",
                    entity_ref=entity_ref,
                    target_speed_mps=speed_value,
                )
            )

        entity_index[entity_ref] = NativeScenarioEntity(
            entity_ref=entity.entity_ref,
            actor_kind=entity.actor_kind,
            blueprint=entity.blueprint,
            role_name=entity.role_name,
            spawn_point=spawn_point,
            is_ego=entity.is_ego,
            init_actions=tuple(init_actions),
        )


def _parse_events(
    root: ElementTree.Element,
    warnings: list[str],
) -> list[NativeScenarioEvent]:
    events: list[NativeScenarioEvent] = []
    for act in root.findall("./Storyboard/Story/Act"):
        for maneuver_group in act.findall("./ManeuverGroup"):
            actor_refs = tuple(
                str(item.attrib.get("entityRef") or "").strip()
                for item in maneuver_group.findall("./Actors/EntityRef")
                if str(item.attrib.get("entityRef") or "").strip()
            )
            for event in maneuver_group.findall(".//Event"):
                action_items: list[NativeEntityAction] = []
                controller_properties = _extract_controller_properties(event)
                if controller_properties:
                    for entity_ref in actor_refs:
                        action_items.append(
                            _build_autopilot_action(entity_ref, controller_properties)
                        )

                speed_value = _extract_speed_action_target(event)
                if speed_value is not None:
                    for entity_ref in actor_refs:
                        action_items.append(
                            NativeEntityAction(
                                kind="keep_velocity",
                                entity_ref=entity_ref,
                                target_speed_mps=speed_value,
                            )
                        )

                if not action_items:
                    warnings.append(
                        "原生 runtime 忽略了不受支持的 Event Action: "
                        f"{event.attrib.get('name', 'unnamed_event')}"
                    )
                    continue

                events.append(
                    NativeScenarioEvent(
                        name=str(event.attrib.get("name") or "event").strip() or "event",
                        actor_refs=actor_refs,
                        start_trigger=_parse_trigger(event.find("./StartTrigger"), warnings),
                        actions=tuple(action_items),
                    )
                )
    return events


def _parse_stop_trigger(
    root: ElementTree.Element,
    warnings: list[str],
) -> NativeTrigger:
    act = root.find("./Storyboard/Story/Act")
    if act is None:
        return NativeTrigger()
    return _parse_trigger(act.find("./StopTrigger"), warnings)


def _parse_trigger(
    trigger: ElementTree.Element | None,
    warnings: list[str],
) -> NativeTrigger:
    if trigger is None:
        return NativeTrigger()

    condition_groups: list[tuple[NativeCondition, ...]] = []
    for group in trigger.findall("./ConditionGroup"):
        conditions: list[NativeCondition] = []
        for condition in group.findall("./Condition"):
            parsed = _parse_condition(condition)
            if parsed is None:
                warnings.append(
                    "原生 runtime 忽略了不受支持的 Condition: "
                    f"{condition.attrib.get('name', 'unnamed_condition')}"
                )
                continue
            conditions.append(parsed)
        if conditions:
            condition_groups.append(tuple(conditions))
    return NativeTrigger(condition_groups=tuple(condition_groups))


def _parse_condition(condition: ElementTree.Element) -> NativeCondition | None:
    simulation_time = condition.find("./ByValueCondition/SimulationTimeCondition")
    if simulation_time is not None:
        return NativeCondition(
            kind="simulation_time",
            value=_parse_float(simulation_time.attrib.get("value"), default=0.0),
            rule=str(simulation_time.attrib.get("rule") or "greaterThan"),
        )

    by_entity = condition.find("./ByEntityCondition")
    if by_entity is None:
        return None

    triggering_entities = tuple(
        str(item.attrib.get("entityRef") or "").strip()
        for item in by_entity.findall("./TriggeringEntities/EntityRef")
        if str(item.attrib.get("entityRef") or "").strip()
    )
    triggering_rule = str(
        by_entity.find("./TriggeringEntities").attrib.get("triggeringEntitiesRule")
        if by_entity.find("./TriggeringEntities") is not None
        else "any"
    )

    relative_distance = by_entity.find("./EntityCondition/RelativeDistanceCondition")
    if relative_distance is not None:
        return NativeCondition(
            kind="relative_distance",
            value=_parse_float(relative_distance.attrib.get("value"), default=0.0),
            rule=str(relative_distance.attrib.get("rule") or "lessThan"),
            target_entity_ref=str(relative_distance.attrib.get("entityRef") or "").strip() or None,
            triggering_entity_refs=triggering_entities,
            triggering_entities_rule=triggering_rule or "any",
            relative_distance_type=(
                str(relative_distance.attrib.get("relativeDistanceType") or "").strip() or None
            ),
        )

    traveled_distance = by_entity.find("./EntityCondition/TraveledDistanceCondition")
    if traveled_distance is not None:
        return NativeCondition(
            kind="traveled_distance",
            value=_parse_float(traveled_distance.attrib.get("value"), default=0.0),
            rule="greaterThan",
            triggering_entity_refs=triggering_entities,
            triggering_entities_rule=triggering_rule or "any",
        )

    return None


def _extract_map_name(root: ElementTree.Element) -> str:
    logic_file = root.find("./RoadNetwork/LogicFile")
    if logic_file is None:
        return "Town01"
    return str(logic_file.attrib.get("filepath") or "").strip() or "Town01"


def _extract_weather(root: ElementTree.Element) -> dict[str, Any] | None:
    environment = root.find("./Storyboard/Init/Actions/GlobalAction/EnvironmentAction/Environment")
    if environment is None:
        return None

    weather_element = environment.find("./Weather")
    if weather_element is None:
        return None

    payload: dict[str, Any] = {}
    cloud_state = str(weather_element.attrib.get("cloudState") or "").strip().lower()
    if cloud_state == "overcast":
        payload["cloudiness"] = 90.0
    elif cloud_state == "cloudy":
        payload["cloudiness"] = 60.0
    elif cloud_state == "rainy":
        payload["cloudiness"] = 100.0
        payload["precipitation"] = 80.0

    sun = weather_element.find("./Sun")
    if sun is not None:
        payload["sun_azimuth_angle"] = _parse_float(sun.attrib.get("azimuth"), default=0.0)
        payload["sun_altitude_angle"] = _parse_float(
            sun.attrib.get("elevation"),
            default=0.0,
        )

    fog = weather_element.find("./Fog")
    if fog is not None and fog.attrib.get("visualRange"):
        visual_range = _parse_float(fog.attrib.get("visualRange"), default=100000.0)
        payload["fog_density"] = max(
            0.0,
            min(100.0, 100.0 * (1.0 - min(visual_range, 100000.0) / 100000.0)),
        )

    precipitation = weather_element.find("./Precipitation")
    if precipitation is not None:
        intensity = _parse_float(precipitation.attrib.get("intensity"), default=0.0)
        payload["precipitation"] = max(0.0, min(100.0, intensity * 100.0))

    return payload or None


def _extract_controller_properties(node: ElementTree.Element) -> dict[str, str]:
    properties = node.findall(
        ".//ControllerAction/AssignControllerAction/Controller/Properties/Property"
    )
    payload: dict[str, str] = {}
    for item in properties:
        name = str(item.attrib.get("name") or "").strip()
        value = str(item.attrib.get("value") or "").strip()
        if name and value:
            payload[name] = value
    return payload


def _build_autopilot_action(
    entity_ref: str,
    properties: dict[str, str],
) -> NativeEntityAction:
    enabled_value = properties.get("enabled")
    enabled = None if enabled_value is None else _parse_bool(enabled_value, default=True)
    return NativeEntityAction(
        kind="autopilot",
        entity_ref=entity_ref,
        enabled=True if enabled is None else enabled,
        target_speed_mps=_optional_float(properties.get("target_speed_mps")),
        auto_lane_change=_optional_bool(properties.get("auto_lane_change")),
        distance_between_vehicles=_optional_float(properties.get("distance_between_vehicles")),
        ignore_vehicles_percentage=_optional_float(properties.get("ignore_vehicles_percentage")),
    )


def _extract_speed_action_target(node: ElementTree.Element) -> float | None:
    absolute_target = node.find(
        ".//PrivateAction/LongitudinalAction/SpeedAction/SpeedActionTarget/AbsoluteTargetSpeed"
    )
    if absolute_target is None:
        return None
    return _optional_float(absolute_target.attrib.get("value"))


def _parse_world_position(position: ElementTree.Element) -> dict[str, float] | None:
    if position is None:
        return None
    return {
        "x": _parse_float(position.attrib.get("x"), default=0.0),
        "y": _parse_float(position.attrib.get("y"), default=0.0),
        "z": _parse_float(position.attrib.get("z"), default=0.5),
        "roll": _parse_float(position.attrib.get("r"), default=0.0),
        "pitch": _parse_float(position.attrib.get("p"), default=0.0),
        "yaw": _parse_float(position.attrib.get("h"), default=0.0),
    }


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    normalized = str(value).strip()
    if not normalized:
        return None
    if normalized.startswith("$"):
        normalized = normalized[1:]
    return float(normalized)


def _parse_float(value: Any, *, default: float) -> float:
    try:
        parsed = _optional_float(value)
    except ValueError:
        return default
    return default if parsed is None else parsed


def _optional_bool(value: Any) -> bool | None:
    if value is None:
        return None
    normalized = str(value).strip().lower()
    if not normalized:
        return None
    return normalized in {"1", "true", "yes", "on"}


def _parse_bool(value: Any, *, default: bool) -> bool:
    parsed = _optional_bool(value)
    return default if parsed is None else parsed
