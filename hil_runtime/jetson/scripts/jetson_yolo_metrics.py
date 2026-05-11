#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import queue
import re
import signal
import subprocess
import sys
import threading
import time
from collections import deque
from pathlib import Path
from typing import Any, Callable
from urllib import error, request


def now_utc_iso8601() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Collect Jetson YOLO demo metrics and post them to Pi"
    )
    parser.add_argument("--output-topic", default="/duckpark/rois")
    parser.add_argument("--input-topic", default="/image_raw")
    parser.add_argument("--model-name", default="tensorrt_yolov5s")
    parser.add_argument("--camera-device", default="")
    parser.add_argument("--run-id", default="")
    parser.add_argument("--source-host", default="")
    parser.add_argument("--result-url", default="")
    parser.add_argument("--result-file", default="")
    parser.add_argument("--tegrastats-command", default="tegrastats --interval 1000")
    parser.add_argument("--duration-seconds", type=float, default=0.0)
    parser.add_argument("--result-timeout-seconds", type=float, default=2.0)
    parser.add_argument("--result-max-retries", type=int, default=3)
    parser.add_argument("--result-retry-backoff-seconds", type=float, default=1.0)
    parser.add_argument("--spin-timeout-seconds", type=float, default=0.1)
    parser.add_argument("--verbose", action="store_true")
    return parser.parse_args(argv)


def log(message: str) -> None:
    sys.stdout.write(f"{now_utc_iso8601()} jetson-yolo-metrics {message}\n")
    sys.stdout.flush()


def parse_tegrastats_line(line: str) -> dict[str, float]:
    metrics: dict[str, float] = {}

    ram_match = re.search(r"RAM\s+(\d+)/(\d+)MB", line)
    if ram_match:
        metrics["memory_used_mb"] = float(ram_match.group(1))
        metrics["memory_total_mb"] = float(ram_match.group(2))

    cpu_match = re.search(r"CPU\s+\[([^\]]+)\]", line)
    if cpu_match:
        cpu_samples = [
            float(match.group(1))
            for item in cpu_match.group(1).split(",")
            if (match := re.search(r"(\d+(?:\.\d+)?)%@", item))
        ]
        if cpu_samples:
            metrics["cpu_usage_percent"] = sum(cpu_samples) / len(cpu_samples)
            metrics["cpu_peak_usage_percent"] = max(cpu_samples)

    emc_match = re.search(r"EMC_FREQ\s+(\d+(?:\.\d+)?)%", line)
    if emc_match:
        metrics["emc_usage_percent"] = float(emc_match.group(1))

    gpu_match = re.search(r"GR3D_FREQ\s+(\d+(?:\.\d+)?)%", line)
    if gpu_match:
        metrics["gpu_usage_percent"] = float(gpu_match.group(1))

    power_match = re.search(r"(?:POM_5V_IN|VDD_IN)\s+(\d+)(?:/\d+)?", line)
    if power_match:
        metrics["power_w"] = float(power_match.group(1)) / 1000.0

    temperatures = [
        float(value) for value in re.findall(r"[A-Z0-9_]+@([0-9]+(?:\.[0-9]+)?)C", line)
    ]
    if temperatures:
        metrics["temperature_c"] = max(temperatures)

    return metrics


def format_metric_value(value: float | int | None) -> str:
    if value is None:
        return "-"
    if isinstance(value, int):
        return str(value)
    return f"{value:.2f}"


class TegrastatsSampler:
    def __init__(self, command: str, *, verbose: bool = False) -> None:
        self._command = command
        self._verbose = verbose
        self._process: subprocess.Popen[str] | None = None
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._metric_samples: dict[str, list[float]] = {
            "power_w": [],
            "temperature_c": [],
            "cpu_usage_percent": [],
            "cpu_peak_usage_percent": [],
            "gpu_usage_percent": [],
            "emc_usage_percent": [],
            "memory_used_mb": [],
            "memory_total_mb": [],
        }

    def start(self) -> None:
        if not self._command.strip():
            return
        self._process = subprocess.Popen(
            self._command,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        self._thread = threading.Thread(target=self._consume_output, daemon=True)
        self._thread.start()

    def _consume_output(self) -> None:
        assert self._process is not None
        if self._process.stdout is None:
            return
        for raw_line in self._process.stdout:
            if self._stop_event.is_set():
                break
            line = raw_line.strip()
            if self._verbose and line:
                log(f"tegrastats {line}")
            parsed = parse_tegrastats_line(line)
            for key, value in parsed.items():
                if value is None:
                    continue
                samples = self._metric_samples.get(key)
                if samples is None:
                    samples = []
                    self._metric_samples[key] = samples
                samples.append(value)

    def stop(self) -> None:
        self._stop_event.set()
        if self._process is not None and self._process.poll() is None:
            self._process.terminate()
            try:
                self._process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self._process.kill()
        if self._thread is not None:
            self._thread.join(timeout=1)

    def summary(self) -> dict[str, float | None]:
        power_samples = self._metric_samples.get("power_w", [])
        temperature_samples = self._metric_samples.get("temperature_c", [])
        cpu_samples = self._metric_samples.get("cpu_usage_percent", [])
        cpu_peak_samples = self._metric_samples.get("cpu_peak_usage_percent", [])
        gpu_samples = self._metric_samples.get("gpu_usage_percent", [])
        emc_samples = self._metric_samples.get("emc_usage_percent", [])
        memory_used_samples = self._metric_samples.get("memory_used_mb", [])
        memory_total_samples = self._metric_samples.get("memory_total_mb", [])

        def _avg(values: list[float]) -> float | None:
            return (sum(values) / len(values)) if values else None

        return {
            "power_w": _avg(power_samples),
            "temperature_c": _avg(temperature_samples),
            "temperature_max_c": max(temperature_samples) if temperature_samples else None,
            "cpu_usage_percent": _avg(cpu_samples),
            "cpu_peak_usage_percent": _avg(cpu_peak_samples),
            "gpu_usage_percent": _avg(gpu_samples),
            "emc_usage_percent": _avg(emc_samples),
            "memory_used_mb": _avg(memory_used_samples),
            "memory_total_mb": (
                memory_total_samples[-1] if memory_total_samples else None
            ),
        }


class YoloOutputMonitor:
    def __init__(self, output_topic: str, *, verbose: bool = False) -> None:
        self._output_topic = output_topic
        self._verbose = verbose
        self._message_count = 0
        self._detection_count = 0
        self._first_message_monotonic: float | None = None
        self._last_message_monotonic: float | None = None
        self._latency_samples_ms: deque[float] = deque(maxlen=2048)
        self._message_version = 0

    @property
    def message_version(self) -> int:
        return self._message_version

    def attach(self) -> tuple[Any, type[Any]]:
        import rclpy
        from rclpy.node import Node
        from tier4_perception_msgs.msg import DetectedObjectsWithFeature

        monitor = self

        class OutputSubscriber(Node):
            def __init__(self) -> None:
                super().__init__("duckpark_yolo_output_monitor")
                self.create_subscription(
                    DetectedObjectsWithFeature,
                    monitor._output_topic,
                    self._handle_message,
                    10,
                )

            def _handle_message(self, msg: Any) -> None:
                now_monotonic = time.monotonic()
                if monitor._first_message_monotonic is None:
                    monitor._first_message_monotonic = now_monotonic
                monitor._last_message_monotonic = now_monotonic
                monitor._message_count += 1
                monitor._message_version += 1

                feature_objects = getattr(msg, "feature_objects", None)
                objects = getattr(msg, "objects", None)
                if isinstance(feature_objects, list):
                    monitor._detection_count += len(feature_objects)
                elif isinstance(objects, list):
                    monitor._detection_count += len(objects)

                stamp = getattr(getattr(msg, "header", None), "stamp", None)
                if stamp is not None and hasattr(stamp, "sec") and hasattr(stamp, "nanosec"):
                    source_time = float(stamp.sec) + float(stamp.nanosec) / 1_000_000_000.0
                    latency_ms = max((time.time() - source_time) * 1000.0, 0.0)
                    monitor._latency_samples_ms.append(latency_ms)
                if monitor._verbose:
                    log(
                        "yolo message "
                        f"count={monitor._message_count} detections={monitor._detection_count}"
                    )

        return rclpy, OutputSubscriber

    def summary(self) -> dict[str, float | int | None]:
        elapsed = None
        if self._first_message_monotonic is not None and self._last_message_monotonic is not None:
            elapsed = max(self._last_message_monotonic - self._first_message_monotonic, 0.0)

        avg_latency = (
            sum(self._latency_samples_ms) / len(self._latency_samples_ms)
            if self._latency_samples_ms
            else None
        )
        p95_latency = None
        if self._latency_samples_ms:
            ordered = sorted(self._latency_samples_ms)
            index = min(max(int(len(ordered) * 0.95) - 1, 0), len(ordered) - 1)
            p95_latency = ordered[index]

        return {
            "output_fps": (self._message_count / elapsed) if elapsed and elapsed > 0 else None,
            "avg_latency_ms": avg_latency,
            "p95_latency_ms": p95_latency,
            "processed_frames": self._message_count,
            "detection_count": self._detection_count,
        }


def build_result_payload(
    args: argparse.Namespace,
    metrics: dict[str, Any],
    *,
    status: str = "COMPLETED",
) -> dict[str, Any]:
    input_topic = str(getattr(args, "input_topic", "") or "").strip()
    output_topic = str(getattr(args, "output_topic", "") or "").strip()
    payload: dict[str, Any] = {
        "status": status,
        "model_name": str(getattr(args, "model_name", "") or "").strip(),
        "received_at_utc": now_utc_iso8601(),
        "metrics": metrics,
    }
    if input_topic:
        payload["input_topic"] = input_topic
    if output_topic:
        payload["output_topic"] = output_topic

    camera_device = str(getattr(args, "camera_device", "") or "").strip()
    run_id = str(getattr(args, "run_id", "") or "").strip()
    source_host = str(getattr(args, "source_host", "") or "").strip()
    if camera_device:
        payload["camera_device"] = camera_device
    if run_id:
        payload["run_id"] = run_id
    if source_host:
        payload["source_host"] = source_host
    return payload


def write_result_file(path: Path | None, payload: dict[str, Any]) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def post_result(
    url: str,
    payload: dict[str, Any],
    *,
    timeout_seconds: float = 5.0,
) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = request.Request(
        url=url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=timeout_seconds) as response:
            response.read()
    except error.URLError as exc:
        raise RuntimeError(f"failed to post result to {url}: {exc}") from exc


class AsyncResultReporter:
    def __init__(
        self,
        *,
        url: str,
        timeout_seconds: float,
        max_retries: int,
        retry_backoff_seconds: float,
        verbose: bool = False,
        post_callable: Callable[[str, dict[str, Any], float], None] | None = None,
    ) -> None:
        self._url = url.strip()
        self._timeout_seconds = max(timeout_seconds, 0.1)
        self._max_retries = max(max_retries, 0)
        self._retry_backoff_seconds = max(retry_backoff_seconds, 0.0)
        self._verbose = verbose
        self._post_callable = post_callable or (
            lambda url, payload, timeout: post_result(
                url,
                payload,
                timeout_seconds=timeout,
            )
        )
        self._queue: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=1)
        self._stop_event = threading.Event()
        self._posting_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if not self._url or self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def submit(self, payload: dict[str, Any]) -> None:
        if not self._url:
            return
        while True:
            try:
                self._queue.put_nowait(payload)
                return
            except queue.Full:
                try:
                    self._queue.get_nowait()
                except queue.Empty:
                    continue
                else:
                    self._queue.task_done()

    def wait_for_idle(self, timeout_seconds: float) -> bool:
        deadline = time.monotonic() + max(timeout_seconds, 0.0)
        while time.monotonic() < deadline:
            if self._queue.unfinished_tasks == 0 and not self._posting_event.is_set():
                return True
            time.sleep(0.05)
        return self._queue.unfinished_tasks == 0 and not self._posting_event.is_set()

    def close(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)

    def _run(self) -> None:
        while not self._stop_event.is_set() or not self._queue.empty():
            try:
                payload = self._queue.get(timeout=0.2)
            except queue.Empty:
                continue
            self._posting_event.set()
            try:
                self._post_with_retry(payload)
            finally:
                self._posting_event.clear()
                self._queue.task_done()

    def _post_with_retry(self, payload: dict[str, Any]) -> None:
        attempt = 0
        max_attempts = self._max_retries + 1
        while attempt < max_attempts:
            attempt += 1
            try:
                self._post_callable(self._url, payload, self._timeout_seconds)
                if self._verbose:
                    log(
                        f"posted result status={payload.get('status')} "
                        f"attempt={attempt}/{max_attempts}"
                    )
                return
            except Exception as exc:
                if attempt >= max_attempts:
                    log(
                        f"failed to post result status={payload.get('status')} "
                        f"attempts={max_attempts} error={exc}"
                    )
                    return
                log(
                    f"retrying result post status={payload.get('status')} "
                    f"attempt={attempt}/{max_attempts} error={exc}"
                )
                time.sleep(self._retry_backoff_seconds)


def build_metrics_snapshot(
    monitor: YoloOutputMonitor,
    tegrastats: TegrastatsSampler,
) -> dict[str, Any]:
    metrics: dict[str, Any] = {}
    metrics.update(monitor.summary())
    metrics.update(tegrastats.summary())
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


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    result_file = Path(args.result_file).expanduser() if args.result_file else None

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
    monitor = YoloOutputMonitor(args.output_topic, verbose=args.verbose)
    tegrastats.start()

    try:
        rclpy, node_cls = monitor.attach()
    except Exception as exc:
        tegrastats.stop()
        reporter.close()
        raise SystemExit(f"failed to attach ROS2 monitor: {exc}") from exc

    rclpy.init(args=None)
    node = node_cls()
    started_monotonic = time.monotonic()
    last_reported_version = 0
    last_progress_log_monotonic = started_monotonic

    log(
        f"start output_topic={args.output_topic} input_topic={args.input_topic} "
        f"result_url={args.result_url or '-'}"
    )

    try:
        while rclpy.ok() and not should_stop:
            rclpy.spin_once(node, timeout_sec=max(args.spin_timeout_seconds, 0.01))

            if args.result_url.strip() and monitor.message_version > last_reported_version:
                reporter.submit(
                    build_result_payload(
                        args,
                        build_metrics_snapshot(monitor, tegrastats),
                        status="RUNNING",
                    )
                )
                last_reported_version = monitor.message_version

            now_monotonic = time.monotonic()
            if (now_monotonic - last_progress_log_monotonic) >= 1.0:
                log_running_snapshot(build_metrics_snapshot(monitor, tegrastats))
                last_progress_log_monotonic = now_monotonic

            if (
                args.duration_seconds > 0
                and (now_monotonic - started_monotonic) >= args.duration_seconds
            ):
                should_stop = True
    finally:
        node.destroy_node()
        rclpy.shutdown()
        tegrastats.stop()

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
