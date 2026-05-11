#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass
from typing import Any
from urllib import error, request


@dataclass
class SmokeContext:
    base_url: str
    timeout_seconds: int
    active_run_id: str | None = None


def api_request(
    base_url: str,
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
    *,
    timeout_seconds: int,
) -> tuple[int, Any]:
    data = None
    headers: dict[str, str] = {}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = request.Request(f"{base_url}{path}", data=data, headers=headers, method=method)
    try:
        with request.urlopen(req, timeout=timeout_seconds) as resp:
            body = resp.read()
            content_type = resp.headers.get("Content-Type", "")
            if "application/json" in content_type:
                return resp.status, json.loads(body.decode("utf-8"))
            return resp.status, body
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{method} {path} failed with HTTP {exc.code}: {detail}") from exc


def wait_for_run_status(
    ctx: SmokeContext,
    run_id: str,
    *,
    allowed_statuses: set[str],
    terminal_failures: set[str],
    timeout_seconds: int,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    last_payload: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        _, payload = api_request(
            ctx.base_url,
            "GET",
            f"/runs/{run_id}",
            timeout_seconds=ctx.timeout_seconds,
        )
        last_payload = payload["data"]
        status = str(last_payload["status"])
        print(f"[remote-smoke] run {run_id} status={status}", flush=True)
        if status in allowed_statuses:
            return last_payload
        if status in terminal_failures:
            raise RuntimeError(f"run {run_id} entered unexpected terminal state {status}")
        time.sleep(1)
    raise RuntimeError(
        f"run {run_id} did not reach any of {sorted(allowed_statuses)} within {timeout_seconds}s; "
        f"last_status={None if last_payload is None else last_payload['status']}"
    )


def wait_for_runtime_control(
    ctx: SmokeContext,
    run_id: str,
    field: str,
    expected_status: str,
    *,
    timeout_seconds: int,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    last_payload: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        _, payload = api_request(
            ctx.base_url,
            "GET",
            f"/runs/{run_id}/environment",
            timeout_seconds=ctx.timeout_seconds,
        )
        runtime_control = payload["data"]["runtime_control"]
        control_state = runtime_control[field]
        last_payload = control_state
        print(
            f"[remote-smoke] run {run_id} {field} status={control_state.get('status')}",
            flush=True,
        )
        if str(control_state.get("status")) == expected_status:
            return control_state
        time.sleep(1)

    raise RuntimeError(
        f"run {run_id} {field} did not reach {expected_status} within {timeout_seconds}s; "
        f"last_state={last_payload}"
    )


def wait_for_run_event(
    ctx: SmokeContext,
    run_id: str,
    *,
    event_types: set[str],
    timeout_seconds: int,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    last_events: list[dict[str, Any]] = []
    while time.monotonic() < deadline:
        _, payload = api_request(
            ctx.base_url,
            "GET",
            f"/runs/{run_id}/events",
            timeout_seconds=ctx.timeout_seconds,
        )
        events = payload["data"]
        last_events = events if isinstance(events, list) else []
        for event in reversed(last_events):
            event_type = str(event.get("event_type") or "")
            if event_type in event_types:
                print(f"[remote-smoke] run {run_id} event={event_type}", flush=True)
                return event
        time.sleep(1)

    raise RuntimeError(
        f"run {run_id} did not emit any of {sorted(event_types)} within {timeout_seconds}s; "
        f"last_event_types={[event.get('event_type') for event in last_events[-5:]]}"
    )


def wait_for_sensor_capture_evidence(
    ctx: SmokeContext,
    run_id: str,
    *,
    timeout_seconds: int,
    min_saved_frames: int = 1,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    last_payload: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        _, payload = api_request(
            ctx.base_url,
            "GET",
            f"/runs/{run_id}/environment",
            timeout_seconds=ctx.timeout_seconds,
        )
        control_state = payload["data"]["runtime_control"]["sensor_capture"]
        last_payload = control_state
        saved_frames = int(control_state.get("saved_frames") or 0)
        manifest = control_state.get("manifest")
        sensor_outputs = control_state.get("sensor_outputs") or []
        print(
            f"[remote-smoke] run {run_id} sensor_capture evidence frames={saved_frames}",
            flush=True,
        )
        if manifest and sensor_outputs and saved_frames >= min_saved_frames:
            return control_state
        time.sleep(1)

    raise RuntimeError(
        f"run {run_id} sensor capture did not produce manifest/data within {timeout_seconds}s; "
        f"last_state={last_payload}"
    )


def smoke_basic(ctx: SmokeContext) -> None:
    status, payload = api_request(ctx.base_url, "GET", "/healthz", timeout_seconds=ctx.timeout_seconds)
    if status != 200 or payload.get("status") != "ok":
        raise RuntimeError(f"/healthz returned unexpected payload: {payload}")
    print("[remote-smoke] /healthz ok", flush=True)

    status, payload = api_request(
        ctx.base_url,
        "GET",
        "/system/status",
        timeout_seconds=ctx.timeout_seconds,
    )
    if status != 200 or not payload.get("success"):
        raise RuntimeError(f"/system/status returned unexpected payload: {payload}")
    if not payload["data"]["frontend"]["bundle_present"]:
        raise RuntimeError("frontend bundle is missing on remote /ui")
    print("[remote-smoke] /system/status ok", flush=True)

    status, body = api_request(ctx.base_url, "GET", "/ui", timeout_seconds=ctx.timeout_seconds)
    if status != 200 or b"<html" not in body.lower():
        raise RuntimeError("/ui did not return an html document")
    print("[remote-smoke] /ui ok", flush=True)


def launch_short_free_drive(
    ctx: SmokeContext,
    *,
    with_sensor_profile: bool,
    num_vehicles: int = 0,
    num_walkers: int = 0,
    traffic_seed: int = 7,
) -> str:
    payload: dict[str, Any] = {
        "scenario_id": "free_drive_sensor_collection",
        "map_name": "Town01",
        "weather": {"preset": "ClearNoon"},
        "traffic": {
            "num_vehicles": num_vehicles,
            "num_walkers": num_walkers,
            "seed": traffic_seed,
        },
        "template_params": {"targetSpeedMps": 8.0},
        "timeout_seconds": 35,
        "auto_start": True,
        "metadata": {
            "author": "remote-smoke",
            "tags": ["smoke"],
            "description": "remote smoke run",
        },
    }
    if with_sensor_profile:
        payload["sensor_profile_name"] = "front_rgb"

    _, response = api_request(
        ctx.base_url,
        "POST",
        "/scenarios/launch",
        payload,
        timeout_seconds=ctx.timeout_seconds,
    )
    run_id = str(response["data"]["run_id"])
    ctx.active_run_id = run_id
    print(f"[remote-smoke] created run {run_id}", flush=True)
    return run_id


def launch_core_native_run(ctx: SmokeContext) -> str:
    payload = {
        "descriptor": {
            "version": 1,
            "scenario_name": "free_drive_sensor_collection",
            "map_name": "Town01",
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
                "enabled": False,
                "num_vehicles": 0,
                "num_walkers": 0,
                "seed": 7,
                "injection_mode": "disabled",
            },
            "sensors": {"enabled": False, "auto_start": False, "sensors": []},
            "termination": {"timeout_seconds": 20, "success_condition": "timeout"},
            "recorder": {"enabled": False},
            "debug": {"viewer_friendly": False},
            "metadata": {
                "author": "remote-smoke",
                "tags": ["smoke", "native_core"],
                "description": "remote smoke core native run",
            },
        }
    }
    _, response = api_request(
        ctx.base_url,
        "POST",
        "/runs",
        payload,
        timeout_seconds=ctx.timeout_seconds,
    )
    run_id = str(response["data"]["run_id"])
    ctx.active_run_id = run_id
    print(f"[remote-smoke] created core run {run_id}", flush=True)
    api_request(
        ctx.base_url,
        "POST",
        f"/runs/{run_id}/start",
        timeout_seconds=ctx.timeout_seconds,
    )
    return run_id


def stop_run_best_effort(ctx: SmokeContext, run_id: str) -> None:
    try:
        api_request(
            ctx.base_url,
            "POST",
            f"/runs/{run_id}/stop",
            timeout_seconds=ctx.timeout_seconds,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"[remote-smoke] stop request failed for {run_id}: {exc}", flush=True)


def smoke_scenario(ctx: SmokeContext) -> None:
    expected_vehicle_count = 2
    expected_walker_count = 1
    expected_seed = 21
    run_id = launch_short_free_drive(
        ctx,
        with_sensor_profile=False,
        num_vehicles=expected_vehicle_count,
        num_walkers=expected_walker_count,
        traffic_seed=expected_seed,
    )
    wait_for_run_status(
        ctx,
        run_id,
        allowed_statuses={"RUNNING"},
        terminal_failures={"FAILED", "CANCELED", "COMPLETED"},
        timeout_seconds=45,
    )
    background_event = wait_for_run_event(
        ctx,
        run_id,
        event_types={"BACKGROUND_TRAFFIC_READY", "BACKGROUND_TRAFFIC_PARTIAL"},
        timeout_seconds=45,
    )
    background_payload = background_event.get("payload", {})
    if (
        int(background_payload.get("requested_vehicle_count") or -1) != expected_vehicle_count
        or int(background_payload.get("requested_walker_count") or -1) != expected_walker_count
        or int(background_payload.get("seed") or -1) != expected_seed
    ):
        raise RuntimeError(
            f"background traffic payload mismatch for {run_id}: {background_payload}"
        )
    if (
        int(background_payload.get("spawned_vehicle_count") or 0) < expected_vehicle_count
        or int(background_payload.get("spawned_walker_count") or 0) < expected_walker_count
    ):
        raise RuntimeError(
            f"background traffic did not fully spawn in formal env: {background_payload}"
        )
    stop_run_best_effort(ctx, run_id)
    wait_for_run_status(
        ctx,
        run_id,
        allowed_statuses={"COMPLETED", "CANCELED"},
        terminal_failures={"FAILED"},
        timeout_seconds=45,
    )
    print(f"[remote-smoke] scenario smoke completed for {run_id}", flush=True)
    ctx.active_run_id = None


def smoke_core(ctx: SmokeContext) -> None:
    run_id = launch_core_native_run(ctx)
    wait_for_run_event(
        ctx,
        run_id,
        event_types={"EGO_SPAWNED"},
        timeout_seconds=45,
    )
    run_payload = wait_for_run_status(
        ctx,
        run_id,
        allowed_statuses={"RUNNING", "COMPLETED"},
        terminal_failures={"FAILED", "CANCELED"},
        timeout_seconds=45,
    )
    if str(run_payload["status"]) == "RUNNING":
        stop_run_best_effort(ctx, run_id)
        run_payload = wait_for_run_status(
            ctx,
            run_id,
            allowed_statuses={"COMPLETED", "CANCELED"},
            terminal_failures={"FAILED"},
            timeout_seconds=45,
        )
    if int(run_payload.get("spawned_actors_count") or 0) < 1:
        raise RuntimeError(f"core smoke run did not spawn hero actor: {run_payload}")
    print(f"[remote-smoke] core smoke completed for {run_id}", flush=True)
    ctx.active_run_id = None


def smoke_capture(ctx: SmokeContext) -> None:
    expected_vehicle_count = 2
    expected_walker_count = 1
    expected_seed = 21
    run_id = launch_short_free_drive(
        ctx,
        with_sensor_profile=True,
        num_vehicles=expected_vehicle_count,
        num_walkers=expected_walker_count,
        traffic_seed=expected_seed,
    )
    wait_for_run_status(
        ctx,
        run_id,
        allowed_statuses={"RUNNING"},
        terminal_failures={"FAILED", "CANCELED", "COMPLETED"},
        timeout_seconds=45,
    )
    background_event = wait_for_run_event(
        ctx,
        run_id,
        event_types={"BACKGROUND_TRAFFIC_READY", "BACKGROUND_TRAFFIC_PARTIAL"},
        timeout_seconds=45,
    )
    background_payload = background_event.get("payload", {})
    if (
        int(background_payload.get("requested_vehicle_count") or -1) != expected_vehicle_count
        or int(background_payload.get("requested_walker_count") or -1) != expected_walker_count
        or int(background_payload.get("seed") or -1) != expected_seed
    ):
        raise RuntimeError(
            f"background traffic payload mismatch for {run_id}: {background_payload}"
        )
    wait_for_runtime_control(
        ctx,
        run_id,
        "recorder",
        "RUNNING",
        timeout_seconds=30,
    )
    api_request(
        ctx.base_url,
        "POST",
        f"/runs/{run_id}/sensor-capture/start",
        timeout_seconds=ctx.timeout_seconds,
    )
    wait_for_runtime_control(
        ctx,
        run_id,
        "sensor_capture",
        "RUNNING",
        timeout_seconds=45,
    )
    sensor_capture_state = wait_for_sensor_capture_evidence(
        ctx,
        run_id,
        timeout_seconds=45,
        min_saved_frames=1,
    )
    try:
        status, frame = api_request(
            ctx.base_url,
            "GET",
            f"/runs/{run_id}/viewer/frame?view=third_person",
            timeout_seconds=max(ctx.timeout_seconds, 10),
        )
        if status != 200 or not isinstance(frame, bytes) or len(frame) == 0:
            raise RuntimeError(
                f"viewer frame request returned unexpected payload for {run_id}"
            )
    except Exception as exc:  # noqa: BLE001
        print(
            f"[remote-smoke] WARNING viewer frame unavailable for {run_id}: {exc}",
            flush=True,
        )
    else:
        print(
            f"[remote-smoke] viewer frame ok for {run_id} ({len(frame)} bytes)",
            flush=True,
        )
    download_url = str(sensor_capture_state.get("download_url") or "").strip()
    if not download_url:
        raise RuntimeError(f"sensor capture download url is missing for {run_id}")
    status, archive_bytes = api_request(
        ctx.base_url,
        "GET",
        download_url,
        timeout_seconds=max(ctx.timeout_seconds, 45),
    )
    if status != 200 or not isinstance(archive_bytes, bytes) or len(archive_bytes) == 0:
        raise RuntimeError(
            f"sensor capture download returned unexpected payload for {run_id}"
        )
    print(
        f"[remote-smoke] sensor capture download ok for {run_id} ({len(archive_bytes)} bytes)",
        flush=True,
    )

    api_request(
        ctx.base_url,
        "POST",
        f"/runs/{run_id}/sensor-capture/stop",
        timeout_seconds=ctx.timeout_seconds,
    )
    wait_for_runtime_control(
        ctx,
        run_id,
        "sensor_capture",
        "STOPPED",
        timeout_seconds=30,
    )
    stop_run_best_effort(ctx, run_id)
    wait_for_run_status(
        ctx,
        run_id,
        allowed_statuses={"COMPLETED", "CANCELED"},
        terminal_failures={"FAILED"},
        timeout_seconds=45,
    )
    print(f"[remote-smoke] capture smoke completed for {run_id}", flush=True)
    ctx.active_run_id = None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Smoke-test a deployed remote CARLA web platform")
    parser.add_argument(
        "--base-url",
        default="http://192.168.110.151:8000",
        help="FastAPI base URL, default: %(default)s",
    )
    parser.add_argument(
        "--mode",
        choices=("basic", "core", "scenario", "capture"),
        default="basic",
        help="Smoke mode, default: %(default)s",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=20,
        help="Per-request timeout in seconds, default: %(default)s",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    ctx = SmokeContext(
        base_url=args.base_url.rstrip("/"),
        timeout_seconds=args.timeout_seconds,
    )
    try:
        smoke_basic(ctx)
        if args.mode == "core":
            smoke_core(ctx)
        elif args.mode == "scenario":
            smoke_scenario(ctx)
        elif args.mode == "capture":
            smoke_capture(ctx)
    except Exception as exc:  # noqa: BLE001
        if ctx.active_run_id is not None:
            stop_run_best_effort(ctx, ctx.active_run_id)
        print(f"[remote-smoke] FAILED: {exc}", file=sys.stderr, flush=True)
        return 1

    print(f"[remote-smoke] PASS mode={args.mode}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
