from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.core.models import RunEvent, RunMetrics, RunRecord
from app.utils.file_utils import ensure_dir


class ArtifactStore:
    """Manage per-run artifact files and event streams."""

    def __init__(self, artifacts_root: Path) -> None:
        self._artifacts_root = ensure_dir(artifacts_root)

    def run_dir(self, run_id: str) -> Path:
        return self._artifacts_root / run_id

    def init_run(self, run_id: str) -> Path:
        run_dir = ensure_dir(self.run_dir(run_id))
        ensure_dir(run_dir / "recorder")
        ensure_dir(run_dir / "outputs")
        (run_dir / "events.jsonl").touch(exist_ok=True)
        (run_dir / "run.log").touch(exist_ok=True)
        return run_dir

    def write_config_snapshot(self, run_id: str, config: dict[str, Any]) -> None:
        path = self.run_dir(run_id) / "config_snapshot.json"
        with path.open("w", encoding="utf-8") as handle:
            json.dump(config, handle, indent=2, ensure_ascii=False)

    def write_status(self, run: RunRecord) -> None:
        path = self.run_dir(run.run_id) / "status.json"
        with path.open("w", encoding="utf-8") as handle:
            json.dump(run.model_dump(mode="json"), handle, indent=2, ensure_ascii=False)

    def write_metrics(self, metrics: RunMetrics) -> None:
        path = self.run_dir(metrics.run_id) / "metrics.json"
        with path.open("w", encoding="utf-8") as handle:
            json.dump(
                metrics.model_dump(mode="json"), handle, indent=2, ensure_ascii=False
            )

    def read_metrics(self, run_id: str) -> dict[str, Any] | None:
        path = self.run_dir(run_id) / "metrics.json"
        if not path.exists():
            return None
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def write_device_metrics(self, run_id: str, payload: dict[str, Any]) -> None:
        path = ensure_dir(self.run_dir(run_id) / "outputs" / "hil") / "device_metrics.json"
        with path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False)

    def read_device_metrics(self, run_id: str) -> dict[str, Any] | None:
        path = self.run_dir(run_id) / "outputs" / "hil" / "device_metrics.json"
        if not path.exists():
            return None
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def append_event(self, event: RunEvent) -> None:
        path = self.run_dir(event.run_id) / "events.jsonl"
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event.model_dump(mode="json"), ensure_ascii=False))
            handle.write("\n")

    def append_run_log(self, run_id: str, line: str) -> None:
        path = self.run_dir(run_id) / "run.log"
        with path.open("a", encoding="utf-8") as handle:
            handle.write(line)
            if not line.endswith("\n"):
                handle.write("\n")

    def read_events(self, run_id: str) -> list[dict[str, Any]]:
        path = self.run_dir(run_id) / "events.jsonl"
        if not path.exists():
            return []

        events: list[dict[str, Any]] = []
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                stripped = line.strip()
                if not stripped:
                    continue
                events.append(json.loads(stripped))
        return events
