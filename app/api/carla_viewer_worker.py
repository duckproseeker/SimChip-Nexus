from __future__ import annotations

import base64
import json
import sys
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


def main() -> int:
    if len(sys.argv) < 2:
        print(json.dumps({"ok": False, "error": "missing viewer payload"}))
        return 2

    payload = json.loads(sys.argv[1])

    try:
        viewer = EgoSnapshotViewer(
            host=str(payload.get("host") or "127.0.0.1"),
            port=int(payload.get("port") or 2000),
            timeout_seconds=float(payload.get("timeout_seconds") or 5.0),
            width=int(payload.get("width") or 1280),
            height=int(payload.get("height") or 720),
            preferred_actor_id=payload.get("preferred_actor_id"),
            preferred_spawn_point=_normalized_spawn_point(
                payload.get("preferred_spawn_point")
            ),
        )
        png_bytes = viewer.capture_png_bytes(
            view_id=str(payload.get("view_id") or "first_person")
        )
    except EgoSnapshotViewerError as exc:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": str(exc),
                    "status_code": 503,
                }
            )
        )
        return 3
    except Exception as exc:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": f"viewer worker failed: {exc}",
                    "status_code": 503,
                }
            )
        )
        return 4

    print(
        json.dumps(
            {
                "ok": True,
                "image_base64": base64.b64encode(png_bytes).decode("ascii"),
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
