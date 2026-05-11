from __future__ import annotations

from typing import Any

DEFAULT_EVALUATION_PROFILES: list[dict[str, Any]] = [
    {
        "profile_name": "yolo_open_loop_v1",
        "display_name": "YOLO 开环 v1",
        "description": "面向相机开环链路的基础检测评测模板。",
        "metrics": [
            "precision",
            "recall",
            "map50",
            "avg_latency_ms",
            "p95_latency_ms",
            "fps",
            "frame_drop_rate",
        ],
        "iou_threshold": 0.5,
        "classes": [],
    }
]


def list_evaluation_profiles() -> list[dict[str, Any]]:
    return [dict(item) for item in DEFAULT_EVALUATION_PROFILES]
