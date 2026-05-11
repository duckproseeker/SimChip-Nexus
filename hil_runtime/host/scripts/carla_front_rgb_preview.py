#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import queue
import random
import signal
import math
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import yaml

try:
    import carla  # type: ignore
except ImportError as exc:  # pragma: no cover - runtime guard
    raise SystemExit(f"carla Python API not available: {exc}") from exc


@dataclass(frozen=True)
class SensorSpec:
    sensor_id: str
    x: float
    y: float
    z: float
    roll: float
    pitch: float
    yaw: float
    width: int
    height: int
    fov: float
    sensor_tick: float


SRC_ROOT = Path(__file__).resolve().parents[3]
PROJECT_ROOT = Path(
    os.environ.get("DUCKPARK_PLATFORM_ROOT", str(SRC_ROOT / "SimChip-Nexus"))
).resolve()
DEFAULT_SENSOR_CONFIG = PROJECT_ROOT / "configs" / "sensors" / "front_rgb.yaml"
DEFAULT_SPAWN_POINT = {
    "x": 0.0,
    "y": 0.0,
    "z": 0.5,
    "roll": 0.0,
    "pitch": 0.0,
    "yaw": 0.0,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Attach a front RGB sensor to hero/ego and show a fullscreen preview."
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=2000)
    parser.add_argument("--traffic-manager-port", type=int, default=8000)
    parser.add_argument("--timeout-seconds", type=float, default=10.0)
    parser.add_argument("--map-name", default="")
    parser.add_argument("--sensor-config", default=str(DEFAULT_SENSOR_CONFIG))
    parser.add_argument("--sensor-id", default="FrontRGB")
    parser.add_argument("--role-name", default="hero")
    parser.add_argument("--blueprint", default="vehicle.lincoln.mkz_2017")
    parser.add_argument("--window-name", default="DuckPark Front RGB Preview")
    parser.add_argument(
        "--display-mode",
        choices=("sensor_preview", "native_follow"),
        default="native_follow",
    )
    parser.add_argument("--sensor-tick", type=float, default=1.0 / 30.0)
    parser.add_argument("--fixed-delta-seconds", type=float, default=1.0 / 30.0)
    parser.add_argument("--follow-rate-hz", type=float, default=60.0)
    parser.add_argument("--wait-for-role-seconds", type=float, default=0.0)
    parser.add_argument("--weather-preset", default="ClearNoon")
    parser.add_argument("--traffic-vehicles", type=int, default=12)
    parser.add_argument("--traffic-seed", type=int, default=7)
    parser.add_argument("--spawn-x", type=float, default=DEFAULT_SPAWN_POINT["x"])
    parser.add_argument("--spawn-y", type=float, default=DEFAULT_SPAWN_POINT["y"])
    parser.add_argument("--spawn-z", type=float, default=DEFAULT_SPAWN_POINT["z"])
    parser.add_argument("--spawn-roll", type=float, default=DEFAULT_SPAWN_POINT["roll"])
    parser.add_argument("--spawn-pitch", type=float, default=DEFAULT_SPAWN_POINT["pitch"])
    parser.add_argument("--spawn-yaw", type=float, default=DEFAULT_SPAWN_POINT["yaw"])
    parser.add_argument(
        "--fullscreen",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Render preview in fullscreen mode.",
    )
    parser.add_argument(
        "--follow-spectator",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Keep CARLA spectator aligned with the front RGB camera.",
    )
    parser.add_argument(
        "--spawn-ego-if-missing",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Spawn a hero vehicle when the requested role name does not exist.",
    )
    parser.add_argument(
        "--enable-autopilot",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Enable autopilot for the hero vehicle.",
    )
    parser.add_argument(
        "--prefer-map-spawn",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Prefer CARLA map spawn points before the requested fallback transform.",
    )
    return parser.parse_args()


def load_sensor_spec(config_path: Path, sensor_id: str, sensor_tick: float) -> SensorSpec:
    payload = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    sensors = payload.get("sensors") or []
    for item in sensors:
        if str(item.get("id") or "").strip() != sensor_id:
            continue
        if str(item.get("type") or "").strip() != "sensor.camera.rgb":
            raise RuntimeError(f"sensor '{sensor_id}' is not a sensor.camera.rgb entry")
        return SensorSpec(
            sensor_id=sensor_id,
            x=float(item.get("x", 1.5)),
            y=float(item.get("y", 0.0)),
            z=float(item.get("z", 1.7)),
            roll=float(item.get("roll", 0.0)),
            pitch=float(item.get("pitch", 0.0)),
            yaw=float(item.get("yaw", 0.0)),
            width=int(item.get("width", 1920)),
            height=int(item.get("height", 1080)),
            fov=float(item.get("fov", 90.0)),
            sensor_tick=float(sensor_tick),
        )
    raise RuntimeError(f"sensor '{sensor_id}' not found in {config_path}")


def normalize_map_name(map_name: str) -> str:
    return str(map_name).strip().rstrip("/").split("/")[-1]


def build_transform(payload: dict[str, float]) -> carla.Transform:
    return carla.Transform(
        carla.Location(x=payload["x"], y=payload["y"], z=payload["z"]),
        carla.Rotation(
            roll=payload.get("roll", 0.0),
            pitch=payload.get("pitch", 0.0),
            yaw=payload.get("yaw", 0.0),
        ),
    )


def find_vehicle_by_role(world: carla.World, role_name: str) -> Any | None:
    target = role_name.strip()
    if not target:
        return None
    vehicles = world.get_actors().filter("vehicle.*")
    for vehicle in vehicles:
        if str(vehicle.attributes.get("role_name") or "").strip() == target:
            return vehicle
    return None


def wait_for_vehicle_by_role(
    world: carla.World,
    role_name: str,
    timeout_seconds: float,
    *,
    poll_interval_seconds: float = 0.5,
) -> Any | None:
    deadline = time.monotonic() + max(0.0, timeout_seconds)
    while True:
        vehicle = find_vehicle_by_role(world, role_name)
        if vehicle is not None:
            return vehicle
        if time.monotonic() >= deadline:
            return None
        try:
            world.wait_for_tick(seconds=min(1.0, poll_interval_seconds))
        except TypeError:
            world.wait_for_tick()
        except RuntimeError:
            # CARLA can accept RPC before the async world starts producing ticks.
            time.sleep(poll_interval_seconds)
            continue
        time.sleep(poll_interval_seconds)


def spawn_ego_vehicle(
    world: carla.World,
    blueprint_id: str,
    role_name: str,
    spawn_point: dict[str, float],
    *,
    prefer_map_spawn: bool,
    seed: int,
) -> Any:
    blueprints = world.get_blueprint_library()
    blueprint = blueprints.find(blueprint_id)
    if blueprint.has_attribute("role_name"):
        blueprint.set_attribute("role_name", role_name)

    map_spawn_points = wait_for_map_spawn_points(world)
    random.Random(seed).shuffle(map_spawn_points)
    requested_transform = build_transform(spawn_point)
    if prefer_map_spawn:
        candidates = list(map_spawn_points)
        fallback_candidates = [requested_transform]
    else:
        candidates = [requested_transform]
        candidates.extend(map_spawn_points)
        fallback_candidates = []
    seen: set[tuple[float, float, float, float, float, float]] = set()
    retry_deadline = time.monotonic() + 10.0
    while True:
        for transform in candidates:
            key = (
                round(float(transform.location.x), 3),
                round(float(transform.location.y), 3),
                round(float(transform.location.z), 3),
                round(float(transform.rotation.roll), 3),
                round(float(transform.rotation.pitch), 3),
                round(float(transform.rotation.yaw), 3),
            )
            if key in seen:
                continue
            seen.add(key)
            actor = world.try_spawn_actor(blueprint, transform)
            if actor is not None:
                return actor
        if time.monotonic() >= retry_deadline:
            break
        seen.clear()
        try:
            world.wait_for_tick(seconds=1.0)
        except TypeError:
            world.wait_for_tick()
        time.sleep(0.5)

    for transform in fallback_candidates:
        actor = world.try_spawn_actor(blueprint, transform)
        if actor is not None:
            if map_spawn_points:
                actor.set_transform(map_spawn_points[0])
                try:
                    world.wait_for_tick(seconds=1.0)
                except TypeError:
                    world.wait_for_tick()
            return actor
    raise RuntimeError("failed to spawn ego vehicle on requested transform or map spawn points")


def wait_for_map_spawn_points(
    world: carla.World,
    *,
    timeout_seconds: float = 20.0,
    poll_interval_seconds: float = 0.5,
) -> list[carla.Transform]:
    deadline = time.monotonic() + max(1.0, timeout_seconds)
    last_count = 0
    while time.monotonic() < deadline:
        spawn_points = list(world.get_map().get_spawn_points())
        last_count = len(spawn_points)
        if spawn_points:
            return spawn_points
        try:
            world.wait_for_tick(seconds=1.0)
        except TypeError:
            world.wait_for_tick()
        time.sleep(poll_interval_seconds)
    raise RuntimeError(f"map spawn points not ready (count={last_count})")


def spawn_rgb_sensor(
    world: carla.World,
    ego_vehicle: Any,
    spec: SensorSpec,
) -> Any:
    blueprint = world.get_blueprint_library().find("sensor.camera.rgb")
    blueprint.set_attribute("image_size_x", str(spec.width))
    blueprint.set_attribute("image_size_y", str(spec.height))
    blueprint.set_attribute("fov", str(spec.fov))
    if blueprint.has_attribute("sensor_tick"):
        blueprint.set_attribute("sensor_tick", str(spec.sensor_tick))

    transform = carla.Transform(
        carla.Location(x=spec.x, y=spec.y, z=spec.z),
        carla.Rotation(roll=spec.roll, pitch=spec.pitch, yaw=spec.yaw),
    )
    return world.spawn_actor(
        blueprint,
        transform,
        attach_to=ego_vehicle,
        attachment_type=carla.AttachmentType.Rigid,
    )


def spawn_traffic(
    client: carla.Client,
    world: carla.World,
    traffic_manager_port: int,
    count: int,
    seed: int,
) -> list[Any]:
    if count <= 0:
        return []

    tm = client.get_trafficmanager(traffic_manager_port)
    tm.set_global_distance_to_leading_vehicle(2.5)
    tm.global_percentage_speed_difference(0.0)
    tm.set_random_device_seed(seed)

    blueprint_library = world.get_blueprint_library().filter("vehicle.*")
    vehicle_blueprints = [
        blueprint
        for blueprint in blueprint_library
        if not blueprint.has_attribute("number_of_wheels")
        or int(blueprint.get_attribute("number_of_wheels").as_int()) == 4
    ]
    if not vehicle_blueprints:
        return []

    spawn_points = list(world.get_map().get_spawn_points())
    random.Random(seed).shuffle(spawn_points)

    actors: list[Any] = []
    for index, transform in enumerate(spawn_points):
        if len(actors) >= count:
            break
        blueprint = random.choice(vehicle_blueprints)
        if blueprint.has_attribute("role_name"):
            blueprint.set_attribute("role_name", f"duckpark_preview_npc_{index}")
        actor = world.try_spawn_actor(blueprint, transform)
        if actor is None:
            continue
        actor.set_autopilot(True, traffic_manager_port)
        actors.append(actor)
    return actors


def decode_bgr(image: Any) -> np.ndarray:
    frame = np.frombuffer(image.raw_data, dtype=np.uint8)
    frame = frame.reshape((image.height, image.width, 4))
    return frame[:, :, :3]


def _rotate_local_offset(base_rotation: carla.Rotation, spec: SensorSpec) -> carla.Location:
    pitch = math.radians(float(base_rotation.pitch))
    yaw = math.radians(float(base_rotation.yaw))
    roll = math.radians(float(base_rotation.roll))

    local_x = float(spec.x)
    local_y = float(spec.y)
    local_z = float(spec.z)

    cy = math.cos(yaw)
    sy = math.sin(yaw)
    cp = math.cos(pitch)
    sp = math.sin(pitch)
    cr = math.cos(roll)
    sr = math.sin(roll)

    # Unreal/CARLA local axes: X forward, Y right, Z up.
    world_x = local_x * cp * cy + local_y * (cy * sp * sr - sy * cr) + local_z * (
        -cy * sp * cr - sy * sr
    )
    world_y = local_x * cp * sy + local_y * (sy * sp * sr + cy * cr) + local_z * (
        -sy * sp * cr + cy * sr
    )
    world_z = local_x * sp + local_y * (-cp * sr) + local_z * (cp * cr)
    return carla.Location(x=world_x, y=world_y, z=world_z)


def build_follow_camera_transform(vehicle_transform: carla.Transform, spec: SensorSpec) -> carla.Transform:
    rotated_offset = _rotate_local_offset(vehicle_transform.rotation, spec)
    location = carla.Location(
        x=float(vehicle_transform.location.x) + float(rotated_offset.x),
        y=float(vehicle_transform.location.y) + float(rotated_offset.y),
        z=float(vehicle_transform.location.z) + float(rotated_offset.z),
    )
    rotation = carla.Rotation(
        pitch=float(vehicle_transform.rotation.pitch) + float(spec.pitch),
        yaw=float(vehicle_transform.rotation.yaw) + float(spec.yaw),
        roll=float(vehicle_transform.rotation.roll) + float(spec.roll),
    )
    return carla.Transform(location, rotation)


def main() -> int:
    args = parse_args()
    sensor_config = Path(args.sensor_config).expanduser().resolve()
    if not sensor_config.is_file():
        raise SystemExit(f"sensor config not found: {sensor_config}")

    sensor_spec = load_sensor_spec(
        sensor_config,
        sensor_id=args.sensor_id,
        sensor_tick=args.sensor_tick,
    )

    client = carla.Client(args.host, args.port)
    client.set_timeout(args.timeout_seconds)
    world = client.get_world()

    if args.map_name:
        current_map = normalize_map_name(world.get_map().name)
        requested_map = normalize_map_name(args.map_name)
        if current_map != requested_map:
            print(f"loading map {requested_map} from {current_map}", flush=True)
            world = client.load_world(requested_map)
            try:
                world.wait_for_tick(seconds=10.0)
            except TypeError:
                world.wait_for_tick()
            time.sleep(1.0)

    settings = world.get_settings()
    settings.synchronous_mode = False
    settings.fixed_delta_seconds = float(args.fixed_delta_seconds)
    world.apply_settings(settings)

    if args.weather_preset:
        weather = getattr(carla.WeatherParameters, args.weather_preset, None)
        if weather is None:
            raise SystemExit(f"unsupported weather preset: {args.weather_preset}")
        world.set_weather(weather)

    ego_vehicle = find_vehicle_by_role(world, args.role_name)
    if ego_vehicle is None and args.wait_for_role_seconds > 0:
        print(
            f"waiting up to {args.wait_for_role_seconds:.1f}s for role '{args.role_name}'",
            flush=True,
        )
        ego_vehicle = wait_for_vehicle_by_role(
            world,
            args.role_name,
            timeout_seconds=args.wait_for_role_seconds,
        )
    spawned_ego = False
    if ego_vehicle is None and args.spawn_ego_if_missing:
        ego_vehicle = spawn_ego_vehicle(
            world,
            blueprint_id=args.blueprint,
            role_name=args.role_name,
            spawn_point={
                "x": args.spawn_x,
                "y": args.spawn_y,
                "z": args.spawn_z,
                "roll": args.spawn_roll,
                "pitch": args.spawn_pitch,
                "yaw": args.spawn_yaw,
            },
            prefer_map_spawn=bool(args.prefer_map_spawn),
            seed=args.traffic_seed,
        )
        spawned_ego = True
        print(
            "spawned ego vehicle "
            f"id={ego_vehicle.id} role={args.role_name} "
            f"location=({ego_vehicle.get_location().x:.2f},"
            f"{ego_vehicle.get_location().y:.2f},"
            f"{ego_vehicle.get_location().z:.2f})",
            flush=True,
        )

    if ego_vehicle is None:
        raise SystemExit(
            f"role '{args.role_name}' not found and spawn disabled"
        )

    if args.enable_autopilot:
        try:
            ego_vehicle.set_autopilot(True, args.traffic_manager_port)
        except RuntimeError as exc:
            print(f"warning: failed to enable ego autopilot: {exc}", flush=True)

    try:
        traffic_actors = spawn_traffic(
            client,
            world,
            traffic_manager_port=args.traffic_manager_port,
            count=max(0, args.traffic_vehicles),
            seed=args.traffic_seed,
        )
    except RuntimeError as exc:
        print(f"warning: failed to spawn traffic: {exc}", flush=True)
        traffic_actors = []
    if traffic_actors:
        print(f"spawned traffic vehicles={len(traffic_actors)}", flush=True)

    should_stop = False

    def request_stop(_signum: int, _frame: Any) -> None:
        nonlocal should_stop
        should_stop = True

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)

    print(
        "preview ready "
        f"map={normalize_map_name(world.get_map().name)} "
        f"display_mode={args.display_mode} "
        f"sensor={sensor_spec.sensor_id} "
        f"resolution={sensor_spec.width}x{sensor_spec.height} "
        f"traffic={len(traffic_actors)}",
        flush=True,
    )

    processed_frames = 0
    started_at = time.monotonic()
    sensor = None
    image_queue: queue.Queue[Any] | None = None
    spectator = world.get_spectator() if (args.follow_spectator or args.display_mode == "native_follow") else None

    if args.display_mode == "sensor_preview":
        image_queue = queue.Queue(maxsize=2)

        def on_image(image: Any) -> None:
            try:
                assert image_queue is not None
                if image_queue.full():
                    _ = image_queue.get_nowait()
                image_queue.put_nowait(image)
            except queue.Empty:
                pass
            except queue.Full:
                pass

        sensor = spawn_rgb_sensor(world, ego_vehicle, sensor_spec)
        sensor.listen(on_image)

        cv2.namedWindow(args.window_name, cv2.WINDOW_NORMAL)
        if args.fullscreen:
            cv2.setWindowProperty(
                args.window_name,
                cv2.WND_PROP_FULLSCREEN,
                cv2.WINDOW_FULLSCREEN,
            )
        else:
            cv2.resizeWindow(args.window_name, sensor_spec.width, sensor_spec.height)

    try:
        while not should_stop:
            if args.display_mode == "sensor_preview":
                assert image_queue is not None
                assert sensor is not None
                try:
                    image = image_queue.get(timeout=2.0)
                except queue.Empty as exc:
                    raise RuntimeError("timed out waiting for camera frames") from exc

                frame = decode_bgr(image)
                cv2.imshow(args.window_name, frame)
                key = cv2.waitKey(1) & 0xFF
                if key in (27, ord("q")):
                    break

                if spectator is not None:
                    spectator.set_transform(sensor.get_transform())

                processed_frames += 1
                if processed_frames % 90 == 0:
                    elapsed = max(time.monotonic() - started_at, 1e-6)
                    preview_fps = processed_frames / elapsed
                    print(
                        f"preview fps={preview_fps:.2f} frames={processed_frames}",
                        flush=True,
                    )
                continue

            assert spectator is not None
            current_vehicle = ego_vehicle
            try:
                vehicle_transform = current_vehicle.get_transform()
            except RuntimeError:
                current_vehicle = wait_for_vehicle_by_role(
                    world,
                    args.role_name,
                    timeout_seconds=max(1.0, args.wait_for_role_seconds),
                )
                if current_vehicle is None:
                    raise RuntimeError(
                        f"role '{args.role_name}' disappeared and could not be reacquired"
                    )
                ego_vehicle = current_vehicle
                vehicle_transform = current_vehicle.get_transform()
            spectator.set_transform(build_follow_camera_transform(vehicle_transform, sensor_spec))
            processed_frames += 1
            if processed_frames % 180 == 0:
                elapsed = max(time.monotonic() - started_at, 1e-6)
                follow_fps = processed_frames / elapsed
                print(
                    f"native_follow loop_hz={follow_fps:.2f} updates={processed_frames}",
                    flush=True,
                )
            time.sleep(max(0.0, 1.0 / max(1.0, float(args.follow_rate_hz))))
    finally:
        try:
            if sensor is not None:
                sensor.stop()
        except Exception:
            pass
        try:
            if sensor is not None:
                sensor.destroy()
        except Exception:
            pass
        for actor in traffic_actors:
            try:
                actor.destroy()
            except Exception:
                pass
        if spawned_ego:
            try:
                ego_vehicle.destroy()
            except Exception:
                pass
        if args.display_mode == "sensor_preview":
            cv2.destroyAllWindows()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
