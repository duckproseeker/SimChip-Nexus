from __future__ import annotations

from app.hil.jetson_rtp_camera_node import (
    JetsonRtpCameraSettings,
    build_gstreamer_pipeline,
    parse_args,
)


def test_build_gstreamer_pipeline_uses_hardware_decoder_defaults() -> None:
    pipeline = build_gstreamer_pipeline(
        JetsonRtpCameraSettings(
            port=5000,
            host="0.0.0.0",
            topic="/image_raw",
            frame_id="camera",
            decoder="nvv4l2decoder",
        )
    )

    assert "udpsrc address=0.0.0.0 port=5000" in pipeline
    assert "encoding-name=H264" in pipeline
    assert "nvv4l2decoder enable-max-performance=1" in pipeline
    assert "appsink drop=true max-buffers=1 sync=false" in pipeline


def test_build_gstreamer_pipeline_supports_decoder_override() -> None:
    pipeline = build_gstreamer_pipeline(
        JetsonRtpCameraSettings(
            port=5600,
            host="127.0.0.1",
            topic="/image_raw",
            frame_id="camera",
            decoder="avdec_h264",
        )
    )

    assert "udpsrc address=127.0.0.1 port=5600" in pipeline
    assert "avdec_h264" in pipeline
    assert "videoconvert ! video/x-raw,format=BGR" in pipeline


def test_parse_args_supports_swap_rb_flag(monkeypatch) -> None:
    monkeypatch.delenv("JETSON_RTP_SWAP_RB", raising=False)

    settings, ros_args = parse_args(["--swap-rb"])

    assert settings.swap_rb is True
    assert ros_args == []


def test_parse_args_reads_swap_rb_from_env(monkeypatch) -> None:
    monkeypatch.setenv("JETSON_RTP_SWAP_RB", "true")

    settings, _ = parse_args([])

    assert settings.swap_rb is True
