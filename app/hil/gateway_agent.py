from __future__ import annotations

import argparse
import json
import os
import re
import socket
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib import error, parse, request

from app.hil.pi_capture import (
    clear_capture_runtime,
    collect_frame_records,
    is_process_running,
    launch_capture_process,
    read_capture_runtime,
    stop_capture_process,
)

AGENT_VERSION = "0.1.0"
DEFAULT_STATE_DIR_NAME = "pi_gateway"


@dataclass(frozen=True)
class GatewayAgentSettings:
    api_base_url: str
    gateway_id: str
    gateway_name: str
    input_video_device: str
    media_device: str
    hdmi_status_device: str
    heartbeat_interval_seconds: float
    api_timeout_seconds: float
    state_dir: Path
    gadget_state_file: Path
    bridge_state_file: Path
    current_run_id_file: Path
    capture_runtime_file: Path
    dut_result_file: Path
    agent_version: str
    video_input_modes: tuple[str, ...]
    dut_output_modes: tuple[str, ...]
    result_ingest_modes: tuple[str, ...]
    once: bool = False


def parse_args(argv: list[str] | None = None) -> GatewayAgentSettings:
    parser = argparse.ArgumentParser(description="DuckPark Pi gateway agent")
    parser.add_argument("--api-base-url", default=os.getenv("PI_GATEWAY_API_BASE_URL"))
    parser.add_argument("--gateway-id", default=os.getenv("PI_GATEWAY_ID"))
    parser.add_argument("--gateway-name", default=os.getenv("PI_GATEWAY_NAME"))
    parser.add_argument(
        "--input-video-device",
        default=os.getenv("PI_GATEWAY_INPUT_VIDEO_DEVICE", "/dev/video0"),
    )
    parser.add_argument(
        "--media-device",
        default=os.getenv("PI_GATEWAY_MEDIA_DEVICE"),
    )
    parser.add_argument(
        "--hdmi-status-device",
        default=os.getenv("PI_GATEWAY_HDMI_STATUS_DEVICE", "/dev/v4l-subdev2"),
    )
    parser.add_argument(
        "--heartbeat-interval",
        type=float,
        default=float(os.getenv("PI_GATEWAY_HEARTBEAT_INTERVAL_SECONDS", "5")),
    )
    parser.add_argument(
        "--api-timeout",
        type=float,
        default=float(os.getenv("PI_GATEWAY_API_TIMEOUT_SECONDS", "3")),
    )
    parser.add_argument(
        "--state-dir",
        default=os.getenv("PI_GATEWAY_STATE_DIR"),
    )
    parser.add_argument(
        "--dut-result-file",
        default=os.getenv("PI_GATEWAY_DUT_RESULT_FILE"),
    )
    parser.add_argument(
        "--agent-version",
        default=os.getenv("PI_GATEWAY_AGENT_VERSION", AGENT_VERSION),
    )
    parser.add_argument(
        "--video-input-modes",
        default=os.getenv("PI_GATEWAY_VIDEO_INPUT_MODES", "hdmi_x1301,frame_stream"),
    )
    parser.add_argument(
        "--dut-output-modes",
        default=os.getenv("PI_GATEWAY_DUT_OUTPUT_MODES", "uvc_gadget"),
    )
    parser.add_argument(
        "--result-ingest-modes",
        default=os.getenv("PI_GATEWAY_RESULT_INGEST_MODES", "http_push"),
    )
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args(argv)

    if not args.api_base_url:
        parser.error("--api-base-url is required")
    if not args.gateway_id:
        parser.error("--gateway-id is required")
    if not args.gateway_name:
        parser.error("--gateway-name is required")

    project_root = Path(__file__).resolve().parents[2]
    default_state_dir = project_root / "run_data" / DEFAULT_STATE_DIR_NAME
    state_dir = Path(args.state_dir or default_state_dir)
    state_dir.mkdir(parents=True, exist_ok=True)
    dut_result_file = (
        Path(args.dut_result_file) if args.dut_result_file else state_dir / "dut_result.json"
    )
    requested_media_device = (args.media_device or "").strip()
    media_device = requested_media_device or find_media_device("rp1-cfe") or "/dev/media0"

    return GatewayAgentSettings(
        api_base_url=args.api_base_url.rstrip("/"),
        gateway_id=args.gateway_id.strip(),
        gateway_name=args.gateway_name.strip(),
        input_video_device=args.input_video_device.strip(),
        media_device=media_device,
        hdmi_status_device=args.hdmi_status_device.strip(),
        heartbeat_interval_seconds=max(args.heartbeat_interval, 1.0),
        api_timeout_seconds=max(args.api_timeout, 1.0),
        state_dir=state_dir,
        gadget_state_file=state_dir / "gadget_state.json",
        bridge_state_file=state_dir / "bridge_state.json",
        current_run_id_file=state_dir / "current_run_id",
        capture_runtime_file=state_dir / "capture_runtime.json",
        dut_result_file=dut_result_file,
        agent_version=args.agent_version.strip(),
        video_input_modes=parse_csv(args.video_input_modes),
        dut_output_modes=parse_csv(args.dut_output_modes),
        result_ingest_modes=parse_csv(args.result_ingest_modes),
        once=args.once,
    )


def parse_csv(raw_value: str | None) -> tuple[str, ...]:
    if not raw_value:
        return tuple()
    return tuple(item.strip() for item in raw_value.split(",") if item.strip())


def now_utc_iso8601() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def read_json_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def read_text_file(path: Path) -> str | None:
    if not path.exists():
        return None
    try:
        return path.read_text(encoding="utf-8").strip() or None
    except OSError:
        return None


def is_module_loaded(module_name: str) -> bool:
    try:
        with Path("/proc/modules").open("r", encoding="utf-8") as handle:
            for line in handle:
                if line.split(" ", 1)[0] == module_name:
                    return True
    except OSError:
        return False
    return False


def list_udc_names() -> list[str]:
    udc_root = Path("/sys/class/udc")
    if not udc_root.exists():
        return []
    return sorted(entry.name for entry in udc_root.iterdir())


def get_udc_state(udc_name: str | None) -> str | None:
    if not udc_name:
        return None
    state_path = Path("/sys/class/udc") / udc_name / "state"
    if not state_path.exists():
        return None
    try:
        return state_path.read_text(encoding="utf-8").strip() or None
    except OSError:
        return None


def run_command(command: list[str], timeout_seconds: float = 2.0) -> str | None:
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            check=False,
            text=True,
            timeout=timeout_seconds,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if completed.returncode != 0:
        return None
    return completed.stdout


def find_media_device(driver_name: str) -> str | None:
    for device in sorted(Path("/dev").glob("media*")):
        output = run_command(["media-ctl", "-p", "-d", str(device)], timeout_seconds=2.0)
        if not output:
            continue
        if re.search(
            rf"^(driver|model)\s+{re.escape(driver_name)}\s*$",
            output,
            flags=re.MULTILINE,
        ):
            return str(device)
    return None


def is_gadget_video_name(name: str | None) -> bool:
    if not name:
        return False
    normalized = name.strip().lower()
    if not normalized:
        return False
    return "gadget" in normalized or "uvc" in normalized


def find_gadget_video_device() -> str | None:
    for sysfs_device in sorted(Path("/sys/class/video4linux").glob("video*")):
        name_path = sysfs_device / "name"
        if not name_path.exists():
            continue
        try:
            name = name_path.read_text(encoding="utf-8", errors="ignore").replace("\x00", "")
        except OSError:
            continue
        if is_gadget_video_name(name):
            return f"/dev/{sysfs_device.name}"

    output = run_command(["v4l2-ctl", "--list-devices"])
    if not output:
        return None

    current_block: str | None = None
    for raw_line in output.splitlines():
        line = raw_line.rstrip()
        if not line:
            current_block = None
            continue
        if not raw_line.startswith("\t"):
            current_block = line
            continue
        if current_block and is_gadget_video_name(current_block):
            device = line.strip()
            if device.startswith("/dev/video"):
                return device
    return None


def probe_v4l2_device(device_path: str, prefix: str) -> dict[str, Any]:
    output = run_command(["v4l2-ctl", "-d", device_path, "--all"])
    if not output:
        return {}

    metrics: dict[str, Any] = {}
    card_type = re.search(r"Card type\s+:\s+(.+)", output)
    width_height = re.search(r"Width/Height\s+:\s+(\d+)/(\d+)", output)
    pixel_format = re.search(r"Pixel Format\s+:\s+'([^']+)'\s+\((.+)\)", output)

    if card_type:
        metrics[f"{prefix}_card_type"] = card_type.group(1).strip()
    if width_height:
        metrics[f"{prefix}_width"] = int(width_height.group(1))
        metrics[f"{prefix}_height"] = int(width_height.group(2))
    if pixel_format:
        metrics[f"{prefix}_pixel_format"] = pixel_format.group(1).strip()
        metrics[f"{prefix}_pixel_format_desc"] = pixel_format.group(2).strip()
    return metrics


def parse_tc358743_status(status_output: str) -> dict[str, Any]:
    metrics: dict[str, Any] = {}
    mapping = {
        "Cable detected (+5V power)": "hdmi_cable_detected",
        "DDC lines enabled": "hdmi_ddc_enabled",
        "Hotplug enabled": "hdmi_hotplug_enabled",
        "TMDS signal detected": "hdmi_tmds_signal_detected",
        "Stable sync signal": "hdmi_stable_sync_signal",
        "PHY PLL locked": "hdmi_phy_pll_locked",
        "PHY DE detected": "hdmi_phy_de_detected",
        "Transmit mode": "hdmi_transmit_mode",
        "Receive mode": "hdmi_receive_mode",
    }
    for label, metric_name in mapping.items():
        match = re.search(rf"{re.escape(label)}:\s+(yes|no)", status_output)
        if match:
            metrics[metric_name] = match.group(1) == "yes"

    configured_format = re.search(r"Configured format:\s+(.+)", status_output)
    input_color_space = re.search(r"Input color space:\s+(.+)", status_output)
    metrics["hdmi_no_video_detected"] = "No video detected" in status_output
    if configured_format:
        metrics["hdmi_configured_format"] = configured_format.group(1).strip()
    if input_color_space:
        metrics["hdmi_input_color_space"] = input_color_space.group(1).strip()

    video_detected = metrics.get("hdmi_tmds_signal_detected", False) and metrics.get(
        "hdmi_stable_sync_signal", False
    )
    metrics["hdmi_video_detected"] = video_detected
    return metrics


def detect_capture_link_enabled(media_device: str) -> bool | None:
    output = run_command(["media-ctl", "-p", "-d", media_device], timeout_seconds=2.0)
    if not output:
        return None
    match = re.search(
        r'-> "rp1-cfe-csi2_ch0":0 \[(?P<flags>[A-Z,]+)?\]',
        output,
    )
    if not match:
        return None
    flags = match.group("flags") or ""
    return "ENABLED" in flags.split(",")


def normalize_dut_result_payload(payload: dict[str, Any]) -> dict[str, Any]:
    metrics: dict[str, Any] = {}

    nested_metrics = payload.get("metrics")
    if isinstance(nested_metrics, dict):
        metrics.update(nested_metrics)

    for key, value in payload.items():
        if key == "metrics":
            continue
        if key == "status":
            metrics["dut_status"] = value
        elif key == "run_id":
            metrics["dut_run_id"] = value
        elif key == "received_at_utc":
            metrics["dut_received_at_utc"] = value
        elif key == "error_reason":
            metrics["dut_error_reason"] = value
        elif key == "model_name":
            metrics["dut_model_name"] = value
        elif key == "input_topic":
            metrics["dut_input_topic"] = value
        elif key == "output_topic":
            metrics["dut_output_topic"] = value
        elif key == "camera_device":
            metrics["dut_camera_device"] = value
        elif key == "source_host":
            metrics["dut_source_host"] = value
        else:
            metrics[key] = value

    return metrics


def read_dut_result_metrics(path: Path) -> dict[str, Any]:
    payload = read_json_file(path)
    if not payload:
        return {}
    return normalize_dut_result_payload(payload)


def detect_local_address(api_base_url: str) -> str | None:
    parsed = parse.urlparse(api_base_url)
    if not parsed.hostname:
        return None
    port = parsed.port
    if port is None:
        port = 443 if parsed.scheme == "https" else 80

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect((parsed.hostname, port))
            address = sock.getsockname()[0]
    except OSError:
        return None
    return address


def read_platform_model() -> str | None:
    model_path = Path("/proc/device-tree/model")
    if not model_path.exists():
        return None
    try:
        return model_path.read_text(encoding="utf-8", errors="ignore").replace("\x00", "").strip()
    except OSError:
        return None


def build_register_payload(
    settings: GatewayAgentSettings, address: str | None, metrics: dict[str, Any]
) -> dict[str, Any]:
    capabilities: dict[str, Any] = {
        "video_input_modes": list(settings.video_input_modes),
        "dut_output_modes": list(settings.dut_output_modes),
        "result_ingest_modes": list(settings.result_ingest_modes),
    }
    platform_model = read_platform_model()
    if platform_model:
        capabilities["platform_model"] = platform_model
    if metrics.get("gadget_driver"):
        capabilities["gadget_driver"] = metrics["gadget_driver"]

    return {
        "gateway_id": settings.gateway_id,
        "name": settings.gateway_name,
        "capabilities": capabilities,
        "agent_version": settings.agent_version,
        "address": address,
    }


def determine_gateway_status(metrics: dict[str, Any], current_run_id: str | None) -> str:
    if not metrics.get("udc_present", False):
        return "ERROR"
    if not metrics.get("input_device_exists", False):
        return "ERROR"
    # RTP-only / HTTP result pipelines can be healthy even when the optional UVC gadget
    # side is not attached. Treat the gateway as online when DUT telemetry is flowing.
    has_live_dut_result = bool(metrics.get("dut_received_at_utc"))
    if not has_live_dut_result:
        if not metrics.get("gadget_driver_loaded", False):
            return "ERROR"
        if not metrics.get("gadget_video_device_exists", False):
            return "ERROR"
    if current_run_id or metrics.get("active_capture_id"):
        return "BUSY"
    if str(metrics.get("dut_status") or "").upper() == "RUNNING":
        return "BUSY"
    return "READY"


def collect_gateway_metrics(settings: GatewayAgentSettings) -> tuple[dict[str, Any], str | None]:
    udc_names = list_udc_names()
    udc_name = udc_names[0] if udc_names else None
    udc_state = get_udc_state(udc_name)

    gadget_state = read_json_file(settings.gadget_state_file)
    bridge_state = read_json_file(settings.bridge_state_file)
    capture_runtime = read_capture_runtime(settings.capture_runtime_file) or {}
    dut_result_metrics = read_dut_result_metrics(settings.dut_result_file)
    current_run_id = read_text_file(settings.current_run_id_file)

    gadget_video_device = (
        gadget_state.get("gadget_video_device")
        or bridge_state.get("gadget_video_device")
        or find_gadget_video_device()
    )
    capture_link_enabled = detect_capture_link_enabled(settings.media_device)
    hdmi_status_output = run_command(
        ["v4l2-ctl", "-d", settings.hdmi_status_device, "--log-status"],
        timeout_seconds=3.0,
    )

    metrics: dict[str, Any] = {
        "captured_at_utc": now_utc_iso8601(),
        "udc_present": bool(udc_name),
        "udc_name": udc_name,
        "udc_state": udc_state or "missing",
        "host_connected": bool(udc_state and udc_state != "not attached"),
        "input_device": settings.input_video_device,
        "input_device_exists": Path(settings.input_video_device).exists(),
        "gadget_driver": gadget_state.get("gadget_driver", "g_webcam"),
        "gadget_driver_loaded": is_module_loaded(
            str(gadget_state.get("gadget_driver", "g_webcam"))
        ),
        "gadget_video_device": gadget_video_device,
        "gadget_video_device_exists": bool(
            gadget_video_device and Path(gadget_video_device).exists()
        ),
        "capture_link_enabled": capture_link_enabled,
        "media_device": settings.media_device,
        "hdmi_status_device": settings.hdmi_status_device,
        "active_capture_id": capture_runtime.get("capture_id"),
        "active_capture_pid": capture_runtime.get("pid"),
        "active_capture_save_dir": capture_runtime.get("save_dir"),
    }
    metrics.update(probe_v4l2_device(settings.input_video_device, "input"))
    if gadget_video_device:
        metrics.update(probe_v4l2_device(gadget_video_device, "gadget"))
    if hdmi_status_output:
        metrics.update(parse_tc358743_status(hdmi_status_output))
    metrics.update(gadget_state)
    metrics.update(bridge_state)
    metrics.update(dut_result_metrics)
    return metrics, current_run_id


def post_json(
    api_base_url: str,
    route: str,
    payload: dict[str, Any],
    timeout_seconds: float,
) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    req = request.Request(
        url=f"{api_base_url}{route}",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with request.urlopen(req, timeout=timeout_seconds) as response:
            response_text = response.read().decode("utf-8")
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"HTTP {exc.code} calling {route}: {detail or exc.reason}") from exc
    except error.URLError as exc:
        raise RuntimeError(f"Network error calling {route}: {exc.reason}") from exc

    try:
        parsed = json.loads(response_text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Invalid JSON from {route}: {response_text}") from exc

    if not parsed.get("success", False):
        raise RuntimeError(f"Platform rejected {route}: {parsed}")
    return parsed


def get_json(
    api_base_url: str,
    route: str,
    timeout_seconds: float,
    query_params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    url = f"{api_base_url}{route}"
    if query_params:
        normalized = {
            key: value for key, value in query_params.items() if value is not None and value != ""
        }
        if normalized:
            url = f"{url}?{parse.urlencode(normalized)}"

    req = request.Request(url=url, headers={"Accept": "application/json"}, method="GET")

    try:
        with request.urlopen(req, timeout=timeout_seconds) as response:
            response_text = response.read().decode("utf-8")
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"HTTP {exc.code} calling {route}: {detail or exc.reason}") from exc
    except error.URLError as exc:
        raise RuntimeError(f"Network error calling {route}: {exc.reason}") from exc

    try:
        parsed = json.loads(response_text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Invalid JSON from {route}: {response_text}") from exc

    if not parsed.get("success", False):
        raise RuntimeError(f"Platform rejected {route}: {parsed}")
    return parsed


def read_bridge_dimensions(bridge_state_file: Path) -> tuple[int | None, int | None]:
    bridge_state = read_json_file(bridge_state_file)
    width = bridge_state.get("capture_width")
    height = bridge_state.get("capture_height")
    try:
        return int(width), int(height)
    except (TypeError, ValueError):
        return None, None


def fetch_running_capture(settings: GatewayAgentSettings) -> dict[str, Any] | None:
    response = get_json(
        settings.api_base_url,
        "/captures",
        settings.api_timeout_seconds,
        query_params={
            "gateway_id": settings.gateway_id,
            "status": "RUNNING",
        },
    )
    captures = response.get("data", {}).get("captures", [])
    if not captures:
        return None
    captures.sort(key=lambda item: item.get("created_at_utc") or "")
    return captures[0]


def sync_capture_progress(
    settings: GatewayAgentSettings,
    runtime: dict[str, Any],
    status: str | None = None,
    error_reason: str | None = None,
) -> None:
    width, height = read_bridge_dimensions(settings.bridge_state_file)
    frames = collect_frame_records(runtime["save_dir"], width=width, height=height)
    payload: dict[str, Any] = {
        "saved_frames": len(frames),
        "frames": frames,
    }
    if status is not None:
        payload["status"] = status
    if error_reason is not None:
        payload["error_reason"] = error_reason
    post_json(
        settings.api_base_url,
        f"/captures/{runtime['capture_id']}/sync",
        payload,
        settings.api_timeout_seconds,
    )


def reconcile_capture_runtime(settings: GatewayAgentSettings) -> None:
    runtime = read_capture_runtime(settings.capture_runtime_file)
    desired_capture = fetch_running_capture(settings)

    if runtime and (
        desired_capture is None or desired_capture["capture_id"] != runtime["capture_id"]
    ):
        if is_process_running(int(runtime.get("pid", 0) or 0)):
            stop_capture_process(runtime)
        sync_capture_progress(settings, runtime)
        clear_capture_runtime(settings.capture_runtime_file)
        runtime = None

    if runtime is None and desired_capture is not None:
        if str(desired_capture.get("save_format", "")).lower() not in {"jpg", "png"}:
            sync_capture_progress(
                settings,
                {
                    "capture_id": desired_capture["capture_id"],
                    "save_dir": desired_capture["save_dir"],
                },
                status="FAILED",
                error_reason="Pi agent 当前仅支持 jpg/png 帧保存",
            )
            return

        project_root = Path(__file__).resolve().parents[2]
        runtime = launch_capture_process(
            project_root=project_root,
            runtime_path=settings.capture_runtime_file,
            capture=desired_capture,
            input_video_device=settings.input_video_device,
            media_device=settings.media_device,
            hdmi_status_device=settings.hdmi_status_device,
        )
        log(
            "capture process started "
            f"capture_id={runtime['capture_id']} pid={runtime['pid']} save_dir={runtime['save_dir']}"
        )

    if runtime is None:
        return

    pid = int(runtime.get("pid", 0) or 0)
    running = is_process_running(pid)

    if running:
        sync_capture_progress(settings, runtime, status="RUNNING")
        return

    frames = collect_frame_records(runtime["save_dir"])
    max_frames = int(runtime.get("max_frames", 0) or 0)
    if max_frames > 0 and len(frames) >= max_frames:
        sync_capture_progress(settings, runtime, status="COMPLETED")
        log(
            "capture process completed "
            f"capture_id={runtime['capture_id']} saved_frames={len(frames)}"
        )
    else:
        sync_capture_progress(
            settings,
            runtime,
            status="FAILED",
            error_reason="Pi capture process exited unexpectedly",
        )
        log(
            "capture process failed "
            f"capture_id={runtime['capture_id']} saved_frames={len(frames)}"
        )
    clear_capture_runtime(settings.capture_runtime_file)


def log(message: str) -> None:
    sys.stdout.write(f"{now_utc_iso8601()} {message}\n")
    sys.stdout.flush()


def run_agent(settings: GatewayAgentSettings) -> int:
    registered = False
    address = detect_local_address(settings.api_base_url)
    log(
        "gateway-agent start "
        f"gateway_id={settings.gateway_id} api={settings.api_base_url} input={settings.input_video_device}"
    )

    while True:
        metrics, current_run_id = collect_gateway_metrics(settings)
        status = determine_gateway_status(metrics, current_run_id)

        try:
            if not registered:
                register_payload = build_register_payload(settings, address, metrics)
                post_json(
                    settings.api_base_url,
                    "/gateways/register",
                    register_payload,
                    settings.api_timeout_seconds,
                )
                registered = True
                log(f"gateway registered gateway_id={settings.gateway_id}")

            reconcile_capture_runtime(settings)
            metrics, current_run_id = collect_gateway_metrics(settings)
            status = determine_gateway_status(metrics, current_run_id)

            heartbeat_payload = {
                "status": status,
                "metrics": metrics,
                "current_run_id": current_run_id,
            }
            post_json(
                settings.api_base_url,
                f"/gateways/{settings.gateway_id}/heartbeat",
                heartbeat_payload,
                settings.api_timeout_seconds,
            )
            log(
                "heartbeat sent "
                f"status={status} udc_state={metrics.get('udc_state')} "
                f"gadget={metrics.get('gadget_video_device') or '-'}"
            )
        except RuntimeError as exc:
            registered = False
            log(f"gateway-agent error: {exc}")

        if settings.once:
            return 0
        time.sleep(settings.heartbeat_interval_seconds)


def main(argv: list[str] | None = None) -> int:
    settings = parse_args(argv)
    return run_agent(settings)


if __name__ == "__main__":
    raise SystemExit(main())
