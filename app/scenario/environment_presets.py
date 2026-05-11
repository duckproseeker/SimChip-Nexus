from __future__ import annotations

from typing import Any

ENVIRONMENT_PRESETS: list[dict[str, Any]] = [
    {
        "preset_id": "clear_noon",
        "display_name": "Clear Noon",
        "description": "CARLA 官方晴朗正午模板，适合作为基线演示和回归起点。",
        "weather": {"preset": "ClearNoon", "sun_altitude_angle": 68.0},
    },
    {
        "preset_id": "cloudy_noon",
        "display_name": "Cloudy Noon",
        "description": "CARLA 官方多云正午模板，适合验证曝光和识别鲁棒性。",
        "weather": {"preset": "CloudyNoon", "cloudiness": 65.0},
    },
    {
        "preset_id": "wet_noon",
        "display_name": "Wet Noon",
        "description": "CARLA 官方潮湿正午模板，适合展示路面反光和视觉退化。",
        "weather": {
            "preset": "WetNoon",
            "wetness": 60.0,
            "precipitation_deposits": 45.0,
        },
    },
    {
        "preset_id": "wet_cloudy_noon",
        "display_name": "Wet Cloudy Noon",
        "description": "CARLA 官方湿地多云正午模板，适合做雨前和阴天过渡展示。",
        "weather": {
            "preset": "WetCloudyNoon",
            "cloudiness": 80.0,
            "wetness": 70.0,
            "precipitation_deposits": 55.0,
        },
    },
    {
        "preset_id": "soft_rain_noon",
        "display_name": "Soft Rain Noon",
        "description": "CARLA 官方小雨正午模板，适合轻量雨天展示。",
        "weather": {
            "preset": "SoftRainNoon",
            "precipitation": 35.0,
            "wetness": 50.0,
            "cloudiness": 75.0,
        },
    },
    {
        "preset_id": "mid_rain_noon",
        "display_name": "Mid Rain Noon",
        "description": "CARLA 官方中雨正午模板，适合稳定复现雨天场景。",
        "weather": {
            "preset": "MidRainyNoon",
            "precipitation": 60.0,
            "wetness": 70.0,
            "cloudiness": 85.0,
        },
    },
    {
        "preset_id": "hard_rain_noon",
        "display_name": "Hard Rain Noon",
        "description": "CARLA 官方大雨正午模板，用于极端开环感知压测。",
        "weather": {
            "preset": "HardRainNoon",
            "precipitation": 85.0,
            "wetness": 85.0,
            "fog_density": 20.0,
        },
    },
    {
        "preset_id": "clear_sunset",
        "display_name": "Clear Sunset",
        "description": "CARLA 官方晴朗黄昏模板，适合展示低太阳高度角效果。",
        "weather": {
            "preset": "ClearSunset",
            "sun_altitude_angle": 12.0,
            "sun_azimuth_angle": 220.0,
        },
    },
    {
        "preset_id": "cloudy_sunset",
        "display_name": "Cloudy Sunset",
        "description": "CARLA 官方多云黄昏模板，适合展示傍晚阴天场景。",
        "weather": {
            "preset": "CloudySunset",
            "cloudiness": 70.0,
            "sun_altitude_angle": 10.0,
        },
    },
    {
        "preset_id": "wet_sunset",
        "display_name": "Wet Sunset",
        "description": "CARLA 官方潮湿黄昏模板，适合展示湿滑路面与夕照。",
        "weather": {
            "preset": "WetSunset",
            "wetness": 60.0,
            "precipitation_deposits": 45.0,
            "sun_altitude_angle": 8.0,
        },
    },
    {
        "preset_id": "wet_cloudy_sunset",
        "display_name": "Wet Cloudy Sunset",
        "description": "CARLA 官方湿地多云黄昏模板，适合演示复杂光照与反光。",
        "weather": {
            "preset": "WetCloudySunset",
            "cloudiness": 80.0,
            "wetness": 75.0,
            "precipitation_deposits": 55.0,
            "sun_altitude_angle": 6.0,
        },
    },
    {
        "preset_id": "soft_rain_sunset",
        "display_name": "Soft Rain Sunset",
        "description": "CARLA 官方小雨黄昏模板，适合展示雨天低照度效果。",
        "weather": {
            "preset": "SoftRainSunset",
            "precipitation": 35.0,
            "cloudiness": 78.0,
            "wetness": 55.0,
            "sun_altitude_angle": 5.0,
        },
    },
    {
        "preset_id": "mid_rain_sunset",
        "display_name": "Mid Rain Sunset",
        "description": "CARLA 官方中雨黄昏模板，适合展示晚高峰雨天观感。",
        "weather": {
            "preset": "MidRainSunset",
            "precipitation": 60.0,
            "cloudiness": 88.0,
            "wetness": 72.0,
            "sun_altitude_angle": 4.0,
        },
    },
    {
        "preset_id": "hard_rain_sunset",
        "display_name": "Hard Rain Sunset",
        "description": "CARLA 官方大雨黄昏模板，适合展示极端雨天和低照度叠加。",
        "weather": {
            "preset": "HardRainSunset",
            "precipitation": 90.0,
            "cloudiness": 92.0,
            "wetness": 88.0,
            "fog_density": 28.0,
            "sun_altitude_angle": 3.0,
        },
    },
    {
        "preset_id": "clear_night",
        "display_name": "Clear Night",
        "description": "基于官方晴朗黄昏模板扩展出的夜晚场景，适合夜间演示。",
        "weather": {
            "preset": "ClearSunset",
            "sun_altitude_angle": -75.0,
            "sun_azimuth_angle": 230.0,
        },
    },
    {
        "preset_id": "wet_night",
        "display_name": "Wet Night",
        "description": "夜晚湿滑路面模板，适合观察灯光反射和低照度退化。",
        "weather": {
            "preset": "WetCloudySunset",
            "sun_altitude_angle": -78.0,
            "cloudiness": 82.0,
            "wetness": 78.0,
            "precipitation_deposits": 60.0,
        },
    },
    {
        "preset_id": "hard_rain_night",
        "display_name": "Hard Rain Night",
        "description": "大雨夜晚模板，适合演示最苛刻的光照和降雨叠加条件。",
        "weather": {
            "preset": "HardRainSunset",
            "sun_altitude_angle": -80.0,
            "cloudiness": 95.0,
            "precipitation": 92.0,
            "wetness": 90.0,
            "fog_density": 30.0,
        },
    },
    {
        "preset_id": "dense_fog_day",
        "display_name": "Dense Fog Day",
        "description": "浓雾白天模板，适合展示远距离可见度下降。",
        "weather": {
            "preset": "CloudyNoon",
            "cloudiness": 75.0,
            "fog_density": 72.0,
            "sun_altitude_angle": 42.0,
        },
    },
    {
        "preset_id": "dense_fog_night",
        "display_name": "Dense Fog Night",
        "description": "浓雾夜晚模板，适合演示夜间能见度和感知退化。",
        "weather": {
            "preset": "CloudySunset",
            "sun_altitude_angle": -82.0,
            "cloudiness": 85.0,
            "fog_density": 88.0,
            "wetness": 20.0,
        },
    },
]


def list_environment_presets() -> list[dict[str, Any]]:
    return [dict(item) for item in ENVIRONMENT_PRESETS]
