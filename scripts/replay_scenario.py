#!/usr/bin/env python3
"""Replay a CARLA recording with sensor(s) attached to the ego vehicle.

Usage:
    # Replay with fullscreen display
    python3 replay_scenario.py recording.log

    # Generate sensor data only (no display)
    python3 replay_scenario.py recording.log --no-display --output /tmp/frames

    # Custom camera settings
    python3 replay_scenario.py recording.log --width 1920 --height 1080 --fov 90

Architecture:
    replay control:  synchronous mode + world.tick() drives simulation
    sensor module:   camera attached to ego, callback fills frame queue
    display module:  OpenCV fullscreen (optional, --no-display to skip)
"""
import carla
import numpy as np
import cv2
import queue
import time
import sys
import os
import signal
import argparse

RUNNING = True


def stop_handler(sig, frame):
    global RUNNING
    RUNNING = False


signal.signal(signal.SIGINT, stop_handler)
signal.signal(signal.SIGTERM, stop_handler)


def wait_for_hero(world, timeout=15.0):
    """Wait for a vehicle with role_name='hero' to appear."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        for a in world.get_actors().filter('vehicle.*'):
            if a.attributes.get('role_name') == 'hero':
                return a
        time.sleep(0.05)
    return None


def parse_args():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('recording', help='Path to .log file')
    parser.add_argument('--duration', type=float, default=0.0,
                        help='Replay duration seconds (0=full)')
    parser.add_argument('--start', type=float, default=0.0,
                        help='Replay start time in seconds')
    parser.add_argument('--host', default='localhost')
    parser.add_argument('--port', type=int, default=2000)
    # Camera
    parser.add_argument('--width', type=int, default=1280)
    parser.add_argument('--height', type=int, default=720)
    parser.add_argument('--fov', type=float, default=100.0)
    parser.add_argument('--cam-x', type=float, default=1.5)
    parser.add_argument('--cam-z', type=float, default=1.7)
    parser.add_argument('--cam-pitch', type=float, default=-5.0)
    # Display
    parser.add_argument('--no-display', action='store_true',
                        help='Skip display, only generate sensor data')
    parser.add_argument('--output', default='',
                        help='Save frames to directory (PNG)')
    # Simulation
    parser.add_argument('--delta', type=float, default=0.05,
                        help='Fixed delta seconds (controls sim speed)')
    return parser.parse_args()


def main():
    global RUNNING
    args = parse_args()

    client = carla.Client(args.host, args.port)
    client.set_timeout(30.0)
    world = client.get_world()

    # --- Synchronous mode for deterministic replay ---
    settings = world.get_settings()
    settings.synchronous_mode = True
    settings.fixed_delta_seconds = args.delta
    world.apply_settings(settings)

    # Start replay (need one tick to process the command)
    print(f"Replay: {args.recording}")
    print(f"  start={args.start}s duration={args.duration}s delta={args.delta}s")
    result = client.replay_file(
        args.recording, args.start, args.duration, 0, False)
    for line in result.strip().split('\n')[:3]:
        print(f"  {line}")
    world.tick()

    # Wait for ego vehicle
    ego = wait_for_hero(world)
    if not ego:
        print("ERROR: No hero vehicle found")
        client.stop_replayer(True)
        settings.synchronous_mode = False
        world.apply_settings(settings)
        return 1
    print(f"Ego: {ego.type_id} (id={ego.id})")

    # --- Sensor module: attach camera ---
    bp_lib = world.get_blueprint_library()
    cam_bp = bp_lib.find('sensor.camera.rgb')
    cam_bp.set_attribute('image_size_x', str(args.width))
    cam_bp.set_attribute('image_size_y', str(args.height))
    cam_bp.set_attribute('fov', str(args.fov))

    cam_transform = carla.Transform(
        carla.Location(x=args.cam_x, z=args.cam_z),
        carla.Rotation(pitch=args.cam_pitch),
    )
    camera = world.spawn_actor(cam_bp, cam_transform, attach_to=ego)
    print(f"Camera: {args.width}x{args.height} FOV={args.fov}")

    # Frame synchronization queue
    image_queue = queue.Queue()
    camera.listen(image_queue.put)

    # --- Display module (optional) ---
    if not args.no_display:
        cv2.namedWindow('CARLA Replay', cv2.WINDOW_NORMAL)
        cv2.setWindowProperty(
            'CARLA Replay', cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)

    if args.output:
        os.makedirs(args.output, exist_ok=True)

    print("Running..." + (" (no display)" if args.no_display else
                          " Press 'q'/ESC to stop."))
    start_time = time.time()
    frames = 0

    while RUNNING:
        # Tick the world to advance replay by one step
        world.tick()

        # Get the sensor frame for this tick
        try:
            image = image_queue.get(timeout=2.0)
        except queue.Empty:
            # Ego might have been destroyed (replay ended)
            try:
                if not ego.is_alive:
                    print("Replay complete.")
                    break
            except RuntimeError:
                print("Replay complete.")
                break
            continue

        frames += 1
        arr = np.frombuffer(image.raw_data, dtype=np.uint8)
        arr = arr.reshape((args.height, args.width, 4))[:, :, :3]

        # Save to disk if requested
        if args.output:
            cv2.imwrite(
                os.path.join(args.output, f"frame_{frames:06d}.png"), arr)

        # Display
        if not args.no_display:
            cv2.imshow('CARLA Replay', arr)
            key = cv2.waitKey(1) & 0xFF
            if key == ord('q') or key == 27:
                break

        # Check duration
        if args.duration > 0:
            sim_time = frames * args.delta
            if sim_time >= args.duration:
                break

    elapsed = time.time() - start_time
    fps = frames / max(elapsed, 0.01)
    print(f"Done: {frames} frames in {elapsed:.1f}s = {fps:.1f} FPS")

    # Cleanup
    camera.stop()
    camera.destroy()
    client.stop_replayer(True)
    settings.synchronous_mode = False
    settings.fixed_delta_seconds = 0.0
    world.apply_settings(settings)
    if not args.no_display:
        cv2.destroyAllWindows()
    return 0


if __name__ == "__main__":
    sys.exit(main())
