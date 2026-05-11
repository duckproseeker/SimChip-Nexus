from __future__ import annotations

import threading
from argparse import Namespace

from scripts.jetson_yolo_metrics import (
    AsyncResultReporter,
    build_result_payload,
    parse_tegrastats_line,
)


def test_parse_tegrastats_line_extracts_power_and_temperature() -> None:
    line = (
        "RAM 1189/3964MB (lfb 299x4MB) SWAP 0/1982MB "
        "CPU [5%@1479,off,off,off] EMC_FREQ 0% GR3D_FREQ 0% "
        "PLL@39.5C CPU@42C PMIC@50C GPU@41.5C AO@44C thermal@41.75C "
        "POM_5V_IN 3890/4001 POM_5V_GPU 512/520 POM_5V_CPU 1102/1110"
    )

    metrics = parse_tegrastats_line(line)

    assert metrics["power_w"] == 3.89
    assert metrics["temperature_c"] == 50.0


def test_build_result_payload_maps_metadata_and_metrics() -> None:
    args = Namespace(
        output_topic="/duckpark/rois",
        input_topic="/image_raw",
        model_name="tensorrt_yolov5s",
        camera_device="/dev/video0",
        run_id="run_demo_001",
        source_host="jetson-nano",
    )

    payload = build_result_payload(
        args,
        {
            "output_fps": 14.2,
            "avg_latency_ms": 65.5,
            "processed_frames": 100,
            "detection_count": 210,
        },
    )

    assert payload["status"] == "COMPLETED"
    assert payload["model_name"] == "tensorrt_yolov5s"
    assert payload["input_topic"] == "/image_raw"
    assert payload["output_topic"] == "/duckpark/rois"
    assert payload["camera_device"] == "/dev/video0"
    assert payload["run_id"] == "run_demo_001"
    assert payload["source_host"] == "jetson-nano"
    assert payload["metrics"]["output_fps"] == 14.2
    assert payload["metrics"]["detection_count"] == 210
    assert payload["received_at_utc"].endswith("Z")


def test_build_result_payload_supports_running_status() -> None:
    args = Namespace(
        output_topic="/duckpark/rois",
        input_topic="/image_raw",
        model_name="tensorrt_yolov5s",
        camera_device="",
        run_id="",
        source_host="",
    )

    payload = build_result_payload(
        args,
        {
            "output_fps": 18.5,
            "avg_latency_ms": 31.2,
            "processed_frames": 300,
            "detection_count": 845,
        },
        status="RUNNING",
    )

    assert payload["status"] == "RUNNING"
    assert payload["metrics"]["processed_frames"] == 300


def test_async_result_reporter_retries_failed_requests() -> None:
    attempts: list[str] = []
    delivered: list[dict[str, object]] = []

    def fake_post(url: str, payload: dict[str, object], timeout: float) -> None:
        attempts.append(url)
        if len(attempts) == 1:
            raise RuntimeError("temporary failure")
        delivered.append(payload)

    reporter = AsyncResultReporter(
        url="http://192.168.7.1:18765/dut-results",
        timeout_seconds=0.2,
        max_retries=1,
        retry_backoff_seconds=0.01,
        post_callable=fake_post,
    )
    reporter.start()
    reporter.submit({"status": "RUNNING", "metrics": {"processed_frames": 10}})

    assert reporter.wait_for_idle(1.0) is True
    reporter.close()

    assert len(attempts) == 2
    assert delivered == [{"status": "RUNNING", "metrics": {"processed_frames": 10}}]


def test_async_result_reporter_keeps_latest_payload_under_load() -> None:
    posted_sequences: list[int] = []
    unblock_first_post = threading.Event()

    def fake_post(url: str, payload: dict[str, object], timeout: float) -> None:
        sequence = int(payload["sequence"])
        if sequence == 1:
            unblock_first_post.wait(timeout=0.2)
        posted_sequences.append(sequence)

    reporter = AsyncResultReporter(
        url="http://192.168.7.1:18765/dut-results",
        timeout_seconds=0.2,
        max_retries=0,
        retry_backoff_seconds=0.0,
        post_callable=fake_post,
    )
    reporter.start()
    reporter.submit({"sequence": 1})
    reporter.submit({"sequence": 2})
    reporter.submit({"sequence": 3})
    unblock_first_post.set()

    assert reporter.wait_for_idle(1.0) is True
    reporter.close()

    assert posted_sequences[-1] == 3
