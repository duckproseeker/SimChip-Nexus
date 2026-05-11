from __future__ import annotations

import base64
import faulthandler
import json
import sys
import time
from typing import Any

from app.viewer.ego_snapshot import EgoSnapshotViewer, EgoSnapshotViewerError


def _normalized_spawn_point(value: Any) -> dict[str, float] | None:
    if not isinstance(value, dict):
        return None
    normalized: dict[str, float] = {}
    for key in ("x", "y", "z", "roll", "pitch", "yaw"):
        raw = value.get(key)
        if raw is None:
            continue
        normalized[key] = float(raw)
    return normalized or None


def _emit(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False), flush=True)


def main() -> int:
    faulthandler.enable(all_threads=True)

    if len(sys.argv) < 2:
        _emit({"ok": False, "error": "missing viewer stream payload", "status_code": 400})
        return 2

    payload = json.loads(sys.argv[1])
    target_interval_seconds = max(0.03, float(payload.get("target_interval_ms") or 66) / 1000.0)
    capture_timeout_seconds = max(
        0.5,
        float(payload.get("capture_timeout_seconds") or 2.0),
    )

    try:
        viewer = EgoSnapshotViewer(
            host=str(payload.get("host") or "127.0.0.1"),
            port=int(payload.get("port") or 2000),
            timeout_seconds=float(payload.get("timeout_seconds") or 5.0),
            width=int(payload.get("width") or 960),
            height=int(payload.get("height") or 540),
            preferred_actor_id=payload.get("preferred_actor_id"),
            preferred_spawn_point=_normalized_spawn_point(
                payload.get("preferred_spawn_point")
            ),
        )
        session = viewer.open_stream_session(
            view_id=str(payload.get("view_id") or "first_person")
        )
    except EgoSnapshotViewerError as exc:
        _emit({"ok": False, "error": str(exc), "status_code": 503})
        return 3
    except Exception as exc:
        _emit({"ok": False, "error": f"viewer stream worker failed: {exc}", "status_code": 503})
        return 4

    try:
        while True:
            frame_started_at = time.monotonic()
            try:
                png_bytes = session.capture_png_bytes(timeout_seconds=capture_timeout_seconds)
            except EgoSnapshotViewerError as exc:
                _emit({"ok": False, "error": str(exc), "status_code": 503})
                return 5

            _emit(
                {
                    "ok": True,
                    "mime": "image/png",
                    "image_base64": base64.b64encode(png_bytes).decode("ascii"),
                }
            )

            elapsed = time.monotonic() - frame_started_at
            if elapsed < target_interval_seconds:
                time.sleep(target_interval_seconds - elapsed)
    finally:
        session.close()


if __name__ == "__main__":
    raise SystemExit(main())
