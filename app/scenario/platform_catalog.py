from __future__ import annotations

from typing import Any

from app.scenario.launch_builder import default_launch_capabilities

MapSelectionMode = str

MAP_SELECTION_FIXED: MapSelectionMode = "fixed"
MAP_SELECTION_SUBSET: MapSelectionMode = "subset"
MAP_SELECTION_ALL: MapSelectionMode = "all"


def list_platform_scenario_catalog() -> list[dict[str, Any]]:
    return [
        build_town10_autonomous_demo_item(),
        build_town01_urban_loop_item(),
        build_town02_suburb_cruise_item(),
        build_town03_intersection_sweep_item(),
        build_town03_rush_hour_item(),
        build_town04_night_cruise_item(),
        build_town05_rainy_commute_item(),
        build_town06_long_route_item(),
        build_town07_hillside_patrol_item(),
        build_town10_dense_flow_item(),
        build_free_drive_sensor_collection_item(),
        build_public_route_materialization_item(),
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
    map_selection_mode: MapSelectionMode,
    allowed_map_names: list[str],
) -> dict[str, Any]:
    map_editable = map_selection_mode != MAP_SELECTION_FIXED
    locked_map_name = default_map_name if map_selection_mode != MAP_SELECTION_ALL else ""
    return {
        "scenario_id": scenario_id,
        "scenario_name": scenario_id,
        "display_name": display_name,
        "description": description,
        "default_map_name": default_map_name,
        "map_selection_mode": map_selection_mode,
        "allowed_map_names": allowed_map_names,
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
            "locked_map_name": locked_map_name,
            "map_locked": not map_editable,
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
            map_editable=map_editable,
            sensor_profile_editable=False,
        ),
    }


def build_town10_autonomous_demo_item() -> dict[str, Any]:
    return {
        "scenario_id": "town10_autonomous_demo",
        "scenario_name": "town10_autonomous_demo",
        "display_name": "自动驾驶演示",
        "description": (
            "面向联调和客户演示的自动驾驶接管模板。固定 Town10HD_Opt，"
            "hero 由平台内置自动驾驶接管，适合配合 OpenCV 相机预览、"
            "Pi HDMI 采集和 Jetson 手动推理展示整条链路。默认保持长驻运行，"
            "由执行页 Stop 按钮手动结束。"
        ),
        "default_map_name": "Town10HD_Opt",
        "map_selection_mode": MAP_SELECTION_FIXED,
        "allowed_map_names": ["Town10HD_Opt"],
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
                "profile_name": "quad_rgb_mosaic",
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
            sensor_profile_editable=True,
            timeout_editable=False,
        ),
    }


def build_town01_urban_loop_item() -> dict[str, Any]:
    return _build_tm_autopilot_catalog_item(
        scenario_id="town01_urban_loop",
        display_name="城市环线巡航",
        description="面向城市街区道路的自动驾驶巡航模板，适合基础联调与城市路网演示。",
        default_map_name="Town01",
        weather_preset="ClearNoon",
        weather_overrides=None,
        target_speed_mps=8.0,
        num_vehicles=16,
        num_walkers=10,
        timeout_seconds=180,
        tags=["town01_urban_loop", "tm_autopilot", "urban"],
        map_selection_mode=MAP_SELECTION_SUBSET,
        allowed_map_names=["Town01", "Town03", "Town05", "Town10HD_Opt"],
    )


def build_public_route_materialization_item() -> dict[str, Any]:
    return {
        "scenario_id": "public_route_materialization",
        "scenario_name": "public_route_materialization",
        "display_name": "公共路线重物化",
        "description": "内部场景源 materialization 模板，用于将 Leaderboard/Bench2Drive route XML 重物化为 recorder 资产。",
        "default_map_name": "Town01",
        "map_selection_mode": MAP_SELECTION_ALL,
        "allowed_map_names": [],
        "execution_support": "native",
        "execution_backend": "native",
        "web_hidden": True,
        "source": {
            "provider": "scenario_source",
            "version": "materialization_v1",
            "launch_mode": "leaderboard_route",
            "template_params": {"targetSpeedMps": 7.0},
        },
        "preset": {
            "locked_map_name": "",
            "map_locked": False,
            "event_locked": True,
            "actors_locked": True,
            "weather_runtime_editable": False,
            "event_summary": "按公共 route XML 的首个 waypoint 生成 hero，并使用 v1 route_follower materialization agent。",
            "actors_summary": "hero + route XML/平台 materialization 控制",
        },
        "parameter_declarations": [],
        "descriptor_template": {
            "version": 1,
            "scenario_name": "public_route_materialization",
            "map_name": "Town01",
            "weather": {"preset": "ClearNoon"},
            "sync": {"enabled": True, "fixed_delta_seconds": 0.05},
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
            "traffic": {"enabled": False, "num_vehicles": 0, "num_walkers": 0},
            "sensors": {"enabled": False, "auto_start": False, "profile_name": None, "sensors": []},
            "termination": {"timeout_seconds": 60, "success_condition": "timeout"},
            "recorder": {"enabled": True},
            "debug": {"viewer_friendly": False},
            "metadata": {
                "author": "scenario-source-materialization",
                "tags": ["scenario_source", "materialization", "leaderboard_route"],
                "description": "公共 route XML materialization run",
            },
        },
        "launch_capabilities": default_launch_capabilities(
            map_editable=True,
            sensor_profile_editable=True,
            timeout_editable=True,
        ),
    }


def build_town02_suburb_cruise_item() -> dict[str, Any]:
    return _build_tm_autopilot_catalog_item(
        scenario_id="town02_suburb_cruise",
        display_name="郊区巡航",
        description="面向郊区道路结构的连续自动驾驶展示，适合低密度交通场景。",
        default_map_name="Town02",
        weather_preset="CloudyNoon",
        weather_overrides=None,
        target_speed_mps=8.5,
        num_vehicles=14,
        num_walkers=6,
        timeout_seconds=180,
        tags=["town02_suburb_cruise", "tm_autopilot", "suburb"],
        map_selection_mode=MAP_SELECTION_SUBSET,
        allowed_map_names=["Town02", "Town07"],
    )


def build_town03_intersection_sweep_item() -> dict[str, Any]:
    return _build_tm_autopilot_catalog_item(
        scenario_id="town03_intersection_sweep",
        display_name="路口穿行",
        description="强调连续路口和车流交织下的 TM 自动驾驶巡航。",
        default_map_name="Town03",
        weather_preset="ClearSunset",
        weather_overrides=None,
        target_speed_mps=7.5,
        num_vehicles=22,
        num_walkers=16,
        timeout_seconds=180,
        tags=["town03_intersection_sweep", "tm_autopilot", "intersection"],
        map_selection_mode=MAP_SELECTION_SUBSET,
        allowed_map_names=["Town03", "Town05", "Town10HD_Opt"],
    )


def build_town03_rush_hour_item() -> dict[str, Any]:
    return _build_tm_autopilot_catalog_item(
        scenario_id="town03_rush_hour",
        display_name="高峰车流",
        description="提升背景交通密度，用于高峰时段自动驾驶展示。",
        default_map_name="Town03",
        weather_preset="WetCloudyNoon",
        weather_overrides=None,
        target_speed_mps=6.5,
        num_vehicles=28,
        num_walkers=20,
        timeout_seconds=180,
        tags=["town03_rush_hour", "tm_autopilot", "dense_traffic"],
        map_selection_mode=MAP_SELECTION_SUBSET,
        allowed_map_names=["Town03", "Town05", "Town10HD_Opt"],
    )


def build_town04_night_cruise_item() -> dict[str, Any]:
    return _build_tm_autopilot_catalog_item(
        scenario_id="town04_night_cruise",
        display_name="夜间巡航",
        description="使用夜间光照语义，适合道路跟车和灯光效果演示。",
        default_map_name="Town04",
        weather_preset="ClearSunset",
        weather_overrides={"sun_altitude_angle": -8.0},
        target_speed_mps=7.0,
        num_vehicles=18,
        num_walkers=8,
        timeout_seconds=180,
        tags=["town04_night_cruise", "tm_autopilot", "night"],
        map_selection_mode=MAP_SELECTION_ALL,
        allowed_map_names=[],
    )


def build_town05_rainy_commute_item() -> dict[str, Any]:
    return _build_tm_autopilot_catalog_item(
        scenario_id="town05_rainy_commute",
        display_name="雨天通勤",
        description="使用雨天预设展示恶劣天气下的自动驾驶巡航。",
        default_map_name="Town05",
        weather_preset="MidRainSunset",
        weather_overrides=None,
        target_speed_mps=6.5,
        num_vehicles=20,
        num_walkers=10,
        timeout_seconds=180,
        tags=["town05_rainy_commute", "tm_autopilot", "rain"],
        map_selection_mode=MAP_SELECTION_ALL,
        allowed_map_names=[],
    )


def build_town06_long_route_item() -> dict[str, Any]:
    return _build_tm_autopilot_catalog_item(
        scenario_id="town06_long_route",
        display_name="长路线巡航",
        description="适合较长路线的稳定巡航与前视画面演示。",
        default_map_name="Town06",
        weather_preset="ClearNoon",
        weather_overrides=None,
        target_speed_mps=9.0,
        num_vehicles=16,
        num_walkers=6,
        timeout_seconds=240,
        tags=["town06_long_route", "tm_autopilot", "long_route"],
        map_selection_mode=MAP_SELECTION_SUBSET,
        allowed_map_names=["Town04", "Town06", "Town10HD_Opt"],
    )


def build_town07_hillside_patrol_item() -> dict[str, Any]:
    return _build_tm_autopilot_catalog_item(
        scenario_id="town07_hillside_patrol",
        display_name="山地道路巡航",
        description="适合坡道和弯道路段的自动驾驶展示。",
        default_map_name="Town07",
        weather_preset="SoftRainSunset",
        weather_overrides=None,
        target_speed_mps=7.0,
        num_vehicles=18,
        num_walkers=8,
        timeout_seconds=180,
        tags=["town07_hillside_patrol", "tm_autopilot", "hillside"],
        map_selection_mode=MAP_SELECTION_SUBSET,
        allowed_map_names=["Town07"],
    )


def build_town10_dense_flow_item() -> dict[str, Any]:
    return _build_tm_autopilot_catalog_item(
        scenario_id="town10_dense_flow",
        display_name="密集车流巡航",
        description="使用更高背景交通密度做高负载巡航演示。",
        default_map_name="Town10HD_Opt",
        weather_preset="CloudySunset",
        weather_overrides=None,
        target_speed_mps=7.5,
        num_vehicles=30,
        num_walkers=18,
        timeout_seconds=240,
        tags=["town10_dense_flow", "tm_autopilot", "dense_traffic"],
        map_selection_mode=MAP_SELECTION_SUBSET,
        allowed_map_names=["Town03", "Town05", "Town10HD_Opt"],
    )


def build_free_drive_sensor_collection_item() -> dict[str, Any]:
    return {
        "scenario_id": "free_drive_sensor_collection",
        "scenario_name": "free_drive_sensor_collection",
        "display_name": "随机自由行驶 / 场景录制",
        "description": (
            "面向 CARLA recorder 场景资产录制的自由行驶模板。支持所有地图随机出生点、"
            "天气、背景车辆/行人和最长运行时长；hero 由平台内置自动驾驶控制，"
            "背景交通会优先围绕 ego 注入。传感器配置只用于运行时预览，不保存帧数据。"
        ),
        "default_map_name": "Town10HD_Opt",
        "map_selection_mode": MAP_SELECTION_ALL,
        "allowed_map_names": [],
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
            "event_summary": "随机背景车流和行人产生自然事件，适合长时间场景录制。",
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
                "profile_name": "quad_rgb_mosaic",
                "config_yaml_path": None,
                "sensors": [],
            },
            "termination": {"timeout_seconds": 120, "success_condition": "timeout"},
            "recorder": {"enabled": True},
            "debug": {"viewer_friendly": False},
            "metadata": {
                "author": "duckpark",
                "tags": ["native", "free_drive_sensor_collection"],
                "description": "随机自由行驶场景录制模板",
            },
        },
        "launch_capabilities": default_launch_capabilities(
            map_editable=True,
            sensor_profile_editable=True,
        ),
    }
