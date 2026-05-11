from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.core.models import CaptureFrameRecord
from app.utils.file_utils import ensure_dir


class CaptureArtifactStore:
    """Local metadata storage for capture manifests and preview assets."""

    def __init__(self, capture_artifacts_root: Path) -> None:
        self._capture_artifacts_root = ensure_dir(capture_artifacts_root)

    def capture_dir(self, capture_id: str) -> Path:
        return self._capture_artifacts_root / capture_id

    def manifest_path(self, capture_id: str) -> Path:
        return self.capture_dir(capture_id) / "manifest.json"

    def preview_frames_dir(self, capture_id: str) -> Path:
        return self.capture_dir(capture_id) / "frames"

    def init_capture(self, capture_id: str) -> Path:
        capture_dir = ensure_dir(self.capture_dir(capture_id))
        ensure_dir(self.preview_frames_dir(capture_id))
        return capture_dir

    def read_manifest(self, capture_id: str) -> dict[str, Any] | None:
        manifest_path = self.manifest_path(capture_id)
        if not manifest_path.exists():
            return None
        with manifest_path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def write_manifest(self, capture_id: str, payload: dict[str, Any]) -> Path:
        manifest_path = self.manifest_path(capture_id)
        ensure_dir(manifest_path.parent)
        with manifest_path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False)
        return manifest_path

    def list_frames(self, capture_id: str, offset: int, limit: int) -> dict[str, Any]:
        manifest = self.read_manifest(capture_id) or {}
        raw_frames = manifest.get("frames", [])
        frames = [
            CaptureFrameRecord.model_validate(item).model_dump(mode="json")
            for item in raw_frames
        ]
        total = len(frames)
        return {
            "total": total,
            "items": frames[offset : offset + limit],
        }
