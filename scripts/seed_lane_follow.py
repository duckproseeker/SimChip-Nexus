#!/usr/bin/env python3
"""
Seed a lane-following scenario asset by recording ego autopilot in CARLA.

Usage (inside the ros2-dev container or any env with carla package):
    python3 scripts/seed_lane_follow.py --host 127.0.0.1 --duration 120

Produces a .log recorder file and registers it as a ScenarioAsset via the
platform API (if --register is passed).
"""
from __future__ import annotations

import argparse
import os
import random
import sys
import time
from pathlib import Path

try:
    import carla
except ImportError:
    carla_egg = os.environ.get("CARLA_EGG")
    if carla_egg:
        sys.path.insert(0, carla_egg)
    import carla


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Record lane-following scenario")
    parser.add_argument("--host", default=os.environ.get("CARLA_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("CARLA_PORT", "2000")))
    parser.add_argument("--tm-port", type=int, default=int(os.environ.get("TRAFFIC_MANAGER_PORT", "8010")))
    parser.add_argument("--map", default="Town10HD_Opt")
    parser.add_argument("--duration", type=int, default=120, help="Recording duration in seconds")
    parser.add_argument("--num-vehicles", type=int, default=30)
    parser.add_argument("--num-walkers", type=int, default=50)
    parser.add_argument("--ego-speed", type=float, default=30.0, help="Ego target speed km/h")
    parser.add_argument("--ego-spawn-idx", type=int, default=5, help="Index into map spawn_points for ego")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--recorder-dir", type=str, default="",
                        help="Host-absolute path where CARLA server writes .log (must be accessible by CARLA process)")
    parser.add_argument("--output-dir", type=str, default="")
    parser.add_argument("--fixed-delta", type=float, default=0.05)
    parser.add_argument("--register", action="store_true", help="Register to platform ScenarioAsset API")
    parser.add_argument("--api-url", default=os.environ.get("DUCKPARK_API_BASE_URL", "http://127.0.0.1:8000"))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    random.seed(args.seed)

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    recorder_filename = f"lane_follow_{args.map}_{timestamp}.log"

    # CARLA server mounts host's run_data/scenario_recordings as /recordings
    # ros2-dev mounts the same dir as /ros2_ws/src/SimChip-Nexus/run_data/scenario_recordings
    # Both containers see the same files.
    carla_container_recorder_dir = "/recordings"
    carla_container_recorder_path = f"{carla_container_recorder_dir}/{recorder_filename}"

    # Local output directory (accessible from ros2-dev via volume mount)
    output_dir = Path(args.output_dir) if args.output_dir else Path("/ros2_ws/src/SimChip-Nexus/run_data/scenario_recordings")
    output_dir.mkdir(parents=True, exist_ok=True)
    local_recorder_path = output_dir / recorder_filename

    # Host path (for registering with the platform API)
    host_recorder_path = Path(str(local_recorder_path).replace("/ros2_ws/src", "/home/du/ros2-humble/src"))

    print(f"[seed] Connecting to CARLA at {args.host}:{args.port}")
    client = carla.Client(args.host, args.port)
    client.set_timeout(20.0)

    print(f"[seed] Loading map: {args.map}")
    world = client.load_world(args.map)

    settings = world.get_settings()
    settings.synchronous_mode = True
    settings.fixed_delta_seconds = args.fixed_delta
    world.apply_settings(settings)

    traffic_manager = client.get_trafficmanager(args.tm_port)
    traffic_manager.set_synchronous_mode(True)
    traffic_manager.set_random_device_seed(args.seed)
    traffic_manager.set_global_distance_to_leading_vehicle(2.5)

    spawned_actors: list = []
    walker_controllers: list = []

    try:
        blueprint_library = world.get_blueprint_library()
        spawn_points = world.get_map().get_spawn_points()

        # Pick ego spawn point: use index 5 which is verified to be on a clear road
        ego_spawn_idx = args.ego_spawn_idx
        if ego_spawn_idx >= len(spawn_points):
            ego_spawn_idx = 5

        # --- Spawn ego vehicle ---
        ego_bp = blueprint_library.find("vehicle.tesla.model3")
        ego_bp.set_attribute("role_name", "hero")
        ego_spawn = spawn_points[ego_spawn_idx]
        ego_vehicle = world.spawn_actor(ego_bp, ego_spawn)
        spawned_actors.append(ego_vehicle)
        print(f"[seed] Ego spawned at {ego_spawn.location} (spawn_point[{ego_spawn_idx}])")

        ego_vehicle.set_autopilot(True, args.tm_port)
        traffic_manager.vehicle_percentage_speed_difference(ego_vehicle, 0.0)
        traffic_manager.auto_lane_change(ego_vehicle, True)
        traffic_manager.distance_to_leading_vehicle(ego_vehicle, 3.0)

        # --- Spawn NPC vehicles (skip points near ego) ---
        vehicle_bps = [bp for bp in blueprint_library.filter("vehicle.*")
                       if int(bp.get_attribute("number_of_wheels")) >= 4]
        # Filter spawn points: exclude ego's point and those too close
        ego_loc = ego_spawn.location
        npc_spawn_points = [
            sp for i, sp in enumerate(spawn_points)
            if i != ego_spawn_idx and sp.location.distance(ego_loc) > 30.0
        ]
        random.shuffle(npc_spawn_points)
        num_vehicles = min(args.num_vehicles, len(npc_spawn_points))
        print(f"[seed] Spawning {num_vehicles} NPC vehicles")

        batch_vehicles = []
        for i in range(num_vehicles):
            bp = random.choice(vehicle_bps)
            if bp.has_attribute("color"):
                color = random.choice(bp.get_attribute("color").recommended_values)
                bp.set_attribute("color", color)
            bp.set_attribute("role_name", "autopilot")
            transform = npc_spawn_points[i]
            batch_vehicles.append(carla.command.SpawnActor(bp, transform).then(
                carla.command.SetAutopilot(carla.command.FutureActor, True, args.tm_port)
            ))

        results = client.apply_batch_sync(batch_vehicles, True)
        for result in results:
            if not result.error:
                spawned_actors.append(world.get_actor(result.actor_id))

        print(f"[seed] {len([r for r in results if not r.error])} NPC vehicles spawned")

        # --- Spawn walkers ---
        walker_bps = blueprint_library.filter("walker.pedestrian.*")
        num_walkers = args.num_walkers
        print(f"[seed] Spawning {num_walkers} walkers")

        walker_spawn_points = []
        for _ in range(num_walkers):
            loc = world.get_random_location_from_navigation()
            if loc is not None:
                walker_spawn_points.append(carla.Transform(location=loc))

        batch_walkers = []
        for sp in walker_spawn_points:
            bp = random.choice(walker_bps)
            if bp.has_attribute("is_invincible"):
                bp.set_attribute("is_invincible", "false")
            batch_walkers.append(carla.command.SpawnActor(bp, sp))

        walker_results = client.apply_batch_sync(batch_walkers, True)
        walkers_spawned = []
        for result in walker_results:
            if not result.error:
                walkers_spawned.append(world.get_actor(result.actor_id))
                spawned_actors.append(world.get_actor(result.actor_id))

        # Spawn walker controllers
        walker_controller_bp = blueprint_library.find("controller.ai.walker")
        batch_controllers = []
        for walker in walkers_spawned:
            batch_controllers.append(carla.command.SpawnActor(walker_controller_bp, carla.Transform(), walker))

        controller_results = client.apply_batch_sync(batch_controllers, True)
        for result in controller_results:
            if not result.error:
                controller = world.get_actor(result.actor_id)
                walker_controllers.append(controller)
                spawned_actors.append(controller)

        # Let world settle
        for _ in range(10):
            world.tick()

        # Start walker AI
        for controller in walker_controllers:
            target = world.get_random_location_from_navigation()
            if target:
                controller.start()
                controller.go_to_location(target)
                controller.set_max_speed(1.0 + random.random() * 1.5)

        print(f"[seed] {len(walkers_spawned)} walkers spawned with AI controllers")

        # Let everything settle
        for _ in range(20):
            world.tick()

        # --- Start recording ---
        print(f"[seed] Starting recorder → {carla_container_recorder_path}")
        client.start_recorder(carla_container_recorder_path, True)

        # --- Run simulation ---
        total_ticks = int(args.duration / args.fixed_delta)
        report_interval = total_ticks // 10
        print(f"[seed] Running {args.duration}s ({total_ticks} ticks at {args.fixed_delta}s delta)")

        for tick in range(total_ticks):
            world.tick()
            if report_interval > 0 and tick % report_interval == 0:
                elapsed = tick * args.fixed_delta
                loc = ego_vehicle.get_location()
                vel = ego_vehicle.get_velocity()
                speed_kmh = 3.6 * (vel.x**2 + vel.y**2 + vel.z**2)**0.5
                print(f"[seed]   t={elapsed:.0f}s  ego=({loc.x:.1f},{loc.y:.1f})  speed={speed_kmh:.1f}km/h")

        # --- Stop recording ---
        client.stop_recorder()
        print(f"[seed] Recording stopped.")
        print(f"[seed] Recorder file inside CARLA container: {carla_container_recorder_path}")
        print(f"[seed] To copy out, run on host:")
        print(f"[seed]   docker cp carla-offscreen:{carla_container_recorder_path} {host_recorder_path}")
        file_size = 0

        # Try docker cp if available (works when running on host, not inside container)
        import subprocess
        copy_cmd = [
            "docker", "cp",
            f"carla-offscreen:{carla_container_recorder_path}",
            str(local_recorder_path),
        ]
        try:
            cp_result = subprocess.run(copy_cmd, capture_output=True, text=True, timeout=30)
            if cp_result.returncode == 0 and local_recorder_path.exists():
                file_size = local_recorder_path.stat().st_size
                print(f"[seed] Copied! {local_recorder_path} ({file_size / 1024 / 1024:.1f} MB)")
            else:
                print(f"[seed] docker cp not available here (expected inside container)")
        except FileNotFoundError:
            print(f"[seed] docker CLI not found (running inside container, copy from host later)")

    finally:
        # Cleanup
        print("[seed] Cleaning up actors...")
        client.set_timeout(20.0)
        for controller in walker_controllers:
            try:
                controller.stop()
            except Exception:
                pass

        # Reset world settings before destroying
        settings = world.get_settings()
        settings.synchronous_mode = False
        settings.fixed_delta_seconds = None
        world.apply_settings(settings)
        try:
            traffic_manager.set_synchronous_mode(False)
        except Exception:
            pass

        if spawned_actors:
            client.apply_batch_sync([carla.command.DestroyActor(a) for a in spawned_actors], True)
        print(f"[seed] Destroyed {len(spawned_actors)} actors")

    # --- Register as ScenarioAsset ---
    if args.register:
        import json
        from urllib import request, error

        payload = json.dumps({
            "name": f"车道跟随 / {args.map} / {args.duration}s",
            "recorder_log_path": str(host_recorder_path),
            "map_name": args.map,
            "duration_seconds": float(args.duration),
            "tags": ["lane_follow", "autopilot", args.map.lower()],
            "description": (
                f"自动录制的车道跟随场景。地图 {args.map}，"
                f"{num_vehicles} 辆 NPC 车辆，{len(walkers_spawned)} 个行人，"
                f"录制时长 {args.duration}s。"
            ),
            "file_size_bytes": file_size,
            "metadata": {
                "seed": args.seed,
                "num_vehicles": num_vehicles,
                "num_walkers": len(walkers_spawned),
                "fixed_delta_seconds": args.fixed_delta,
                "author": "seed_lane_follow",
            },
        }).encode("utf-8")

        url = f"{args.api_url.rstrip('/')}/scenario-assets"
        req = request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
        try:
            with request.urlopen(req, timeout=10) as resp:
                result = json.loads(resp.read().decode())
                print(f"[seed] Registered as ScenarioAsset: {result.get('id')}")
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            print(f"[seed] Failed to register: HTTP {exc.code} — {detail}")
        except Exception as exc:
            print(f"[seed] Failed to register: {exc}")

    print("[seed] Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
