#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import signal
import sys
import time
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from jetson_yolo_metrics import (
    AsyncResultReporter,
    TegrastatsSampler,
    build_result_payload,
    format_metric_value,
    log,
    write_result_file,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Collect non-ROS Jetson detector metrics and post them to Pi"
    )
    parser.add_argument("--metrics-file", required=True)
    parser.add_argument("--model-name", default="tensorrt_detector")
    parser.add_argument("--camera-device", default="")
    parser.add_argument("--run-id", default="")
    parser.add_argument("--source-host", default="")
    parser.add_argument("--result-url", default="")
    parser.add_argument("--result-file", default="")
    parser.add_argument("--input-topic", default="")
    parser.add_argument("--output-topic", default="")
    parser.add_argument("--tegrastats-command", default="tegrastats --interval 1000")
    parser.add_argument("--duration-seconds", type=float, default=0.0)
    parser.add_argument("--result-timeout-seconds", type=float, default=2.0)
    parser.add_argument("--result-max-retries", type=int, default=3)
    parser.add_argument("--result-retry-backoff-seconds", type=float, default=1.0)
    parser.add_argument("--poll-interval-seconds", type=float, default=0.2)
    parser.add_argument("--verbose", action="store_true")
    return parser.parse_args(argv)


def normalize_metrics_payload(payload: dict[str, Any]) -> dict[str, Any]:
    metrics: dict[str, Any] = {}
    nested_metrics = payload.get("metrics")
    if isinstance(nested_metrics, dict):
        metrics.update(nested_metrics)

    for key, value in payload.items():
        if key == "metrics":
            continue
        metrics[key] = value
    return metrics


def read_metrics_file(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, json.JSONDecodeError):
        return {}

    if not isinstance(payload, dict):
        return {}
    return normalize_metrics_payload(payload)


class MetricsFileMonitor:
    def __init__(self, metrics_file: Path) -> None:
        self._metrics_file = metrics_file
        self._latest_metrics: dict[str, Any] = {}
        self._last_signature: tuple[int, int] | None = None
        self._version = 0

    @property
    def version(self) -> int:
        return self._version

    def summary(self) -> dict[str, Any]:
        return dict(self._latest_metrics)

    def poll(self) -> bool:
        try:
            stat_result = self._metrics_file.stat()
        except OSError:
            return False

        signature = (int(stat_result.st_mtime_ns), int(stat_result.st_size))
        if signature == self._last_signature:
            return False

        metrics = read_metrics_file(self._metrics_file)
        self._last_signature = signature
        if not metrics:
            return False

        self._latest_metrics = metrics
        self._version += 1
        return True


def build_metrics_snapshot(
    monitor: MetricsFileMonitor,
    tegrastats: TegrastatsSampler,
) -> dict[str, Any]:
    metrics: dict[str, Any] = {}
    metrics.update(monitor.summary())
    tegrastats_summary = tegrastats.summary()
    for key, value in tegrastats_summary.items():
        if metrics.get(key) is None:
            metrics[key] = value
    return metrics


def log_running_snapshot(metrics: dict[str, Any]) -> None:
    processed_frames = int(metrics.get("processed_frames") or 0)
    if processed_frames <= 0:
        return
    log(
        "running "
        f"output_fps={format_metric_value(metrics.get('output_fps'))} "
        f"avg_latency_ms={format_metric_value(metrics.get('avg_latency_ms'))} "
        f"processed_frames={format_metric_value(metrics.get('processed_frames'))} "
        f"detection_count={format_metric_value(metrics.get('detection_count'))}"
    )


def poll_final_metrics(
    monitor: MetricsFileMonitor,
    *,
    poll_interval_seconds: float,
    wait_timeout_seconds: float = 1.0,
) -> None:
    deadline = time.monotonic() + max(wait_timeout_seconds, 0.0)
    while time.monotonic() < deadline:
        changed = monitor.poll()
        if changed:
            # Give the detector one more short window in case it is still flushing.
            time.sleep(max(poll_interval_seconds, 0.05))
            continue
        time.sleep(0.05)
    monitor.poll()


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    result_file = Path(args.result_file).expanduser() if args.result_file else None
    metrics_file = Path(args.metrics_file).expanduser()

    should_stop = False
    interrupted = False

    def _request_stop(signum: int, frame: Any) -> None:
        nonlocal should_stop, interrupted
        should_stop = True
        interrupted = True
        log(f"received signal={signum}, finalizing")

    signal.signal(signal.SIGINT, _request_stop)
    signal.signal(signal.SIGTERM, _request_stop)

    reporter = AsyncResultReporter(
        url=args.result_url,
        timeout_seconds=args.result_timeout_seconds,
        max_retries=args.result_max_retries,
        retry_backoff_seconds=args.result_retry_backoff_seconds,
        verbose=args.verbose,
    )
    reporter.start()

    tegrastats = TegrastatsSampler(args.tegrastats_command, verbose=args.verbose)
    tegrastats.start()
    monitor = MetricsFileMonitor(metrics_file)

    started_monotonic = time.monotonic()
    last_reported_version = 0
    last_progress_log_monotonic = started_monotonic

    log(
        f"start metrics_file={metrics_file} model_name={args.model_name} "
        f"result_url={args.result_url or '-'}"
    )

    try:
        while not should_stop:
            changed = monitor.poll()
            if args.result_url.strip() and changed and monitor.version > last_reported_version:
                reporter.submit(
                    build_result_payload(
                        args,
                        build_metrics_snapshot(monitor, tegrastats),
                        status="RUNNING",
                    )
                )
                last_reported_version = monitor.version

            now_monotonic = time.monotonic()
            if (now_monotonic - last_progress_log_monotonic) >= 1.0:
                log_running_snapshot(build_metrics_snapshot(monitor, tegrastats))
                last_progress_log_monotonic = now_monotonic

            if (
                args.duration_seconds > 0
                and (now_monotonic - started_monotonic) >= args.duration_seconds
            ):
                should_stop = True
                continue

            time.sleep(max(args.poll_interval_seconds, 0.05))
    finally:
        tegrastats.stop()

    poll_final_metrics(
        monitor,
        poll_interval_seconds=args.poll_interval_seconds,
    )
    final_metrics = build_metrics_snapshot(monitor, tegrastats)
    payload = build_result_payload(
        args,
        final_metrics,
        status="INTERRUPTED" if interrupted else "COMPLETED",
    )
    write_result_file(result_file, payload)
    if args.result_url.strip():
        reporter.submit(payload)
        reporter.wait_for_idle(
            timeout_seconds=max(
                2.0,
                args.result_timeout_seconds * max(args.result_max_retries + 1, 1),
            )
            + args.result_retry_backoff_seconds,
        )
        reporter.close()
        log(f"queued final result url={args.result_url.strip()}")
    else:
        reporter.close()
        log("result_url not set, wrote local payload only")

    sys.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
