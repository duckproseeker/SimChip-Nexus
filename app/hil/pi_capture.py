from __future__ import annotations

import json
import os
import signal
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.utils.file_utils import ensure_dir
from app.utils.time_utils import now_utc


def read_capture_runtime(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def write_capture_runtime(path: Path, payload: dict[str, Any]) -> None:
    ensure_dir(path.parent)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def clear_capture_runtime(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        return


def build_capture_command(
    project_root: Path,
    save_dir: Path,
    save_format: str,
    sample_fps: float,
    max_frames: int,
    input_video_device: str,
    media_device: str,
    hdmi_status_device: str,
) -> list[str]:
    return [
        "bash",
        str(project_root / "scripts" / "start_pi_frame_capture.sh"),
        "--save-dir",
        str(save_dir),
        "--save-format",
        save_format,
        "--sample-fps",
        str(sample_fps),
        "--max-frames",
        str(max_frames),
        "--input-video-device",
        input_video_device,
        "--media-device",
        media_device,
        "--hdmi-status-device",
        hdmi_status_device,
    ]


def launch_capture_process(
    project_root: Path,
    runtime_path: Path,
    capture: dict[str, Any],
    input_video_device: str,
    media_device: str,
    hdmi_status_device: str,
) -> dict[str, Any]:
    save_dir = Path(str(capture["save_dir"]))
    ensure_dir(save_dir)
    log_path = save_dir / "capture.log"
    command = build_capture_command(
        project_root=project_root,
        save_dir=save_dir,
        save_format=str(capture["save_format"]),
        sample_fps=float(capture["sample_fps"]),
        max_frames=int(capture["max_frames"]),
        input_video_device=input_video_device,
        media_device=media_device,
        hdmi_status_device=hdmi_status_device,
    )

    with log_path.open("ab") as handle:
        process = subprocess.Popen(
            command,
            cwd=str(project_root),
            stdout=handle,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )

    runtime = {
        "capture_id": capture["capture_id"],
        "pid": process.pid,
        "save_dir": str(save_dir),
        "frames_dir": str(save_dir / "frames"),
        "save_format": capture["save_format"],
        "sample_fps": capture["sample_fps"],
        "max_frames": capture["max_frames"],
        "started_at_utc": now_utc().isoformat(),
        "log_path": str(log_path),
    }
    write_capture_runtime(runtime_path, runtime)
    return runtime


def is_process_running(pid: int | None) -> bool:
    if pid is None or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def stop_capture_process(runtime: dict[str, Any], sig: int = signal.SIGTERM) -> None:
    pid = int(runtime.get("pid", 0) or 0)
    if pid <= 0:
        return
    try:
        os.killpg(pid, sig)
    except OSError:
        return


def collect_frame_records(
    save_dir: str | Path,
    width: int | None = None,
    height: int | None = None,
) -> list[dict[str, Any]]:
    frames_dir = Path(save_dir) / "frames"
    if not frames_dir.exists():
        return []

    records: list[dict[str, Any]] = []
    for index, path in enumerate(sorted(frames_dir.iterdir())):
        if not path.is_file():
            continue
        stat_result = path.stat()
        records.append(
            {
                "frame_index": index,
                "captured_at_utc": datetime.fromtimestamp(
                    stat_result.st_mtime, tz=timezone.utc
                ).isoformat(),
                "relative_path": str(path.relative_to(save_dir)),
                "width": width,
                "height": height,
                "size_bytes": stat_result.st_size,
            }
        )
    return records
