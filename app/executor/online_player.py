"""Online dataset player — plays pre-rendered frames fullscreen via mpv (GPU-accelerated).

The host machine's display is used for output (for HDMI capture).
"""
from __future__ import annotations

import subprocess
import threading
from pathlib import Path
from typing import Any


# Active sessions registry
_sessions: dict[str, "PlaybackSession"] = {}


class PlaybackSession:
    """Tracks a running playback."""

    def __init__(self, dataset_id: str, sensor_id: str, target_fps: float):
        self.dataset_id = dataset_id
        self.sensor_id = sensor_id
        self.target_fps = target_fps
        self.running = False
        self._proc: subprocess.Popen | None = None

    def start(self, output_dir: str) -> None:
        self.running = True
        t = threading.Thread(target=self._run, args=(output_dir,), daemon=True)
        t.start()

    def stop(self) -> None:
        self.running = False
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()

    def _run(self, output_dir: str) -> None:
        host_dir = output_dir.replace(
            "/ros2_ws/datasets", "/home/du/ros2-humble/datasets"
        )
        sensor_dir = f"{host_dir}/{self.sensor_id}"

        try:
            self._proc = subprocess.Popen(
                [
                    "mpv",
                    f"mf://{sensor_dir}/*.jpg",
                    f"--mf-fps={self.target_fps}",
                    "--fs",
                    "--vo=gpu",
                    "--hwdec=auto",
                    "--no-osc",
                    "--really-quiet",
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            self._proc.wait()
        except Exception:
            pass
        finally:
            self.running = False
            if self.dataset_id in _sessions:
                del _sessions[self.dataset_id]


def start_playback(
    dataset_id: str,
    output_dir: str,
    sensor_id: str = "",
    target_fps: float = 30.0,
    mode: str = "display",
) -> PlaybackSession:
    """Start fullscreen playback on the host display via mpv."""
    if dataset_id in _sessions:
        _sessions[dataset_id].stop()

    session = PlaybackSession(dataset_id, sensor_id, target_fps)
    session.start(output_dir)
    _sessions[dataset_id] = session
    return session


def stop_playback(dataset_id: str) -> bool:
    """Stop a running playback session."""
    if dataset_id in _sessions:
        _sessions[dataset_id].stop()
        del _sessions[dataset_id]
        return True
    return False


def get_session(dataset_id: str) -> PlaybackSession | None:
    return _sessions.get(dataset_id)
