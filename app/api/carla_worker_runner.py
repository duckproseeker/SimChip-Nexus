from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass
from typing import Any


@dataclass
class CarlaWorkerError(RuntimeError):
    status_code: int
    detail: str

    def __str__(self) -> str:
        return self.detail


def run_carla_worker(
    module_name: str,
    payload: dict[str, Any],
    *,
    timeout_seconds: float,
) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                module_name,
                json.dumps(payload, ensure_ascii=False),
            ],
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        raise CarlaWorkerError(
            status_code=503,
            detail=f"{module_name} timed out while talking to the simulator.",
        ) from exc

    stdout = (completed.stdout or "").strip()
    stderr = (completed.stderr or "").strip()
    payload_text = stdout or stderr

    try:
        worker_payload = json.loads(payload_text) if payload_text else {}
    except json.JSONDecodeError:
        worker_payload = {}

    if completed.returncode != 0:
        detail = (
            worker_payload.get("error")
            or stderr
            or stdout
            or f"{module_name} failed."
        )
        status_code = int(worker_payload.get("status_code") or 503)
        raise CarlaWorkerError(status_code=status_code, detail=detail)

    if not isinstance(worker_payload, dict):
        return {}
    return worker_payload
