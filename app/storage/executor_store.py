from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.utils.file_utils import ensure_dir


class ExecutorStore:
    """Persist executor heartbeat so control-plane can detect stale queues."""

    def __init__(self, executor_root: Path) -> None:
        self._executor_root = ensure_dir(executor_root)

    def heartbeat_path(self) -> Path:
        return self._executor_root / "heartbeat.json"

    def write_heartbeat(self, payload: dict[str, Any]) -> Path:
        path = self.heartbeat_path()
        ensure_dir(path.parent)
        with path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False)
        return path

    def read_heartbeat(self) -> dict[str, Any] | None:
        path = self.heartbeat_path()
        if not path.exists():
            return None
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
