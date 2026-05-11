from __future__ import annotations

import os
import socket
import subprocess
from typing import Any

from app.utils.time_utils import now_utc, to_iso8601


def probe_pi_gateway(settings: Any, timeout_seconds: float = 1.5) -> dict[str, Any]:
    host = getattr(settings, "duckpark_pi_host", None)
    user = getattr(settings, "duckpark_pi_user", None)
    port = int(getattr(settings, "duckpark_pi_port", 22) or 22)
    checked_at = now_utc()

    start_command = getattr(settings, "hil_pi_start_command", None)
    stop_command = getattr(settings, "hil_pi_stop_command", None)
    configured = bool(host and user and start_command)

    if not host or not user:
        return {
            "status": "UNKNOWN",
            "configured": False,
            "reachable": False,
            "host": host,
            "user": user,
            "port": port,
            "start_command_configured": bool(start_command),
            "stop_command_configured": bool(stop_command),
            "last_probe_at_utc": to_iso8601(checked_at),
            "warning": "DUCKPARK_PI_HOST / DUCKPARK_PI_USER 未配置，平台不会尝试拉起树莓派链路。",
        }

    reachable = False
    warning = None
    try:
        with socket.create_connection((host, port), timeout=timeout_seconds):
            reachable = True
    except OSError as exc:
        warning = str(exc)

    return {
        "status": "READY" if reachable else "OFFLINE",
        "configured": configured,
        "reachable": reachable,
        "host": host,
        "user": user,
        "port": port,
        "start_command_configured": bool(start_command),
        "stop_command_configured": bool(stop_command),
        "last_probe_at_utc": to_iso8601(checked_at),
        "warning": warning,
    }


def run_pi_gateway_command(settings: Any, action: str) -> dict[str, Any]:
    normalized_action = action.strip().lower()
    if normalized_action not in {"start", "stop"}:
        raise ValueError(f"Unsupported Pi gateway action: {action}")

    command = (
        getattr(settings, "hil_pi_start_command", None)
        if normalized_action == "start"
        else getattr(settings, "hil_pi_stop_command", None)
    )
    if not command or not command.strip():
        raise RuntimeError(f"Pi gateway {normalized_action} command is not configured")

    env = os.environ.copy()
    env["PROJECT_ROOT"] = str(settings.project_root)
    env["DUCKPARK_SRC_ROOT"] = str(settings.project_root.parent)
    env["DUCKPARK_PLATFORM_ROOT"] = str(settings.project_root)
    env["DUCKPARK_HIL_RUNTIME_ROOT"] = str(settings.hil_runtime_root)
    if getattr(settings, "duckpark_pi_host", None):
        env["DUCKPARK_PI_HOST"] = str(settings.duckpark_pi_host)
    if getattr(settings, "duckpark_pi_user", None):
        env["DUCKPARK_PI_USER"] = str(settings.duckpark_pi_user)
    env["DUCKPARK_PI_PORT"] = str(getattr(settings, "duckpark_pi_port", 22) or 22)

    completed = subprocess.run(
        ["bash", "-lc", command.strip()],
        cwd=str(settings.hil_runtime_workdir),
        env=env,
        capture_output=True,
        text=True,
        timeout=settings.hil_command_timeout_seconds,
        check=False,
    )
    combined_output = "\n".join(
        part.strip()
        for part in [completed.stdout or "", completed.stderr or ""]
        if part and part.strip()
    )

    return {
        "action": normalized_action,
        "success": completed.returncode == 0,
        "exit_code": completed.returncode,
        "output": combined_output or None,
        "status": probe_pi_gateway(settings),
    }
