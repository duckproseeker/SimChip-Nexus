from __future__ import annotations

import json
import sys
from pathlib import Path

from app.core.config import get_settings
from app.executor.carla_client import CarlaClient
from app.scenario.maps import map_family_key


def _ok(checks: dict[str, bool], details: dict[str, object]) -> None:
    print(json.dumps({"ok": True, "checks": checks, "details": details}, ensure_ascii=False))


def _fail(checks: dict[str, bool], message: str, details: dict[str, object] | None = None) -> int:
    print(
        json.dumps(
            {
                "ok": False,
                "error": message,
                "status_code": 409,
                "checks": checks,
                "details": details or {},
            },
            ensure_ascii=False,
        )
    )
    return 3


def main() -> int:
    if len(sys.argv) < 2:
        return _fail({}, "missing worker payload")
    payload = json.loads(sys.argv[1])
    map_name = str(payload.get("map_name") or "").strip()
    fixed_delta_seconds = float(payload.get("fixed_delta_seconds") or 0.05)
    recorder_output_dir = Path(str(payload.get("recorder_output_dir") or "")).expanduser()
    sensor_profile_valid = bool(payload.get("sensor_profile_valid", False))

    checks = {
        "carla_server_ready": False,
        "world_loaded_or_loadable": False,
        "traffic_manager_port_reachable": False,
        "traffic_manager_sync_configurable": False,
        "synchronous_mode_settable": False,
        "fixed_delta_settable": False,
        "map_available": False,
        "recorder_output_dir_writable": False,
        "sensor_profile_valid": sensor_profile_valid,
    }
    if not sensor_profile_valid:
        return _fail(checks, "sensor profile invalid")

    try:
        recorder_output_dir.mkdir(parents=True, exist_ok=True)
        probe_path = recorder_output_dir / ".materialization-preflight"
        probe_path.write_text("ok", encoding="utf-8")
        probe_path.unlink(missing_ok=True)
        checks["recorder_output_dir_writable"] = True
    except OSError as exc:
        return _fail(checks, f"recorder output dir not writable: {exc}")

    settings = get_settings()
    client = CarlaClient(
        settings.carla_host,
        settings.carla_port,
        settings.carla_timeout_seconds,
        settings.traffic_manager_port,
    )
    try:
        client.connect(connect_traffic_manager=False)
        checks["carla_server_ready"] = True
        available_maps = client.get_available_maps()
        checks["map_available"] = any(
            map_family_key(item) == map_family_key(map_name) for item in available_maps
        )
        if not checks["map_available"]:
            return _fail(checks, f"map unavailable: {map_name}", {"available_maps": available_maps})

        client.load_map(map_name)
        checks["world_loaded_or_loadable"] = True
        client.connect_traffic_manager(
            startup_timeout_seconds=max(settings.carla_timeout_seconds, 15.0)
        )
        checks["traffic_manager_port_reachable"] = True
        client.configure_world_sync(True, fixed_delta_seconds)
        checks["synchronous_mode_settable"] = True
        checks["fixed_delta_settable"] = True
        client.configure_tm_sync(True)
        checks["traffic_manager_sync_configurable"] = True
    except Exception as exc:
        return _fail(checks, f"materialization preflight failed: {exc}")
    finally:
        try:
            client.cleanup()
        except Exception:
            pass

    _ok(checks, {"map_name": map_name, "fixed_delta_seconds": fixed_delta_seconds})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
