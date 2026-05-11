from __future__ import annotations

import math
import queue
import struct
import tempfile
import time
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ViewerView:
    view_id: str
    label: str
    transform: dict[str, float]
    attachment_type: str


VIEWER_VIEWS: tuple[ViewerView, ...] = (
    ViewerView(
        view_id="first_person",
        label="第一视角",
        transform={
            "x": 1.45,
            "y": 0.0,
            "z": 1.62,
            "pitch": -2.0,
            "yaw": 0.0,
            "roll": 0.0,
        },
        attachment_type="rigid",
    ),
    ViewerView(
        view_id="third_person",
        label="第三视角",
        transform={
            "x": -6.0,
            "y": 0.0,
            "z": 2.6,
            "pitch": -12.0,
            "yaw": 0.0,
            "roll": 0.0,
        },
        attachment_type="spring_arm",
    ),
)


class EgoSnapshotViewerError(RuntimeError):
    """Raised when a read-only viewer snapshot cannot be collected."""


@dataclass
class EgoViewerStreamSession:
    viewer: EgoSnapshotViewer
    sensor: Any
    image_queue: queue.Queue[Any]
    temp_dir: Any

    def capture_png_bytes(self, timeout_seconds: float = 2.5) -> bytes:
        try:
            image = self.image_queue.get(timeout=timeout_seconds)
        except queue.Empty as exc:
            raise EgoSnapshotViewerError(
                "未在超时时间内收到 viewer 帧，请确认 run 正在推进"
            ) from exc
        return self.viewer._image_to_png_bytes(
            image, output_dir=Path(self.temp_dir.name)
        )

    def close(self) -> None:
        try:
            self.sensor.stop()
        except Exception:
            pass
        try:
            self.sensor.destroy()
        except Exception:
            pass
        self.temp_dir.cleanup()


class EgoSnapshotViewer:
    """Read-only CARLA snapshot viewer.

    This class follows the same constraint as `scripts/ego_viewer.py`:
    it never calls `world.tick()` and only attaches a temporary camera
    to the already-running ego vehicle.
    """

    def __init__(
        self,
        *,
        host: str,
        port: int,
        timeout_seconds: float,
        width: int = 1280,
        height: int = 720,
        role_names: tuple[str, ...] = ("ego_vehicle", "hero", "ego"),
        preferred_actor_id: int | None = None,
        preferred_spawn_point: dict[str, float] | None = None,
        ego_wait_timeout_seconds: float = 5.0,
        poll_interval_seconds: float = 0.35,
    ) -> None:
        self._host = host
        self._port = port
        self._timeout_seconds = timeout_seconds
        self._width = width
        self._height = height
        self._preferred_actor_id = preferred_actor_id
        self._preferred_spawn_point = preferred_spawn_point
        self._ego_wait_timeout_seconds = ego_wait_timeout_seconds
        self._poll_interval_seconds = poll_interval_seconds
        self._role_names = tuple(
            role_name.strip().lower() for role_name in role_names if role_name.strip()
        )

        self._carla: Any = None
        self._client: Any = None
        self._world: Any = None

    def _connect(self) -> None:
        try:
            import carla  # type: ignore
        except ImportError as exc:
            raise EgoSnapshotViewerError(
                "viewer 依赖 carla Python API，当前 API 进程环境不可用"
            ) from exc

        self._carla = carla
        try:
            self._client = carla.Client(self._host, self._port)
            self._client.set_timeout(self._timeout_seconds)
            self._world = self._client.get_world()
        except Exception as exc:
            # specifically catch carla.client.TimeoutException or other C++ aborts mapped to Python
            raise EgoSnapshotViewerError(f"Failed to connect to CARLA world: {exc}") from exc

    def _refresh_world(self) -> None:
        if self._client is None:
            raise EgoSnapshotViewerError("CARLA client 未连接")
        try:
            self._world = self._client.get_world()
        except Exception as exc:
            raise EgoSnapshotViewerError(f"Failed to refresh CARLA world: {exc}") from exc

    @staticmethod
    def _vehicle_sort_key(vehicle: Any) -> tuple[int, float]:
        velocity = vehicle.get_velocity()
        speed = math.sqrt(
            velocity.x * velocity.x
            + velocity.y * velocity.y
            + velocity.z * velocity.z
        )
        alive = 1 if vehicle.is_alive else 0
        return alive, speed

    @staticmethod
    def _distance_to_spawn(vehicle: Any, spawn_point: dict[str, float]) -> float:
        transform = vehicle.get_transform()
        dx = float(transform.location.x) - float(spawn_point["x"])
        dy = float(transform.location.y) - float(spawn_point["y"])
        dz = float(transform.location.z) - float(spawn_point["z"])
        return math.sqrt(dx * dx + dy * dy + dz * dz)

    @staticmethod
    def _vehicle_preview(vehicles: list[Any], max_items: int = 8) -> str:
        preview = []
        for vehicle in vehicles[:max_items]:
            preview.append(
                f"{vehicle.id}:{vehicle.attributes.get('role_name', '').strip() or '<empty>'}"
            )
        return ", ".join(preview) if preview else "<none>"

    def _find_ego_vehicle_once(self) -> Any | None:
        if self._world is None:
            raise EgoSnapshotViewerError("CARLA world 未连接")

        vehicles = list(self._world.get_actors().filter("vehicle.*"))
        alive_vehicles = [vehicle for vehicle in vehicles if getattr(vehicle, "is_alive", False)]

        if self._preferred_actor_id is not None:
            for vehicle in alive_vehicles:
                if int(vehicle.id) == int(self._preferred_actor_id):
                    return vehicle

        for role_name in self._role_names:
            matches = [
                vehicle
                for vehicle in alive_vehicles
                if vehicle.attributes.get("role_name", "").strip().lower() == role_name
            ]
            if matches:
                matches.sort(key=self._vehicle_sort_key, reverse=True)
                return matches[0]

        if len(alive_vehicles) == 1:
            return alive_vehicles[0]

        if self._preferred_spawn_point and alive_vehicles:
            closest = min(
                alive_vehicles,
                key=lambda vehicle: self._distance_to_spawn(
                    vehicle, self._preferred_spawn_point
                ),
            )
            distance_m = self._distance_to_spawn(closest, self._preferred_spawn_point)
            if distance_m <= 12.0:
                return closest

        return None

    def _wait_for_ego_vehicle(self) -> Any:
        deadline = time.monotonic() + max(0.5, self._ego_wait_timeout_seconds)
        last_preview = "<none>"
        last_count = 0

        while time.monotonic() < deadline:
            self._refresh_world()
            assert self._world is not None
            vehicles = list(self._world.get_actors().filter("vehicle.*"))
            last_count = len(vehicles)
            last_preview = self._vehicle_preview(vehicles)

            ego_vehicle = self._find_ego_vehicle_once()
            if ego_vehicle is not None:
                return ego_vehicle

            time.sleep(self._poll_interval_seconds)

        raise EgoSnapshotViewerError(
            "当前 world 中未找到 ego_vehicle"
            f"（vehicles={last_count}, preview={last_preview}）"
        )

    def _camera_blueprint(self) -> Any:
        if self._world is None:
            raise EgoSnapshotViewerError("CARLA world 未连接")

        bp = self._world.get_blueprint_library().find("sensor.camera.rgb")
        bp.set_attribute("image_size_x", str(self._width))
        bp.set_attribute("image_size_y", str(self._height))
        bp.set_attribute("fov", "100")
        if bp.has_attribute("sensor_tick"):
            bp.set_attribute("sensor_tick", "0.0")
        return bp

    def _viewer_view(self, view_id: str) -> ViewerView:
        for view in VIEWER_VIEWS:
            if view.view_id == view_id:
                return view
        raise EgoSnapshotViewerError(f"未知 viewer 视角: {view_id}")

    @staticmethod
    def _image_queue_handler(image_queue: queue.Queue[Any]) -> Any:
        def on_image(image: Any) -> None:
            try:
                if image_queue.full():
                    _ = image_queue.get_nowait()
                image_queue.put_nowait(image)
            except queue.Empty:
                pass
            except queue.Full:
                pass

        return on_image

    def _build_transform(self, view: ViewerView) -> Any:
        assert self._carla is not None
        return self._carla.Transform(
            self._carla.Location(
                x=view.transform["x"],
                y=view.transform["y"],
                z=view.transform["z"],
            ),
            self._carla.Rotation(
                pitch=view.transform["pitch"],
                yaw=view.transform["yaw"],
                roll=view.transform["roll"],
            ),
        )

    def _spawn_viewer_sensor(self, ego_vehicle: Any, view_id: str, image_queue: queue.Queue[Any]) -> Any:
        assert self._world is not None
        assert self._carla is not None
        viewer_view = self._viewer_view(view_id)
        sensor = self._world.spawn_actor(
            self._camera_blueprint(),
            self._build_transform(viewer_view),
            attach_to=ego_vehicle,
            attachment_type=(
                self._carla.AttachmentType.SpringArmGhost
                if viewer_view.attachment_type == "spring_arm"
                else self._carla.AttachmentType.Rigid
            ),
        )
        sensor.listen(self._image_queue_handler(image_queue))
        return sensor

    @staticmethod
    def _write_image_to_path(image: Any, image_path: Path) -> bytes:
        image.save_to_disk(str(image_path))
        return image_path.read_bytes()

    @staticmethod
    def _png_chunk(chunk_type: bytes, payload: bytes) -> bytes:
        return b"".join(
            [
                struct.pack(">I", len(payload)),
                chunk_type,
                payload,
                struct.pack(">I", zlib.crc32(chunk_type + payload) & 0xFFFFFFFF),
            ]
        )

    @staticmethod
    def _raw_bgra_to_png_bytes(image: Any) -> bytes:
        width = int(image.width)
        height = int(image.height)
        raw_data = memoryview(bytes(image.raw_data))
        row_stride = width * 4
        rgb_rows = bytearray((width * 3 + 1) * height)
        write_offset = 0

        for row_index in range(height):
            row_start = row_index * row_stride
            rgb_rows[write_offset] = 0
            write_offset += 1
            for pixel_offset in range(row_start, row_start + row_stride, 4):
                blue = raw_data[pixel_offset]
                green = raw_data[pixel_offset + 1]
                red = raw_data[pixel_offset + 2]
                rgb_rows[write_offset] = red
                rgb_rows[write_offset + 1] = green
                rgb_rows[write_offset + 2] = blue
                write_offset += 3

        compressed = zlib.compress(bytes(rgb_rows), level=1)
        header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
        return b"".join(
            [
                b"\x89PNG\r\n\x1a\n",
                EgoSnapshotViewer._png_chunk(b"IHDR", header),
                EgoSnapshotViewer._png_chunk(b"IDAT", compressed),
                EgoSnapshotViewer._png_chunk(b"IEND", b""),
            ]
        )

    def _image_to_png_bytes(self, image: Any, *, output_dir: Path | None = None) -> bytes:
        try:
            return self._raw_bgra_to_png_bytes(image)
        except Exception:
            pass

        if output_dir is not None:
            image_path = output_dir / "frame.png"
            return self._write_image_to_path(image, image_path)

        with tempfile.TemporaryDirectory(prefix="ego-snapshot-") as tmp_dir:
            image_path = Path(tmp_dir) / "frame.png"
            return self._write_image_to_path(image, image_path)

    def open_stream_session(self, *, view_id: str) -> EgoViewerStreamSession:
        self._connect()
        ego_vehicle = self._wait_for_ego_vehicle()
        image_queue: queue.Queue[Any] = queue.Queue(maxsize=2)
        temp_dir = tempfile.TemporaryDirectory(prefix="ego-stream-")
        sensor = self._spawn_viewer_sensor(ego_vehicle, view_id, image_queue)
        return EgoViewerStreamSession(
            viewer=self,
            sensor=sensor,
            image_queue=image_queue,
            temp_dir=temp_dir,
        )

    def capture_png_bytes(self, *, view_id: str) -> bytes:
        session = self.open_stream_session(view_id=view_id)
        try:
            return session.capture_png_bytes()
        finally:
            session.close()


def list_viewer_views() -> list[dict[str, str]]:
    return [{"view_id": item.view_id, "label": item.label} for item in VIEWER_VIEWS]
