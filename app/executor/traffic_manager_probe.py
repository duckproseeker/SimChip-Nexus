from __future__ import annotations

import argparse


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Probe CARLA Traffic Manager readiness")
    parser.add_argument("--host", required=True)
    parser.add_argument("--port", required=True, type=int)
    parser.add_argument("--traffic-manager-port", required=True, type=int)
    parser.add_argument("--timeout-seconds", required=True, type=float)
    args = parser.parse_args(argv)

    import carla  # type: ignore

    client = carla.Client(args.host, args.port)
    client.set_timeout(args.timeout_seconds)
    client.get_world()
    traffic_manager = client.get_trafficmanager(args.traffic_manager_port)
    traffic_manager.get_port()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
