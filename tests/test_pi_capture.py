from __future__ import annotations

from pathlib import Path

from app.hil.pi_capture import build_capture_command, collect_frame_records


def test_build_capture_command_contains_expected_arguments(tmp_path: Path) -> None:
    command = build_capture_command(
        project_root=tmp_path,
        save_dir=tmp_path / "capture",
        save_format="jpg",
        sample_fps=2.0,
        max_frames=300,
        input_video_device="/dev/video0",
        media_device="/dev/media3",
        hdmi_status_device="/dev/v4l-subdev2",
    )

    assert command[0:3] == ["bash", str(tmp_path / "scripts" / "start_pi_frame_capture.sh"), "--save-dir"]
    assert "--media-device" in command
    assert "/dev/media3" in command


def test_collect_frame_records_reads_saved_files(tmp_path: Path) -> None:
    frames_dir = tmp_path / "frames"
    frames_dir.mkdir()
    frame_a = frames_dir / "frame_000001.jpg"
    frame_b = frames_dir / "frame_000002.jpg"
    frame_a.write_bytes(b"abc")
    frame_b.write_bytes(b"abcdef")

    records = collect_frame_records(tmp_path, width=1920, height=1080)

    assert len(records) == 2
    assert records[0]["frame_index"] == 0
    assert records[0]["relative_path"] == "frames/frame_000001.jpg"
    assert records[0]["width"] == 1920
    assert records[1]["size_bytes"] == 6
