from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

from app.core.errors import ConflictError, NotFoundError
from app.core.models import CaptureRecord
from app.utils.file_utils import ensure_dir
from app.utils.time_utils import now_utc

CaptureUpdater = Callable[[CaptureRecord], CaptureRecord]


class CaptureStore:
    """File-based persistence for capture records."""

    def __init__(self, captures_root: Path) -> None:
        self._captures_root = ensure_dir(captures_root)

    def _capture_path(self, capture_id: str) -> Path:
        return self._captures_root / f"{capture_id}.json"

    def create(self, capture: CaptureRecord) -> CaptureRecord:
        path = self._capture_path(capture.capture_id)
        if path.exists():
            raise ConflictError(f"Capture already exists: {capture.capture_id}")

        with path.open("w", encoding="utf-8") as handle:
            json.dump(capture.model_dump(mode="json"), handle, indent=2, ensure_ascii=False)
        return capture

    def get(self, capture_id: str) -> CaptureRecord:
        path = self._capture_path(capture_id)
        if not path.exists():
            raise NotFoundError(f"Capture not found: {capture_id}")

        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        return CaptureRecord.model_validate(payload)

    def list(self) -> list[CaptureRecord]:
        captures: list[CaptureRecord] = []
        for path in sorted(self._captures_root.glob("*.json")):
            with path.open("r", encoding="utf-8") as handle:
                payload = json.load(handle)
            captures.append(CaptureRecord.model_validate(payload))
        return captures

    def save(self, capture: CaptureRecord) -> CaptureRecord:
        path = self._capture_path(capture.capture_id)
        if not path.exists():
            raise NotFoundError(f"Capture not found: {capture.capture_id}")

        capture.updated_at = now_utc()
        with path.open("w", encoding="utf-8") as handle:
            json.dump(capture.model_dump(mode="json"), handle, indent=2, ensure_ascii=False)
        return capture

    def update(self, capture_id: str, updater: CaptureUpdater) -> CaptureRecord:
        capture = self.get(capture_id)
        updated = updater(capture)
        return self.save(updated)
