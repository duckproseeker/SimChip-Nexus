from __future__ import annotations

from pathlib import Path

from app.hil.gateway_agent import (
    GatewayAgentSettings,
    build_register_payload,
    determine_gateway_status,
    is_gadget_video_name,
    parse_args,
    parse_csv,
    parse_tc358743_status,
    read_dut_result_metrics,
)


def make_settings(tmp_path: Path) -> GatewayAgentSettings:
    state_dir = tmp_path / "pi_gateway"
    state_dir.mkdir()
    return GatewayAgentSettings(
        api_base_url="http://127.0.0.1:8000",
        gateway_id="rpi5-x1301-01",
        gateway_name="bench-a",
        input_video_device="/dev/video0",
        media_device="/dev/media0",
        hdmi_status_device="/dev/v4l-subdev2",
        heartbeat_interval_seconds=5.0,
        api_timeout_seconds=3.0,
        state_dir=state_dir,
        gadget_state_file=state_dir / "gadget_state.json",
        bridge_state_file=state_dir / "bridge_state.json",
        current_run_id_file=state_dir / "current_run_id",
        capture_runtime_file=state_dir / "capture_runtime.json",
        dut_result_file=state_dir / "dut_result.json",
        agent_version="0.1.0",
        video_input_modes=("hdmi_x1301", "frame_stream"),
        dut_output_modes=("uvc_gadget",),
        result_ingest_modes=("http_push",),
        once=False,
    )


def test_parse_csv_trims_empty_items() -> None:
    assert parse_csv(" hdmi_x1301, frame_stream ,, ") == ("hdmi_x1301", "frame_stream")


def test_is_gadget_video_name_accepts_legacy_and_configfs_uvc_names() -> None:
    assert is_gadget_video_name("Webcam gadget")
    assert is_gadget_video_name("UVC Gadget")
    assert is_gadget_video_name("ConfigFS UVC Gadget")
    assert not is_gadget_video_name("USB Camera")
    assert not is_gadget_video_name("")


def test_determine_gateway_status_ready_and_busy() -> None:
    metrics = {
        "udc_present": True,
        "input_device_exists": True,
        "gadget_driver_loaded": True,
        "gadget_video_device_exists": True,
    }
    assert determine_gateway_status(metrics, None) == "READY"
    assert determine_gateway_status(metrics, "run_001") == "BUSY"


def test_determine_gateway_status_error_when_gadget_missing() -> None:
    metrics = {
        "udc_present": True,
        "input_device_exists": True,
        "gadget_driver_loaded": False,
        "gadget_video_device_exists": False,
    }
    assert determine_gateway_status(metrics, None) == "ERROR"


def test_determine_gateway_status_ready_when_dut_telemetry_is_live_without_gadget() -> None:
    metrics = {
        "udc_present": True,
        "input_device_exists": True,
        "gadget_driver_loaded": False,
        "gadget_video_device_exists": False,
        "dut_received_at_utc": "2026-03-23T13:29:12Z",
        "dut_status": "RUNNING",
    }
    assert determine_gateway_status(metrics, None) == "BUSY"


def test_build_register_payload_contains_capabilities(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    payload = build_register_payload(
        settings,
        address="192.168.110.236",
        metrics={"gadget_driver": "g_webcam"},
    )

    assert payload["gateway_id"] == "rpi5-x1301-01"
    assert payload["address"] == "192.168.110.236"
    assert payload["capabilities"]["video_input_modes"] == ["hdmi_x1301", "frame_stream"]
    assert payload["capabilities"]["dut_output_modes"] == ["uvc_gadget"]
    assert payload["capabilities"]["result_ingest_modes"] == ["http_push"]
    assert payload["capabilities"]["gadget_driver"] == "g_webcam"


def test_parse_tc358743_status_extracts_signal_flags() -> None:
    status_output = """
    tc358743 11-000f: Cable detected (+5V power): yes
    tc358743 11-000f: DDC lines enabled: yes
    tc358743 11-000f: Hotplug enabled: yes
    tc358743 11-000f: TMDS signal detected: no
    tc358743 11-000f: Stable sync signal: no
    tc358743 11-000f: PHY PLL locked: no
    tc358743 11-000f: PHY DE detected: no
    tc358743 11-000f: No video detected
    tc358743 11-000f: Configured format: 640x480p59.94 (800x525)
    tc358743 11-000f: Input color space: RGB full range
    """

    metrics = parse_tc358743_status(status_output)

    assert metrics["hdmi_cable_detected"] is True
    assert metrics["hdmi_hotplug_enabled"] is True
    assert metrics["hdmi_tmds_signal_detected"] is False
    assert metrics["hdmi_stable_sync_signal"] is False
    assert metrics["hdmi_video_detected"] is False
    assert metrics["hdmi_configured_format"] == "640x480p59.94 (800x525)"
    assert metrics["hdmi_input_color_space"] == "RGB full range"


def test_read_dut_result_metrics_flattens_nested_payload(tmp_path: Path) -> None:
    result_path = tmp_path / "dut_result.json"
    result_path.write_text(
        """
        {
          "status": "COMPLETED",
          "run_id": "run_demo_001",
          "received_at_utc": "2026-03-16T12:00:00Z",
          "model_name": "tensorrt_yolov5s",
          "metrics": {
            "output_fps": 14.8,
            "avg_latency_ms": 67.5,
            "processed_frames": 320,
            "detection_count": 1410
          }
        }
        """.strip(),
        encoding="utf-8",
    )

    metrics = read_dut_result_metrics(result_path)

    assert metrics["dut_status"] == "COMPLETED"
    assert metrics["dut_run_id"] == "run_demo_001"
    assert metrics["dut_received_at_utc"] == "2026-03-16T12:00:00Z"
    assert metrics["dut_model_name"] == "tensorrt_yolov5s"
    assert metrics["output_fps"] == 14.8
    assert metrics["avg_latency_ms"] == 67.5
    assert metrics["processed_frames"] == 320
    assert metrics["detection_count"] == 1410


def test_parse_args_auto_detects_media_device(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("PI_GATEWAY_API_BASE_URL", "http://127.0.0.1:8000")
    monkeypatch.setenv("PI_GATEWAY_ID", "rpi5-x1301-01")
    monkeypatch.setenv("PI_GATEWAY_NAME", "bench-a")
    monkeypatch.delenv("PI_GATEWAY_MEDIA_DEVICE", raising=False)
    monkeypatch.setattr(
        "app.hil.gateway_agent.find_media_device", lambda driver_name: "/dev/media3"
    )

    settings = parse_args(["--state-dir", str(tmp_path / "state"), "--once"])

    assert settings.media_device == "/dev/media3"
