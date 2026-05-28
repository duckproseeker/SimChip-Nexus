"""Offline sensor data renderer.

Replays a CARLA recording in synchronous mode, attaches sensors to the ego
vehicle, and saves each frame to disk with timestamps for perfect multi-sensor
synchronization.
"""
from __future__ import annotations

import json
import subprocess
import textwrap
import threading
import uuid
from pathlib import Path
from typing import Any

from app.core.models import DatasetRecord, DatasetStatus, SensorConfig
from app.storage.dataset_store import get_dataset_store
from app.utils.time_utils import now_utc


CONTAINER = "ros2-dev"
CARLA_HOST = "localhost"
CARLA_PORT = 2000

_render_lock = threading.Lock()
_current_render: dict[str, Any] = {"dataset_id": None, "thread": None}


def is_rendering() -> bool:
    return _current_render["dataset_id"] is not None


def current_render_dataset_id() -> str | None:
    return _current_render["dataset_id"]


def start_render(
    dataset_id: str,
    scenario_log_path: str,
    sensor_configs: list[SensorConfig],
    output_dir: str,
    delta_seconds: float = 0.05,
    duration: float = 0.0,
    start_time: float = 0.0,
) -> str | None:
    """Start offline rendering in a background thread. Returns error message if busy."""
    with _render_lock:
        if _current_render["dataset_id"] is not None:
            return f"渲染进程忙，正在渲染 {_current_render['dataset_id']}，请等待完成后再试"
        _current_render["dataset_id"] = dataset_id

    t = threading.Thread(
        target=_run_render,
        args=(dataset_id, scenario_log_path, sensor_configs, output_dir, delta_seconds, duration, start_time),
        daemon=True,
    )
    _current_render["thread"] = t
    t.start()
    return None


def start_render_sync(
    dataset_id: str,
    scenario_log_path: str,
    sensor_configs: list[SensorConfig],
    output_dir: str,
    delta_seconds: float = 0.05,
    duration: float = 0.0,
    start_time: float = 0.0,
    weather_preset: str = "",
) -> None:
    """Run offline rendering synchronously (blocking). Caller must be in a background thread."""
    with _render_lock:
        if _current_render["dataset_id"] is not None:
            raise RuntimeError(f"渲染进程忙，正在渲染 {_current_render['dataset_id']}")
        _current_render["dataset_id"] = dataset_id
        _current_render["thread"] = threading.current_thread()

    try:
        _run_render(dataset_id, scenario_log_path, sensor_configs, output_dir, delta_seconds, duration, start_time, weather_preset)
    finally:
        pass  # _run_render's finally block handles lock release


def _run_render(
    dataset_id: str,
    scenario_log_path: str,
    sensor_configs: list[SensorConfig],
    output_dir: str,
    delta_seconds: float,
    duration: float,
    start_time: float,
    weather_preset: str = "",
) -> None:
    """Execute rendering inside the CARLA container."""
    store = get_dataset_store()
    store.update(dataset_id, status=DatasetStatus.RENDERING.value)

    # Generate the render script
    script = _build_render_script(
        scenario_log_path=scenario_log_path,
        sensor_configs=[s.model_dump() for s in sensor_configs],
        output_dir=output_dir,
        delta_seconds=delta_seconds,
        duration=duration,
        start_time=start_time,
        weather_preset=weather_preset,
    )

    try:
        proc = subprocess.run(
            ["docker", "exec", "-i", CONTAINER, "python3", "-c", script],
            capture_output=True,
            text=True,
            timeout=1800,
        )

        if proc.returncode != 0:
            store.update(
                dataset_id,
                status=DatasetStatus.FAILED.value,
                error_message=proc.stderr[-500:] if proc.stderr else "Unknown error",
            )
            return

        output_lines = proc.stdout.strip().split('\n')
        total_frames = 0
        for line in output_lines:
            if line.startswith("TOTAL_FRAMES="):
                total_frames = int(line.split("=")[1])

        store.update(
            dataset_id,
            status=DatasetStatus.COMPLETED.value,
            total_frames=total_frames,
            rendered_frames=total_frames,
        )

    except subprocess.TimeoutExpired:
        store.update(
            dataset_id,
            status=DatasetStatus.FAILED.value,
            error_message="Render timed out (600s)",
        )
    except Exception as e:
        store.update(
            dataset_id,
            status=DatasetStatus.FAILED.value,
            error_message=str(e)[:500],
        )
    finally:
        with _render_lock:
            _current_render["dataset_id"] = None
            _current_render["thread"] = None


def _build_render_script(
    scenario_log_path: str,
    sensor_configs: list[dict],
    output_dir: str,
    delta_seconds: float,
    duration: float,
    start_time: float,
    weather_preset: str = "",
) -> str:
    """Build the Python script that runs inside the CARLA container."""
    # Convert host path to CARLA container path (/recordings/ mount)
    carla_log_path = scenario_log_path
    host_recordings_dir = "/home/du/ros2-humble/src/SimChip-Nexus/run_data/scenario_recordings/"
    if carla_log_path.startswith(host_recordings_dir):
        carla_log_path = "/recordings/" + carla_log_path[len(host_recordings_dir):]

    configs_json = json.dumps(sensor_configs)
    return textwrap.dedent(f'''
import carla
import numpy as np
import os
import json
import time
import queue

CARLA_HOST = "localhost"
CARLA_PORT = 2000
SCENARIO_LOG = "{carla_log_path}"
OUTPUT_DIR = "{output_dir}"
DELTA = {delta_seconds}
DURATION = {duration}
START_TIME = {start_time}
WEATHER_PRESET = "{weather_preset}"
SENSOR_CONFIGS = json.loads('{configs_json}')

os.makedirs(OUTPUT_DIR, exist_ok=True)

client = carla.Client(CARLA_HOST, CARLA_PORT)
client.set_timeout(30.0)
world = client.get_world()

# Clean up any leftover actors from previous runs
cleanup_actors = [a for a in world.get_actors() if 'vehicle' in a.type_id or 'walker' in a.type_id or 'controller' in a.type_id]
if cleanup_actors:
    client.apply_batch([carla.command.DestroyActor(a.id) for a in cleanup_actors])
    print(f"Cleaned up {{len(cleanup_actors)}} leftover actors")

# Synchronous mode
settings = world.get_settings()
settings.synchronous_mode = True
settings.fixed_delta_seconds = DELTA
world.apply_settings(settings)

# Start replay normally (hero IS spawned by replay)
client.set_replayer_ignore_hero(False)
result = client.replay_file(SCENARIO_LOG, START_TIME, DURATION, 0, False)
print(f"Replay started: {{result[:80]}}")

# Tick to let replay spawn all actors
for _ in range(20):
    world.tick()

# Find the replay hero
ego = None
for _ in range(50):
    for a in world.get_actors().filter("vehicle.*"):
        if a.attributes.get("role_name") == "hero":
            ego = a
            break
    if ego:
        break
    world.tick()

if not ego:
    print("ERROR: No hero vehicle found in replay")
    settings.synchronous_mode = False
    settings.fixed_delta_seconds = None
    world.apply_settings(settings)
    exit(1)

print(f"Hero found: {{ego.type_id}} at {{ego.get_location()}}")

# Now set ignore_hero: replay stops overwriting hero's position,
# hero gets physics + autopilot (real collision with NPC actors)
client.set_replayer_ignore_hero(True)
ego.set_simulate_physics(True)

tm = client.get_trafficmanager(8010)
tm.set_synchronous_mode(True)
ego.set_autopilot(True, 8010)
tm.vehicle_percentage_speed_difference(ego, 0.0)
tm.auto_lane_change(ego, True)
tm.distance_to_leading_vehicle(ego, 3.0)

print(f"Hero physics enabled, autopilot on")

# Apply weather preset
if WEATHER_PRESET:
    weather_presets = {{
        "clear_noon": carla.WeatherParameters.ClearNoon,
        "clear_night": carla.WeatherParameters.ClearNight,
        "cloudy_noon": carla.WeatherParameters.CloudyNoon,
        "cloudy_night": carla.WeatherParameters.CloudyNight,
        "rain_noon": carla.WeatherParameters.MidRainyNoon,
        "rain_night": carla.WeatherParameters.MidRainSunset,
        "heavy_rain": carla.WeatherParameters.HardRainNoon,
        "fog_morning": carla.WeatherParameters(
            sun_altitude_angle=15.0, fog_density=70.0, fog_distance=10.0,
            fog_falloff=1.0, wetness=30.0, cloudiness=80.0),
        "fog_night": carla.WeatherParameters(
            sun_altitude_angle=-10.0, fog_density=80.0, fog_distance=5.0,
            fog_falloff=1.0, cloudiness=90.0),
        "wet_noon": carla.WeatherParameters.WetNoon,
        "wet_night": carla.WeatherParameters.WetCloudyNight,
    }}
    w_params = weather_presets.get(WEATHER_PRESET)
    if w_params:
        world.set_weather(w_params)
        print(f"Weather set: {{WEATHER_PRESET}}")
    else:
        print(f"Unknown weather preset: {{WEATHER_PRESET}}")

# Spawn sensors
sensors = []
queues = {{}}
for cfg in SENSOR_CONFIGS:
    sid = cfg["sensor_id"]
    stype = cfg["sensor_type"]
    attrs = cfg.get("attributes", {{}})
    tf = cfg.get("transform", {{}})

    bp = world.get_blueprint_library().find(stype)
    attr_remap = {{"width": "image_size_x", "height": "image_size_y"}}
    for k, v in attrs.items():
        carla_key = attr_remap.get(k, k)
        if bp.has_attribute(carla_key):
            bp.set_attribute(carla_key, str(int(v) if isinstance(v, float) and v == int(v) else v))

    transform = carla.Transform(
        carla.Location(x=tf.get("x", 0), y=tf.get("y", 0), z=tf.get("z", 1.7)),
        carla.Rotation(pitch=tf.get("pitch", 0), yaw=tf.get("yaw", 0), roll=tf.get("roll", 0)),
    )

    sensor = world.spawn_actor(bp, transform, attach_to=ego)
    q = queue.Queue()
    sensor.listen(q.put)
    sensors.append(sensor)
    queues[sid] = q

    sensor_dir = os.path.join(OUTPUT_DIR, sid)
    os.makedirs(sensor_dir, exist_ok=True)

# Render loop
timestamps = []
frame_idx = 0
max_frames = int(DURATION / DELTA) if DURATION > 0 else 999999

while frame_idx < max_frames:
    world.tick()
    frame_idx += 1

    try:
        if not ego.is_alive:
            break
    except RuntimeError:
        break

    sim_time = frame_idx * DELTA
    ts_entry = {{"frame": frame_idx, "sim_time": sim_time}}

    for cfg in SENSOR_CONFIGS:
        sid = cfg["sensor_id"]
        stype = cfg["sensor_type"]
        try:
            data = queues[sid].get(timeout=2.0)
        except queue.Empty:
            continue

        sensor_dir = os.path.join(OUTPUT_DIR, sid)
        fname = f"{{frame_idx:06d}}"

        if "camera" in stype:
            arr = np.frombuffer(data.raw_data, dtype=np.uint8)
            w = int(cfg["attributes"].get("image_size_x", 0) or cfg["attributes"].get("width", 1280))
            h = int(cfg["attributes"].get("image_size_y", 0) or cfg["attributes"].get("height", 720))
            arr = arr.reshape((h, w, 4))[:, :, :3]
            import cv2
            cv2.imwrite(os.path.join(sensor_dir, fname + ".jpg"), arr, [cv2.IMWRITE_JPEG_QUALITY, 90])
        elif "lidar" in stype:
            pts = np.frombuffer(data.raw_data, dtype=np.float32).reshape(-1, 4)
            pts.tofile(os.path.join(sensor_dir, fname + ".bin"))
        elif "radar" in stype:
            detections = [{{
                "velocity": d.velocity,
                "azimuth": d.azimuth,
                "altitude": d.altitude,
                "depth": d.depth,
            }} for d in data]
            with open(os.path.join(sensor_dir, fname + ".json"), "w") as f:
                json.dump(detections, f)

    timestamps.append(ts_entry)

    if DURATION > 0 and sim_time >= DURATION:
        break

# Save metadata
metadata = {{
    "total_frames": frame_idx,
    "delta_seconds": DELTA,
    "duration_seconds": frame_idx * DELTA,
    "sensor_configs": SENSOR_CONFIGS,
}}
with open(os.path.join(OUTPUT_DIR, "metadata.json"), "w") as f:
    json.dump(metadata, f, indent=2)

with open(os.path.join(OUTPUT_DIR, "timestamps.csv"), "w") as f:
    f.write("frame,sim_time\\n")
    for ts in timestamps:
        f.write(f"{{ts['frame']}},{{ts['sim_time']:.4f}}\\n")

# Cleanup
for s in sensors:
    s.stop()
    s.destroy()
try:
    ego.set_autopilot(False, 8010)
    client.set_replayer_ignore_hero(False)
    client.stop_replayer(True)
    settings.synchronous_mode = False
    settings.fixed_delta_seconds = None
    world.apply_settings(settings)
    tm.set_synchronous_mode(False)
except Exception:
    pass

print(f"TOTAL_FRAMES={{frame_idx}}")
print(f"Done: {{frame_idx}} frames saved to {{OUTPUT_DIR}}")
''').strip()
