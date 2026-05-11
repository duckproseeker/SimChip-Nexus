from __future__ import annotations

import argparse
import os
import signal
import sys
import threading
import time
from dataclasses import dataclass
from typing import Any

try:
    import cv2
except ImportError:  # pragma: no cover - exercised on Jetson runtime
    cv2 = None  # type: ignore[assignment]

try:
    import rclpy
    from rclpy.node import Node
    from rclpy.qos import (
        QoSDurabilityPolicy,
        QoSHistoryPolicy,
        QoSProfile,
        QoSReliabilityPolicy,
    )
    from sensor_msgs.msg import Image
except ImportError:  # pragma: no cover - exercised on Jetson runtime
    rclpy = None  # type: ignore[assignment]
    Node = object  # type: ignore[misc, assignment]
    QoSDurabilityPolicy = None  # type: ignore[misc, assignment]
    QoSHistoryPolicy = None  # type: ignore[misc, assignment]
    QoSProfile = None  # type: ignore[misc, assignment]
    QoSReliabilityPolicy = None  # type: ignore[misc, assignment]
    Image = Any  # type: ignore[misc, assignment]


def now_utc_iso8601() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def log(message: str) -> None:
    sys.stdout.write(f"{now_utc_iso8601()} jetson-rtp-camera {message}\n")
    sys.stdout.flush()


@dataclass(frozen=True)
class JetsonRtpCameraSettings:
    port: int
    host: str
    topic: str
    frame_id: str
    decoder: str
    buffer_size: int = 4_194_304
    jitter_latency_ms: int = 50
    swap_rb: bool = False


def env_flag(name: str, default: bool = False) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    return raw_value.strip().lower() in {"1", "true", "yes", "on"}


def build_image_qos_profile() -> Any:
    if QoSProfile is None:  # pragma: no cover - guarded by runtime import
        return 10
    return QoSProfile(
        history=QoSHistoryPolicy.KEEP_LAST,
        depth=1,
        reliability=QoSReliabilityPolicy.BEST_EFFORT,
        durability=QoSDurabilityPolicy.VOLATILE,
    )


def parse_args(argv: list[str] | None = None) -> tuple[JetsonRtpCameraSettings, list[str]]:
    parser = argparse.ArgumentParser(description="Receive RTP H264 and publish /image_raw")
    parser.add_argument("--port", type=int, default=int(os.getenv("JETSON_RTP_PORT", "5000")))
    parser.add_argument("--host", default=os.getenv("JETSON_RTP_HOST", "0.0.0.0"))
    parser.add_argument("--topic", default=os.getenv("JETSON_RTP_TOPIC", "/image_raw"))
    parser.add_argument("--frame-id", default=os.getenv("JETSON_RTP_FRAME_ID", "camera"))
    parser.add_argument("--decoder", default=os.getenv("JETSON_RTP_DECODER", "nvv4l2decoder"))
    parser.add_argument(
        "--buffer-size",
        type=int,
        default=int(os.getenv("JETSON_RTP_BUFFER_SIZE", "4194304")),
    )
    parser.add_argument(
        "--jitter-latency-ms",
        type=int,
        default=int(os.getenv("JETSON_RTP_JITTER_LATENCY_MS", "50")),
    )
    parser.add_argument(
        "--swap-rb",
        action="store_true",
        default=env_flag("JETSON_RTP_SWAP_RB", default=False),
        help="Swap the red and blue channels before publishing the ROS image.",
    )
    args, ros_args = parser.parse_known_args(argv)

    settings = JetsonRtpCameraSettings(
        port=max(int(args.port), 1),
        host=str(args.host).strip() or "0.0.0.0",
        topic=str(args.topic).strip() or "/image_raw",
        frame_id=str(args.frame_id).strip() or "camera",
        decoder=str(args.decoder).strip() or "nvv4l2decoder",
        buffer_size=max(int(args.buffer_size), 0),
        jitter_latency_ms=max(int(args.jitter_latency_ms), 0),
        swap_rb=bool(args.swap_rb),
    )
    return settings, ros_args


def build_gstreamer_pipeline(settings: JetsonRtpCameraSettings) -> str:
    caps = (
        "application/x-rtp,media=video,clock-rate=90000,"
        "encoding-name=H264,payload=96"
    )
    if settings.decoder == "nvv4l2decoder":
        decode_chain = (
            "rtph264depay ! h264parse ! nvv4l2decoder enable-max-performance=1 ! "
            "nvvidconv ! video/x-raw,format=BGRx ! videoconvert ! video/x-raw,format=BGR"
        )
    else:
        decode_chain = (
            f"rtph264depay ! h264parse ! {settings.decoder} ! videoconvert ! "
            "video/x-raw,format=BGR"
        )

    return (
        f"udpsrc address={settings.host} port={settings.port} "
        f"buffer-size={settings.buffer_size} caps=\"{caps}\" ! "
        f"rtpjitterbuffer latency={settings.jitter_latency_ms} drop-on-latency=true ! "
        "queue max-size-buffers=4 leaky=downstream ! "
        f"{decode_chain} ! "
        "appsink drop=true max-buffers=1 sync=false"
    )


def frame_to_image_message(frame: Any, stamp: Any, frame_id: str) -> Image:
    if Image is Any:  # pragma: no cover - guarded by runtime import
        raise RuntimeError("sensor_msgs is not available")

    msg = Image()
    msg.header.stamp = stamp
    msg.header.frame_id = frame_id
    msg.height = int(frame.shape[0])
    msg.width = int(frame.shape[1])
    msg.encoding = "bgr8"
    msg.is_bigendian = 0
    msg.step = int(frame.shape[1] * frame.shape[2])
    msg.data = frame.tobytes()
    return msg


class JetsonRtpCameraNode(Node):
    def __init__(self, settings: JetsonRtpCameraSettings) -> None:
        super().__init__("jetson_rtp_camera")
        self._settings = settings
        self._publisher = self.create_publisher(
            Image,
            settings.topic,
            build_image_qos_profile(),
        )
        self._stop_event = threading.Event()
        self._capture_lock = threading.Lock()
        self._capture = self._open_capture()
        self._thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._frames_total = 0
        self._frames_since_log = 0
        self._last_log_monotonic = time.monotonic()
        self._last_failure_log_monotonic = 0.0
        self._thread.start()

    def _open_capture(self) -> Any:
        if cv2 is None:  # pragma: no cover - exercised on Jetson runtime
            raise RuntimeError("OpenCV with GStreamer support is required")

        pipeline = build_gstreamer_pipeline(self._settings)
        self.get_logger().info(
            f"opening RTP stream topic={self._settings.topic} port={self._settings.port}"
        )
        self.get_logger().info(f"gstreamer_pipeline={pipeline}")
        capture = cv2.VideoCapture(pipeline, cv2.CAP_GSTREAMER)
        if not capture.isOpened():
            raise RuntimeError(f"failed to open RTP stream with pipeline: {pipeline}")
        return capture

    def _capture_loop(self) -> None:
        while not self._stop_event.is_set():
            with self._capture_lock:
                ok, frame = self._capture.read()
            if not ok:
                self._log_read_failure()
                time.sleep(0.05)
                continue

            if self._settings.swap_rb:
                frame = frame[:, :, ::-1].copy()

            stamp = self.get_clock().now().to_msg()
            msg = frame_to_image_message(frame, stamp, self._settings.frame_id)
            self._publisher.publish(msg)
            self._frames_total += 1
            self._frames_since_log += 1
            self._maybe_log_fps(frame)

    def _log_read_failure(self) -> None:
        now_monotonic = time.monotonic()
        if (now_monotonic - self._last_failure_log_monotonic) < 5.0:
            return
        self._last_failure_log_monotonic = now_monotonic
        self.get_logger().warning(
            f"waiting for RTP video frames on udp/{self._settings.port}"
        )

    def _maybe_log_fps(self, frame: Any) -> None:
        now_monotonic = time.monotonic()
        elapsed = now_monotonic - self._last_log_monotonic
        if elapsed < 1.0:
            return
        fps = self._frames_since_log / elapsed if elapsed > 0 else 0.0
        height = int(frame.shape[0])
        width = int(frame.shape[1])
        self.get_logger().info(
            f"publishing topic={self._settings.topic} fps={fps:.2f} "
            f"resolution={width}x{height} frames_total={self._frames_total}"
        )
        self._frames_since_log = 0
        self._last_log_monotonic = now_monotonic

    def close(self) -> None:
        self._stop_event.set()
        with self._capture_lock:
            if hasattr(self, "_capture") and self._capture is not None:
                self._capture.release()
        if hasattr(self, "_thread"):
            self._thread.join(timeout=2.0)


def main(argv: list[str] | None = None) -> int:
    settings, ros_args = parse_args(argv)
    if rclpy is None:  # pragma: no cover - exercised on Jetson runtime
        raise SystemExit("rclpy is required to run jetson_rtp_camera_node")

    rclpy.init(args=ros_args)
    node = JetsonRtpCameraNode(settings)

    def _request_shutdown(signum: int, frame: Any) -> None:
        log(f"received signal={signum}, shutting down")
        if rclpy.ok():
            rclpy.shutdown()

    signal.signal(signal.SIGINT, _request_shutdown)
    signal.signal(signal.SIGTERM, _request_shutdown)

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.close()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
