from __future__ import annotations

import json
from pathlib import Path

from scripts.jetson_non_ros_metrics import (
    MetricsFileMonitor,
    normalize_metrics_payload,
    read_metrics_file,
)


def test_normalize_metrics_payload_merges_nested_metrics() -> None:
    normalized = normalize_metrics_payload(
        {
            "metrics": {"output_fps": 28.4, "processed_frames": 42},
            "detection_count": 7,
        }
    )

    assert normalized["output_fps"] == 28.4
    assert normalized["processed_frames"] == 42
    assert normalized["detection_count"] == 7


def test_read_metrics_file_ignores_invalid_payloads(tmp_path: Path) -> None:
    metrics_file = tmp_path / "metrics.json"
    metrics_file.write_text('["not-an-object"]', encoding="utf-8")

    assert read_metrics_file(metrics_file) == {}


def test_metrics_file_monitor_tracks_file_updates(tmp_path: Path) -> None:
    metrics_file = tmp_path / "metrics.json"
    monitor = MetricsFileMonitor(metrics_file)

    assert monitor.poll() is False

    metrics_file.write_text(
        json.dumps({"processed_frames": 5, "detection_count": 1}),
        encoding="utf-8",
    )

    assert monitor.poll() is True
    assert monitor.version == 1
    assert monitor.summary()["processed_frames"] == 5

    metrics_file.write_text(
        json.dumps({"processed_frames": 8, "detection_count": 3}),
        encoding="utf-8",
    )

    assert monitor.poll() is True
    assert monitor.version == 2
    assert monitor.summary()["detection_count"] == 3
