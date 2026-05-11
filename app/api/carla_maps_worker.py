from __future__ import annotations

import json
import sys

from app.core.config import get_settings
from app.executor.carla_client import CarlaClient
from app.scenario.maps import collapse_available_maps


def main() -> int:
    if len(sys.argv) < 2:
        print(json.dumps({"ok": False, "error": "missing worker payload"}))
        return 2

    _ = json.loads(sys.argv[1])
    settings = get_settings()

    try:
        client = CarlaClient(
            settings.carla_host,
            settings.carla_port,
            settings.carla_timeout_seconds,
            settings.traffic_manager_port,
        )
        client.connect(connect_traffic_manager=False)
        available_maps = client.get_available_maps()
    except Exception as exc:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": f"获取 CARLA 地图列表失败: {exc}",
                    "status_code": 503,
                }
            )
        )
        return 3

    print(json.dumps({"ok": True, "maps": collapse_available_maps(available_maps)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
