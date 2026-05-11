from __future__ import annotations

from typing import Any

from app.scenario.launch_builder import default_launch_capabilities


def list_platform_scenario_catalog() -> list[dict[str, Any]]:
    return [
        build_town10_autonomous_demo_item(),
        build_town01_urban_loop_item(),
        build_town02_suburb_cruise_item(),
        build_town03_intersection_sweep_item(),
        build_town03_rush_hour_item(),
        build_town04_night_cruise_item(),
        build_town05_rainy_commute_item(),
        build_town10_dense_flow_item(),
        build_free_drive_sensor_collection_item(),
    ]


def _build_tm_autopilot_catalog_item(
    *,
    scenario_id: str,
    display_name: str,
    description: str,
    default_map_name: str,
    weather_preset: str,
    weather_overrides: dict[str, float] | None,
    target_speed_mps: float,
    num_vehicles: int,
    num_walkers: int,
    timeout_seconds: int,
    tags: list[str],
) -> dict[str, Any]:
    return {
        "scenario_id": scenario_id,
        "scenario_name": scenario_id,
        "display_name": display_name,
        "description": description,
        "default_map_name": default_map_name,
        "execution_support": "native",
        "execution_backend": "native",
        "web_hidden": False,
        "source": {
            "provider": "native",
            "version": "duckpark_native",
            "launch_mode": "native_descriptor",
            "template_params": {"targetSpeedMps": target_speed_mps},
        },
        "preset": {
            "locked_map_name": default_map_name,
            "map_locked": True,
            "event_locked": False,
            "actors_locked": False,
            "weather_runtime_editable": False,
            "event_summary": "hero 由平台内置 TM 自动驾驶控制，可直接启动巡航。",
            "actors_summary": "hero + 内置背景车辆/行人",
        },
        "parameter_declarations": [],
        "descriptor_template": {
            "version": 1,
            "scenario_name": scenario_id,
            "map_name": default_map_name,
            "weather": {
                "preset": weather_preset,
                **(weather_overrides or {}),
            },
            "sync": {"enabled": False, "fixed_delta_seconds": 1.0 / 30.0},
            "ego_vehicle": {
                "blueprint": "vehicle.lincoln.mkz_2017",
                "spawn_point": {
                    "x": 0.0,
                    "y": 0.0,
                    "z": 0.5,
                    "roll": 0.0,
                    "pitch": 0.0,
                    "yaw": 0.0,
                },
            },
            "traffic": {
                "enabled": True,
                "num_vehicles": num_vehicles,
                "num_walkers": num_walkers,
                "seed": None,
                "injection_mode": "carla_api_near_ego",
            },
            "sensors": {
                "enabled": True,
                "auto_start": False,
                "profile_name": "front_rgb",
                "config_yaml_path": None,
                "sensors": [],
            },
            "termination": {
                "timeout_seconds": timeout_seconds,
                "success_condition": "timeout",
            },
            "recorder": {"enabled": True},
            "debug": {"viewer_friendly": False},
            "metadata": {
                "author": "duckpark",
                "tags": ["native", *tags],
                "description": display_name,
            },
        },
        "launch_capabilities": default_launch_capabilities(
            map_editable=False,
            sensor_profile_editable=False,
        ),
    }


def build_town10_autonomous_demo_item() -> dict[str, Any]:
    return {
        "scenario_id": "town10_autonomous_demo",
        "scenario_name": "town10_autonomous_demo",
        "display_name": "Town10 自动驾驶演示",
        "description": (
            "面向联调和客户演示的自动驾驶接管模板。固定 Town10HD_Opt，"
            "hero 由平台内置自动驾驶接管，适合配合 CARLA 跟随视角、"
            "Pi HDMI 采集和 Jetson 手动推理展示整条链路。默认保持长驻运行，"
            "由执行页 Stop 按钮手动结束。"
        ),
        "default_map_name": "Town10HD_Opt",
        "execution_support": "native",
        "execution_backend": "native",
        "web_hidden": False,
        "source": {
            "provider": "native",
            "version": "duckpark_native",
            "launch_mode": "native_descriptor",
            "template_params": {"targetSpeedMps": 6.5},
        },
        "preset": {
            "locked_map_name": "Town10HD_Opt",
            "map_locked": True,
            "event_locked": False,
            "actors_locked": False,
            "weather_runtime_editable": False,
            "event_summary": (
                "平台自动驾驶在 Town10HD_Opt 内长驻巡航，便于持续展示前视画面与推理结果；"
                "默认通过执行页 Stop 手动结束。"
            ),
            "actors_summary": "hero + 演示级背景车辆/行人，默认围绕 ego 注入",
        },
        "parameter_declarations": [],
        "descriptor_template": {
            "version": 1,
            "scenario_name": "town10_autonomous_demo",
            "map_name": "Town10HD_Opt",
            "weather": {"preset": "ClearNoon"},
            "sync": {"enabled": False, "fixed_delta_seconds": 1.0 / 30.0},
            "ego_vehicle": {
                "blueprint": "vehicle.lincoln.mkz_2017",
                "spawn_point": {
                    "x": 0.0,
                    "y": 0.0,
                    "z": 0.5,
                    "roll": 0.0,
                    "pitch": 0.0,
                    "yaw": 0.0,
                },
            },
            "traffic": {
                "enabled": True,
                "num_vehicles": 12,
                "num_walkers": 8,
                "seed": None,
                "injection_mode": "carla_api_near_ego",
            },
            "sensors": {
                "enabled": True,
                "auto_start": False,
                "profile_name": "front_rgb",
                "config_yaml_path": None,
                "sensors": [],
            },
            "termination": {"timeout_seconds": 86400, "success_condition": "manual_stop"},
            "recorder": {"enabled": True},
            "debug": {"viewer_friendly": False},
            "metadata": {
                "author": "duckpark",
                "tags": ["native", "town10_autonomous_demo", "demo"],
                "description": "Town10 自动驾驶演示模板",
            },
        },
        "launch_capabilities": default_launch_capabilities(
            map_editable=False,
            sensor_profile_editable=False,
            timeout_editable=False,
        ),
    }


def build_town01_urban_loop_item() -> dict[str, Any]:
    return _build_tm_autopilot_catalog_item(
        scenario_id="town01_urban_loop",
        display_name="Town01 城市环线巡航",
        description="固定 Town01，hero 由内置 TM 自动驾驶巡航，适合基础联调与城市街区演示。",
        default_map_name="Town01",
        weather_preset="ClearNoon",
        weather_overrides=None,
        target_speed_mps=8.0,
        num_vehicles=16,
        num_walkers=10,
        timeout_seconds=180,
        tags=["town01_urban_loop", "tm_autopilot", "urban"],
    )


def build_town02_suburb_cruise_item() -> dict[str, Any]:
    return _build_tm_autopilot_catalog_item(
        scenario_id="town02_suburb_cruise",
        display_name="Town02 郊区巡航",
        description="固定 Town02，适合低密度交通下的连续自动驾驶展示。",
        default_map_name="Town02",
        weather_preset="CloudyNoon",
        weather_overrides=None,
        target_speed_mps=8.5,
        num_vehicles=14,
        num_walkers=6,
        timeout_seconds=180,
        tags=["town02_suburb_cruise", "tm_autopilot", "suburb"],
    )


def build_town03_intersection_sweep_item() -> dict[str, Any]:
    return _build_tm_autopilot_catalog_item(
        scenario_id="town03_intersection_sweep",
        display_name="Town03 路口穿行",
        description="固定 Town03，强调连续路口和车流交织下的 TM 自动驾驶巡航。",
        default_map_name="Town03",
        weather_preset="ClearSunset",
        weather_overrides=None,
        target_speed_mps=7.5,
        num_vehicles=22,
        num_walkers=16,
        timeout_seconds=180,
        tags=["town03_intersection_sweep", "tm_autopilot", "intersection"],
    )


def build_town03_rush_hour_item() -> dict[str, Any]:
    return _build_tm_autopilot_catalog_item(
        scenario_id="town03_rush_hour",
        display_name="Town03 高峰车流",
        description="固定 Town03，提升背景交通密度，用于高峰时段自动驾驶展示。",
        default_map_name="Town03",
        weather_preset="WetCloudyNoon",
        weather_overrides=None,
        target_speed_mps=6.5,
        num_vehicles=28,
        num_walkers=20,
        timeout_seconds=180,
        tags=["town03_rush_hour", "tm_autopilot", "dense_traffic"],
    )


def build_town04_night_cruise_item() -> dict[str, Any]:
    return _build_tm_autopilot_catalog_item(
        scenario_id="town04_night_cruise",
        display_name="Town04 夜间巡航",
        description="固定 Town04，适合夜间道路跟车和灯光效果演示。",
        default_map_name="Town04",
        weather_preset="ClearSunset",
        weather_overrides={"sun_altitude_angle": -8.0},
        target_speed_mps=7.0,
        num_vehicles=18,
        num_walkers=8,
        timeout_seconds=180,
        tags=["town04_night_cruise", "tm_autopilot", "night"],
    )


def build_town05_rainy_commute_item() -> dict[str, Any]:
    return _build_tm_autopilot_catalog_item(
        scenario_id="town05_rainy_commute",
        display_name="Town05 雨天通勤",
        description="固定 Town05，使用雨天预设展示恶劣天气下的自动驾驶巡航。",
        default_map_name="Town05",
        weather_preset="MidRainSunset",
        weather_overrides=None,
        target_speed_mps=6.5,
        num_vehicles=20,
        num_walkers=10,
        timeout_seconds=180,
        tags=["town05_rainy_commute", "tm_autopilot", "rain"],
    )


def build_town06_long_route_item() -> dict[str, Any]:
    return _build_tm_autopilot_catalog_item(
        scenario_id="town06_long_route",
        display_name="Town06 长路线巡航",
        description="固定 Town06，适合较长路线的稳定巡航与前视画面演示。",
        default_map_name="Town06",
        weather_preset="ClearNoon",
        weather_overrides=None,
        target_speed_mps=9.0,
        num_vehicles=16,
        num_walkers=6,
        timeout_seconds=240,
        tags=["town06_long_route", "tm_autopilot", "long_route"],
    )


def build_town07_hillside_patrol_item() -> dict[str, Any]:
    return _build_tm_autopilot_catalog_item(
        scenario_id="town07_hillside_patrol",
        display_name="Town07 山地道路巡航",
        description="固定 Town07，适合坡道和弯道路段的自动驾驶展示。",
        default_map_name="Town07",
        weather_preset="SoftRainSunset",
        weather_overrides=None,
        target_speed_mps=7.0,
        num_vehicles=18,
        num_walkers=8,
        timeout_seconds=180,
        tags=["town07_hillside_patrol", "tm_autopilot", "hillside"],
    )


def build_town10_dense_flow_item() -> dict[str, Any]:
    return _build_tm_autopilot_catalog_item(
        scenario_id="town10_dense_flow",
        display_name="Town10 密集车流巡航",
        description="固定 Town10HD_Opt，使用更高背景交通密度做高负载巡航演示。",
        default_map_name="Town10HD_Opt",
        weather_preset="CloudySunset",
        weather_overrides=None,
        target_speed_mps=7.5,
        num_vehicles=30,
        num_walkers=18,
        timeout_seconds=240,
        tags=["town10_dense_flow", "tm_autopilot", "dense_traffic"],
    )


def build_free_drive_sensor_collection_item() -> dict[str, Any]:
    return {
        "scenario_id": "free_drive_sensor_collection",
        "scenario_name": "free_drive_sensor_collection",
        "display_name": "随机自由行驶 / 传感器采集",
        "description": (
            "面向传感器数据采集的自由行驶模板。支持所有地图随机出生点、"
            "天气、背景车辆/行人和最长运行时长；hero 由平台内置自动驾驶控制，"
            "背景交通会优先围绕 ego 注入。"
        ),
        "default_map_name": "Town10HD_Opt",
        "execution_support": "native",
        "execution_backend": "native",
        "web_hidden": False,
        "source": {
            "provider": "native",
            "version": "duckpark_native",
            "launch_mode": "native_descriptor",
        },
        "preset": {
            "locked_map_name": "",
            "map_locked": False,
            "event_locked": False,
            "actors_locked": False,
            "weather_runtime_editable": False,
            "event_summary": "随机背景车流和行人产生自然事件，适合长时间传感器采集。",
            "actors_summary": "hero + 可配置背景车辆/行人",
        },
        "parameter_declarations": [],
        "descriptor_template": {
            "version": 1,
            "scenario_name": "free_drive_sensor_collection",
            "map_name": "Town10HD_Opt",
            "weather": {"preset": "ClearNoon"},
            "sync": {"enabled": False, "fixed_delta_seconds": 1.0 / 30.0},
            "ego_vehicle": {
                "blueprint": "vehicle.lincoln.mkz_2017",
                "spawn_point": {
                    "x": 0.0,
                    "y": 0.0,
                    "z": 0.5,
                    "roll": 0.0,
                    "pitch": 0.0,
                    "yaw": 0.0,
                },
            },
            "traffic": {
                "enabled": True,
                "num_vehicles": 20,
                "num_walkers": 16,
                "seed": None,
                "injection_mode": "carla_api_near_ego",
            },
            "sensors": {
                "enabled": True,
                "auto_start": False,
                "profile_name": "front_rgb",
                "config_yaml_path": None,
                "sensors": [],
            },
            "termination": {"timeout_seconds": 120, "success_condition": "timeout"},
            "recorder": {"enabled": True},
            "debug": {"viewer_friendly": False},
            "metadata": {
                "author": "duckpark",
                "tags": ["native", "free_drive_sensor_collection"],
                "description": "随机自由行驶传感器采集模板",
            },
        },
        "launch_capabilities": default_launch_capabilities(
            map_editable=True,
            sensor_profile_editable=True,
        ),
    }
