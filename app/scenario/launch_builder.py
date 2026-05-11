from __future__ import annotations

import copy
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

from app.core.config import Settings
from app.scenario.environment_presets import list_environment_presets
from app.scenario.official_runner import resolve_official_xosc_path
from app.scenario.template_registry import ScenarioTemplateScalar, format_template_param_value
from app.utils.file_utils import atomic_write_json, ensure_dir


@dataclass(frozen=True)
class ScenarioLaunchArtifacts:
    build_dir: Path
    run_spec_path: Path
    xosc_path: Path | None = None
    config_path: Path | None = None
    additional_scenario_path: Path | None = None


def default_launch_weather() -> dict[str, Any]:
    for item in list_environment_presets():
        if item.get("preset_id") == "clear_noon":
            return copy.deepcopy(item["weather"])
    return {"preset": "ClearNoon", "sun_altitude_angle": 68.0}


def default_launch_capabilities(
    *,
    map_editable: bool = False,
    sensor_profile_editable: bool = False,
    timeout_editable: bool = True,
) -> dict[str, Any]:
    return {
        "map_editable": map_editable,
        "weather_editable": True,
        "traffic_vehicle_count_editable": True,
        "traffic_walker_count_editable": True,
        "sensor_profile_editable": sensor_profile_editable,
        "timeout_editable": timeout_editable,
        "max_vehicle_count": 48,
        "max_walker_count": 48,
        "notes": [
            "前端只暴露场景配置项，底层生成 per-run 运行输入并统一交给平台 native runtime。",
            "轻量 OpenSCENARIO 会翻译成平台受控子集执行，不保证完整还原所有标准语义。",
            "hero 默认走平台内置 TM 自动驾驶控制，预留手动接管模式但当前不启用。",
            "背景交通 seed 留空时会在创建 run 时自动生成，并回写到 per-run spec 里。",
        ],
    }


def build_launch_descriptor(
    catalog_item: dict[str, Any],
    *,
    map_name: str | None,
    weather: dict[str, Any] | None,
    traffic: dict[str, Any] | None,
    sensors: dict[str, Any] | None,
    timeout_seconds: int | None,
    metadata: dict[str, Any] | None,
) -> dict[str, Any]:
    descriptor = copy.deepcopy(catalog_item["descriptor_template"])
    descriptor["map_name"] = (map_name or descriptor.get("map_name") or "").strip()
    descriptor["weather"] = _resolve_launch_weather(descriptor.get("weather", {}), weather)
    descriptor["traffic"] = _resolve_launch_traffic(
        descriptor.get("traffic", {}),
        traffic,
    )
    descriptor["sensors"] = _resolve_launch_sensors(descriptor.get("sensors", {}), sensors)
    if timeout_seconds is not None:
        descriptor.setdefault("termination", {})["timeout_seconds"] = timeout_seconds
    descriptor["metadata"] = _resolve_launch_metadata(
        catalog_item, descriptor.get("metadata", {}), metadata
    )
    return descriptor


def write_launch_artifacts(
    *,
    settings: Settings,
    run_id: str,
    catalog_item: dict[str, Any],
    descriptor: dict[str, Any],
    launch_request: dict[str, Any],
    template_params: dict[str, ScenarioTemplateScalar],
) -> ScenarioLaunchArtifacts:
    build_dir = ensure_dir(settings.scenario_builds_root / run_id)
    run_spec_path = build_dir / "scenario_launch_spec.json"
    source = catalog_item.get("source", {})
    launch_mode = str(source.get("launch_mode") or "native_descriptor").strip() or "native_descriptor"

    xosc_path: Path | None = None
    config_path: Path | None = None
    additional_scenario_path: Path | None = None
    template_source_payload: dict[str, Any] = {}
    generated_source_payload: dict[str, Any] = {}

    if launch_mode == "python_scenario":
        config_path = build_dir / "generated_scenario_config.xml"
        additional_scenario_path = Path(str(source.get("additional_scenario_path") or "").strip())
        if not additional_scenario_path.exists():
            raise RuntimeError(f"找不到 Python Scenario 实现: {additional_scenario_path}")

        _write_generated_python_scenario_config(
            output_path=config_path,
            scenario_class=str(source.get("scenario_class") or "").strip(),
            settings=settings,
            descriptor=descriptor,
            template_params=template_params,
            additional_scenario_path=additional_scenario_path,
        )
        template_source_payload = {
            "scenario_class": source.get("scenario_class"),
            "additional_scenario_path": str(additional_scenario_path),
        }
        generated_source_payload = {
            "config_path": str(config_path),
        }
    elif launch_mode == "openscenario":
        xosc_path = build_dir / "generated_scenario.xosc"
        relative_xosc_path = str(source.get("relative_xosc_path") or "").strip()
        template_xosc_path = resolve_official_xosc_path(relative_xosc_path, settings)
        if template_xosc_path is None:
            raise RuntimeError(f"找不到官方 OpenSCENARIO 文件: {relative_xosc_path}")

        _write_generated_xosc(
            template_path=template_xosc_path,
            output_path=xosc_path,
            scenario_id=catalog_item["scenario_id"],
            settings=settings,
            map_name=str(descriptor["map_name"]),
            weather=descriptor.get("weather", {}),
            template_params=template_params,
            timeout_seconds=int(descriptor.get("termination", {}).get("timeout_seconds") or 30),
        )
        template_source_payload = {
            "relative_xosc_path": relative_xosc_path,
            "resolved_xosc_path": str(template_xosc_path),
        }
        generated_source_payload = {
            "xosc_path": str(xosc_path),
        }
    else:
        template_source_payload = {
            "scenario_id": catalog_item["scenario_id"],
            "provider": str(source.get("provider") or "native"),
        }

    atomic_write_json(
        run_spec_path,
        {
            "scenario_id": catalog_item["scenario_id"],
            "display_name": catalog_item["display_name"],
            "launch_mode": launch_mode,
            "launch_request": launch_request,
            "resolved_template_params": template_params,
            "descriptor": descriptor,
            "template_source": template_source_payload,
            "generated_source": generated_source_payload,
        },
    )
    return ScenarioLaunchArtifacts(
        build_dir=build_dir,
        run_spec_path=run_spec_path,
        xosc_path=xosc_path,
        config_path=config_path,
        additional_scenario_path=additional_scenario_path,
    )


def build_generated_scenario_source(
    catalog_item: dict[str, Any],
    artifacts: ScenarioLaunchArtifacts,
    template_params: dict[str, ScenarioTemplateScalar],
) -> dict[str, Any]:
    template_source = catalog_item.get("source", {})
    launch_mode = (
        str(template_source.get("launch_mode") or "native_descriptor").strip()
        or "native_descriptor"
    )
    payload = {
        "provider": str(template_source.get("provider") or "native"),
        "version": "generated",
        "generated_spec_path": str(artifacts.run_spec_path),
        "template_params": template_params,
        "launch_mode": launch_mode,
    }
    if launch_mode == "python_scenario":
        payload.update(
            {
                "scenario_class": template_source.get("scenario_class"),
                "additional_scenario_path": (
                    str(artifacts.additional_scenario_path)
                    if artifacts.additional_scenario_path is not None
                    else None
                ),
                "generated_config_path": (
                    str(artifacts.config_path) if artifacts.config_path is not None else None
                ),
            }
        )
    else:
        payload.update(
            {
                "relative_xosc_path": (
                    None if launch_mode != "openscenario" else template_source.get("relative_xosc_path")
                ),
                "resolved_xosc_path": (
                    str(artifacts.xosc_path) if artifacts.xosc_path is not None else None
                ),
                "template_relative_xosc_path": (
                    template_source.get("relative_xosc_path")
                    if launch_mode == "openscenario"
                    else None
                ),
                "template_resolved_xosc_path": (
                    template_source.get("resolved_xosc_path")
                    if launch_mode == "openscenario"
                    else None
                ),
                "generated_xosc_path": (
                    str(artifacts.xosc_path) if artifacts.xosc_path is not None else None
                ),
            }
        )
    return payload


def _resolve_launch_weather(
    template_weather: dict[str, Any], override_weather: dict[str, Any] | None
) -> dict[str, Any]:
    base_weather = copy.deepcopy(default_launch_weather())
    if isinstance(template_weather, dict):
        template_preset = str(template_weather.get("preset") or "").strip()
        if template_preset:
            base_weather["preset"] = template_preset
        for key, value in template_weather.items():
            if value is not None and key != "preset":
                base_weather[key] = value

    if isinstance(override_weather, dict):
        for key, value in override_weather.items():
            if value is not None:
                base_weather[key] = value

    preset = str(base_weather.get("preset") or "").strip()
    base_weather["preset"] = preset or "ClearNoon"
    return base_weather


def _resolve_launch_traffic(
    template_traffic: dict[str, Any],
    override_traffic: dict[str, Any] | None,
) -> dict[str, Any]:
    traffic = copy.deepcopy(template_traffic) if isinstance(template_traffic, dict) else {}
    override = override_traffic if isinstance(override_traffic, dict) else {}
    if override:
        traffic.update(copy.deepcopy(override))

    num_vehicles = max(0, int(traffic.get("num_vehicles") or 0))
    num_walkers = max(0, int(traffic.get("num_walkers") or 0))
    raw_seed = traffic.get("seed")
    seed = None if raw_seed in {None, ""} else max(0, int(raw_seed))
    enabled = num_vehicles > 0 or num_walkers > 0
    injection_mode = str(traffic.get("injection_mode") or "").strip()
    return {
        "enabled": enabled,
        "num_vehicles": num_vehicles,
        "num_walkers": num_walkers,
        "seed": seed,
        "injection_mode": (injection_mode or "carla_api_near_ego" if enabled else "disabled"),
    }


def _resolve_launch_sensors(
    template_sensors: dict[str, Any], override_sensors: dict[str, Any] | None
) -> dict[str, Any]:
    sensors = copy.deepcopy(template_sensors) if isinstance(template_sensors, dict) else {}
    override = override_sensors if isinstance(override_sensors, dict) else {}

    if override:
        sensors.update(copy.deepcopy(override))

    enabled = bool(sensors.get("enabled"))
    auto_start = bool(sensors.get("auto_start", False))
    profile_name = str(sensors.get("profile_name") or "").strip() or None
    config_yaml_path = str(sensors.get("config_yaml_path") or "").strip() or None
    sensor_items = sensors.get("sensors", [])
    if not isinstance(sensor_items, list):
        sensor_items = []

    return {
        "enabled": enabled,
        "auto_start": auto_start,
        "profile_name": profile_name,
        "config_yaml_path": config_yaml_path,
        "sensors": copy.deepcopy(sensor_items),
    }


def _resolve_launch_metadata(
    catalog_item: dict[str, Any],
    template_metadata: dict[str, Any],
    override_metadata: dict[str, Any] | None,
) -> dict[str, Any]:
    metadata = copy.deepcopy(template_metadata) if isinstance(template_metadata, dict) else {}
    override = override_metadata if isinstance(override_metadata, dict) else {}
    metadata["author"] = str(
        override.get("author") or metadata.get("author") or "scenario-launcher"
    ).strip()
    metadata["description"] = str(
        override.get("description")
        or metadata.get("description")
        or f"{catalog_item['display_name']}（Scenario Launch）"
    ).strip()

    tags: list[str] = []
    for value in [
        *(metadata.get("tags", []) if isinstance(metadata.get("tags"), list) else []),
        *(override.get("tags", []) if isinstance(override.get("tags"), list) else []),
        "native",
        str(catalog_item["scenario_id"]),
        "scenario_launch",
    ]:
        normalized = str(value).strip()
        if normalized and normalized not in tags:
            tags.append(normalized)
    metadata["tags"] = tags

    dut_model = override.get("dut_model", metadata.get("dut_model"))
    metadata["dut_model"] = (
        str(dut_model).strip() if isinstance(dut_model, str) and dut_model.strip() else None
    )
    return metadata


def _write_generated_python_scenario_config(
    *,
    output_path: Path,
    scenario_class: str,
    settings: Settings,
    descriptor: dict[str, Any],
    template_params: dict[str, ScenarioTemplateScalar],
    additional_scenario_path: Path,
) -> None:
    if not scenario_class:
        raise RuntimeError("Python Scenario 缺少 scenario_class")

    scenario = ElementTree.Element("scenarios")
    scenario_node = ElementTree.SubElement(
        scenario,
        "scenario",
        {
            "name": scenario_class,
            "type": scenario_class,
            "town": str(descriptor.get("map_name") or "Town01"),
        },
    )

    ego_vehicle = descriptor.get("ego_vehicle", {})
    spawn_point = ego_vehicle.get("spawn_point", {})
    ego_attributes = {
        "model": str(ego_vehicle.get("blueprint") or "vehicle.lincoln.mkz_2017"),
        "rolename": "hero",
        "x": str(spawn_point.get("x") or 0.0),
        "y": str(spawn_point.get("y") or 0.0),
        "z": str(spawn_point.get("z") or 0.5),
        "yaw": str(spawn_point.get("yaw") or 0.0),
        "random_location": "true",
    }
    ElementTree.SubElement(scenario_node, "ego_vehicle", ego_attributes)

    weather = descriptor.get("weather", {})
    weather_attrs = {
        key: str(value) for key, value in weather.items() if value is not None and key != "preset"
    }
    if weather_attrs:
        ElementTree.SubElement(scenario_node, "weather", weather_attrs)

    free_drive_attrs = {
        "timeout_seconds": str(descriptor.get("termination", {}).get("timeout_seconds") or 120),
        "controller_module": str(
            Path(__file__).resolve().parent / "controllers" / "duckpark_autopilot.py"
        ),
        "additional_scenario_path": str(additional_scenario_path),
        "traffic_manager_port": str(settings.traffic_manager_port),
        "target_speed_mps": str(template_params.get("targetSpeedMps", 10.0)),
        "roaming_seed": str(
            descriptor.get("traffic", {}).get("seed")
            if descriptor.get("traffic", {}).get("seed") is not None
            else 0
        ),
    }
    ElementTree.SubElement(scenario_node, "duckpark_free_drive", free_drive_attrs)

    ensure_dir(output_path.parent)
    tree = ElementTree.ElementTree(scenario)
    try:
        ElementTree.indent(tree, space="  ")
    except AttributeError:
        pass
    tree.write(output_path, encoding="utf-8", xml_declaration=True)


def _write_generated_xosc(
    *,
    template_path: Path,
    output_path: Path,
    scenario_id: str,
    settings: Settings,
    map_name: str,
    weather: dict[str, Any],
    template_params: dict[str, ScenarioTemplateScalar],
    timeout_seconds: int,
) -> None:
    root = ElementTree.parse(template_path).getroot()
    _apply_template_params(root, template_params)
    _apply_map_name(root, map_name)
    _apply_weather(root, weather)
    _apply_platform_launch_patch(
        root,
        scenario_id,
        settings,
        template_params,
        timeout_seconds,
    )
    _apply_launch_timeout(root, timeout_seconds)
    ensure_dir(output_path.parent)
    tree = ElementTree.ElementTree(root)
    try:
        ElementTree.indent(tree, space="  ")
    except AttributeError:
        pass
    tree.write(output_path, encoding="utf-8", xml_declaration=True)


def _apply_map_name(root: ElementTree.Element, map_name: str) -> None:
    road_network = _ensure_child(root, "RoadNetwork")
    logic_file = _ensure_child(road_network, "LogicFile")
    logic_file.set("filepath", map_name)


def _apply_template_params(
    root: ElementTree.Element,
    template_params: dict[str, ScenarioTemplateScalar],
) -> None:
    if not template_params:
        return

    declarations = {
        str(item.attrib.get("name") or "").strip(): item
        for item in root.findall("./ParameterDeclarations/ParameterDeclaration")
        if str(item.attrib.get("name") or "").strip()
    }
    for field, value in template_params.items():
        declaration = declarations.get(field)
        if declaration is None:
            continue
        declaration.set("value", format_template_param_value(value))


def _apply_launch_timeout(root: ElementTree.Element, timeout_seconds: int) -> None:
    for act in root.findall("./Storyboard/Story/Act"):
        stop_trigger = _ensure_child(act, "StopTrigger")
        _replace_with_simulation_time_stop_trigger(stop_trigger, timeout_seconds)


def _apply_platform_launch_patch(
    root: ElementTree.Element,
    scenario_id: str,
    settings: Settings,
    template_params: dict[str, ScenarioTemplateScalar],
    timeout_seconds: int,
) -> None:
    _apply_platform_actor_controller(root, settings, entity_ref="hero", target_speed_mps=10.0)
    if scenario_id == "osc_follow_leading_vehicle":
        _patch_follow_leading_vehicle(root, settings, template_params, timeout_seconds)


def _apply_platform_actor_controller(
    root: ElementTree.Element,
    settings: Settings,
    *,
    entity_ref: str,
    target_speed_mps: float,
) -> None:
    controller_module_path = (
        Path(__file__).resolve().parent / "controllers" / "duckpark_autopilot.py"
    )
    if not controller_module_path.exists():
        return

    actions = _ensure_child_path(root, ["Storyboard", "Init", "Actions"])
    private_actions = actions.find(f"./Private[@entityRef='{entity_ref}']")
    if private_actions is None:
        private_actions = ElementTree.SubElement(actions, "Private")
        private_actions.set("entityRef", entity_ref)

    controller_properties = private_actions.find(
        "./PrivateAction/ControllerAction/AssignControllerAction/Controller/Properties"
    )
    override_action = private_actions.find(
        "./PrivateAction/ControllerAction/OverrideControllerValueAction"
    )
    if controller_properties is None:
        private_action = ElementTree.SubElement(private_actions, "PrivateAction")
        controller_action = ElementTree.SubElement(private_action, "ControllerAction")
        assign_controller_action = ElementTree.SubElement(
            controller_action, "AssignControllerAction"
        )
        controller = ElementTree.SubElement(
            assign_controller_action,
            "Controller",
            {"name": f"DuckParkAutoPilot_{entity_ref}"},
        )
        controller_properties = ElementTree.SubElement(controller, "Properties")
        override_action = ElementTree.SubElement(controller_action, "OverrideControllerValueAction")

    if override_action is None:
        controller_action = private_actions.find("./PrivateAction/ControllerAction")
        if controller_action is None:
            private_action = private_actions.find("./PrivateAction")
            if private_action is None:
                private_action = ElementTree.SubElement(private_actions, "PrivateAction")
            controller_action = ElementTree.SubElement(private_action, "ControllerAction")
        override_action = ElementTree.SubElement(controller_action, "OverrideControllerValueAction")

    for tag in ("Throttle", "Brake", "Clutch", "ParkingBrake", "SteeringWheel", "Gear"):
        if override_action.find(tag) is None:
            attrs = {"value": "0", "active": "false"}
            if tag == "Gear":
                attrs = {"number": "0", "active": "false"}
            ElementTree.SubElement(override_action, tag, attrs)

    module_property = None
    traffic_manager_port_property = None
    target_speed_property = None
    for item in controller_properties.findall("Property"):
        name = str(item.attrib.get("name") or "").strip()
        if name == "module":
            module_property = item
        elif name == "traffic_manager_port":
            traffic_manager_port_property = item
        elif name == "target_speed_mps":
            target_speed_property = item

    if module_property is None:
        module_property = ElementTree.SubElement(controller_properties, "Property")
        module_property.set("name", "module")
    module_property.set("value", str(controller_module_path))

    if traffic_manager_port_property is None:
        traffic_manager_port_property = ElementTree.SubElement(controller_properties, "Property")
        traffic_manager_port_property.set("name", "traffic_manager_port")
    traffic_manager_port_property.set("value", str(settings.traffic_manager_port))

    if target_speed_property is None:
        target_speed_property = ElementTree.SubElement(controller_properties, "Property")
        target_speed_property.set("name", "target_speed_mps")
    target_speed_property.set("value", f"{float(target_speed_mps):.1f}")


def _patch_follow_leading_vehicle(
    root: ElementTree.Element,
    settings: Settings,
    template_params: dict[str, ScenarioTemplateScalar],
    timeout_seconds: int,
) -> None:
    leading_speed = float(template_params.get("leadingSpeed") or 2.0)
    _apply_platform_actor_controller(
        root,
        settings,
        entity_ref="adversary",
        target_speed_mps=leading_speed,
    )

    start_trigger = root.find(".//Event[@name='LeadingVehicleKeepsVelocity']/StartTrigger")
    if start_trigger is None:
        return
    _replace_with_simulation_time_start_trigger(
        start_trigger,
        start_after_seconds=1.0,
        condition_name="PlatformAutoStartLeadingVehicle",
    )
    dynamics = root.find(
        ".//Event[@name='LeadingVehicleKeepsVelocity']"
        "/Action/PrivateAction/LongitudinalAction/SpeedAction/SpeedActionDynamics"
    )
    if dynamics is not None:
        dynamics.set("dynamicsShape", "step")
        dynamics.set("dynamicsDimension", "time")
        dynamics.set("value", "1.0")

    waits_start_trigger = root.find(".//Event[@name='LeadingVehicleWaits']/StartTrigger")
    if waits_start_trigger is not None:
        _replace_with_simulation_time_start_trigger(
            waits_start_trigger,
            start_after_seconds=float(timeout_seconds) + 30.0,
            condition_name="PlatformDelayLeadingVehicleWait",
        )


def _replace_with_simulation_time_start_trigger(
    start_trigger: ElementTree.Element,
    *,
    start_after_seconds: float,
    condition_name: str,
) -> None:
    for child in list(start_trigger):
        start_trigger.remove(child)

    condition_group = ElementTree.SubElement(start_trigger, "ConditionGroup")
    condition = ElementTree.SubElement(
        condition_group,
        "Condition",
        {
            "name": condition_name,
            "delay": "0",
            "conditionEdge": "rising",
        },
    )
    by_value_condition = ElementTree.SubElement(condition, "ByValueCondition")
    ElementTree.SubElement(
        by_value_condition,
        "SimulationTimeCondition",
        {
            "value": f"{start_after_seconds:.1f}",
            "rule": "greaterThan",
        },
    )


def _replace_with_simulation_time_stop_trigger(
    stop_trigger: ElementTree.Element, timeout_seconds: int
) -> None:
    for child in list(stop_trigger):
        stop_trigger.remove(child)

    condition_group = ElementTree.SubElement(stop_trigger, "ConditionGroup")
    condition = ElementTree.SubElement(
        condition_group,
        "Condition",
        {
            "name": "LaunchTimeoutCondition",
            "delay": "0",
            "conditionEdge": "rising",
        },
    )
    by_value_condition = ElementTree.SubElement(condition, "ByValueCondition")
    ElementTree.SubElement(
        by_value_condition,
        "SimulationTimeCondition",
        {
            "value": f"{float(timeout_seconds):.1f}",
            "rule": "greaterThan",
        },
    )


def _apply_weather(root: ElementTree.Element, weather: dict[str, Any]) -> None:
    environment = _ensure_child_path(
        root,
        [
            "Storyboard",
            "Init",
            "Actions",
            "GlobalAction",
            "EnvironmentAction",
            "Environment",
        ],
    )
    environment.set(
        "name", environment.attrib.get("name", "LaunchEnvironment") or "LaunchEnvironment"
    )

    time_of_day = _ensure_child(environment, "TimeOfDay")
    time_of_day.set("animation", "false")
    if not time_of_day.attrib.get("dateTime"):
        time_of_day.set("dateTime", "2020-01-01T12:00:00")

    weather_element = _ensure_child(environment, "Weather")
    weather_element.set("cloudState", _cloud_state_from_weather(weather))

    sun = _ensure_child(weather_element, "Sun")
    if weather.get("sun_azimuth_angle") is not None:
        sun.set(
            "azimuth",
            f"{math.radians(float(weather['sun_azimuth_angle'])):.6f}",
        )
    elif not sun.attrib.get("azimuth"):
        sun.set("azimuth", "0")

    if weather.get("sun_altitude_angle") is not None:
        sun.set(
            "elevation",
            f"{math.radians(float(weather['sun_altitude_angle'])):.6f}",
        )
        sun.set(
            "intensity",
            f"{_sun_intensity_from_altitude(float(weather['sun_altitude_angle'])):.3f}",
        )
    else:
        sun.set("intensity", sun.attrib.get("intensity", "0.85") or "0.85")
        if not sun.attrib.get("elevation"):
            sun.set("elevation", "1.31")

    fog = _ensure_child(weather_element, "Fog")
    fog_density = weather.get("fog_density")
    if fog_density is not None:
        fog.set(
            "visualRange",
            f"{_visual_range_from_fog(float(fog_density)):.1f}",
        )
    elif not fog.attrib.get("visualRange"):
        fog.set("visualRange", "100000.0")

    precipitation = _ensure_child(weather_element, "Precipitation")
    precipitation_intensity = float(weather.get("precipitation") or 0.0)
    precipitation.set("intensity", f"{min(1.0, precipitation_intensity / 100.0):.3f}")
    precipitation.set(
        "precipitationType",
        "rain" if precipitation_intensity > 0.0 else "dry",
    )

    road_condition = _ensure_child(environment, "RoadCondition")
    road_condition.set(
        "frictionScaleFactor",
        f"{_friction_from_surface(weather):.3f}",
    )


def _ensure_child_path(root: ElementTree.Element, path: list[str]) -> ElementTree.Element:
    current = root
    for tag in path:
        current = _ensure_child(current, tag)
    return current


def _ensure_child(parent: ElementTree.Element, tag: str) -> ElementTree.Element:
    child = parent.find(tag)
    if child is None:
        child = ElementTree.SubElement(parent, tag)
    return child


def _cloud_state_from_weather(weather: dict[str, Any]) -> str:
    cloudiness = float(weather.get("cloudiness") or 0.0)
    precipitation = float(weather.get("precipitation") or 0.0)
    if precipitation >= 40.0:
        return "rainy"
    if cloudiness >= 70.0:
        return "overcast"
    if cloudiness >= 30.0:
        return "cloudy"
    return "free"


def _sun_intensity_from_altitude(altitude_angle: float) -> float:
    normalized = max(0.0, min(1.0, (altitude_angle + 5.0) / 85.0))
    return 0.15 + normalized * 0.85


def _visual_range_from_fog(fog_density: float) -> float:
    normalized = max(0.0, min(100.0, fog_density))
    return max(30.0, 100000.0 * (1.0 - normalized / 100.0))


def _friction_from_surface(weather: dict[str, Any]) -> float:
    wetness = max(0.0, min(100.0, float(weather.get("wetness") or 0.0)))
    deposits = max(
        0.0,
        min(100.0, float(weather.get("precipitation_deposits") or 0.0)),
    )
    penalty = max(wetness, deposits) / 150.0
    return max(0.45, 1.0 - penalty)
