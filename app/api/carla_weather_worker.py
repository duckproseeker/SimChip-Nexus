from __future__ import annotations

import json
import sys

from app.core.config import get_settings


def main() -> int:
    if len(sys.argv) < 2:
        print(json.dumps({"ok": False, "error": "missing weather payload"}))
        return 2

    payload = json.loads(sys.argv[1])
    settings = get_settings()

    try:
        import carla  # type: ignore
    except ImportError:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": "CARLA Python API is not installed in the environment.",
                }
            )
        )
        return 3

    client = carla.Client(settings.carla_host, settings.carla_port)
    client.set_timeout(5.0)

    world = client.get_world()

    preset_name = str(payload.get("preset", "")).strip()
    weather_params = getattr(carla.WeatherParameters, preset_name, None)
    if weather_params is None:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": f"Unsupported weather preset: {preset_name}",
                    "status_code": 400,
                }
            )
        )
        return 4

    runtime_weather = carla.WeatherParameters(
        cloudiness=float(weather_params.cloudiness),
        precipitation=float(weather_params.precipitation),
        precipitation_deposits=float(weather_params.precipitation_deposits),
        wind_intensity=float(weather_params.wind_intensity),
        sun_azimuth_angle=float(weather_params.sun_azimuth_angle),
        sun_altitude_angle=float(weather_params.sun_altitude_angle),
        fog_density=float(weather_params.fog_density),
        wetness=float(weather_params.wetness),
    )

    for key, value in payload.items():
        if key == "preset" or value is None:
            continue
        if hasattr(runtime_weather, key):
            setattr(runtime_weather, key, float(value))

    world.set_weather(runtime_weather)
    print(
        json.dumps(
            {
                "ok": True,
                "message": f"Successfully updated global weather to {preset_name}",
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
