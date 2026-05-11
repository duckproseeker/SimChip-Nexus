from __future__ import annotations

import uuid
from typing import Any

from app.core.errors import ConflictError, ValidationError
from app.core.models import CaptureFrameRecord, CaptureRecord, CaptureStatus
from app.storage.capture_artifact_store import CaptureArtifactStore
from app.storage.capture_store import CaptureStore
from app.storage.gateway_store import GatewayStore
from app.utils.time_utils import now_utc


class CaptureManager:
    """Control-plane manager for Pi capture task metadata and lifecycle."""

    def __init__(
        self,
        capture_store: CaptureStore,
        capture_artifact_store: CaptureArtifactStore,
        gateway_store: GatewayStore,
    ) -> None:
        self._capture_store = capture_store
        self._capture_artifact_store = capture_artifact_store
        self._gateway_store = gateway_store

    def _build_manifest_payload(self, capture: CaptureRecord) -> dict[str, Any]:
        existing = self._capture_artifact_store.read_manifest(capture.capture_id) or {}
        frames = existing.get("frames", [])
        return {
            "capture_id": capture.capture_id,
            "gateway_id": capture.gateway_id,
            "source": capture.source,
            "save_format": capture.save_format,
            "sample_fps": capture.sample_fps,
            "max_frames": capture.max_frames,
            "save_dir": capture.save_dir,
            "status": capture.status.value,
            "note": capture.note,
            "saved_frames": len(frames),
            "created_at_utc": capture.created_at.isoformat(),
            "started_at_utc": capture.started_at.isoformat() if capture.started_at else None,
            "ended_at_utc": capture.ended_at.isoformat() if capture.ended_at else None,
            "error_reason": capture.error_reason,
            "frames": frames,
        }

    def _persist_manifest(self, capture: CaptureRecord) -> None:
        payload = self._build_manifest_payload(capture)
        self._capture_artifact_store.write_manifest(capture.capture_id, payload)

    def _sync_saved_frame_count(self, capture: CaptureRecord) -> CaptureRecord:
        manifest = self._capture_artifact_store.read_manifest(capture.capture_id) or {}
        frames = manifest.get("frames", [])
        capture.saved_frames = len(frames)
        return capture

    def create_capture(
        self,
        gateway_id: str,
        source: str,
        save_format: str,
        sample_fps: float,
        max_frames: int,
        save_dir: str,
        note: str | None = None,
    ) -> CaptureRecord:
        self._gateway_store.get(gateway_id)

        if sample_fps <= 0:
            raise ValidationError("sample_fps 必须大于 0")
        if max_frames < 1:
            raise ValidationError("max_frames 必须大于等于 1")

        capture_id = f"cap_{now_utc().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:8]}"
        self._capture_artifact_store.init_capture(capture_id)
        manifest_path = self._capture_artifact_store.manifest_path(capture_id)

        capture = CaptureRecord(
            capture_id=capture_id,
            gateway_id=gateway_id,
            source=source,
            save_format=save_format,
            sample_fps=sample_fps,
            max_frames=max_frames,
            save_dir=save_dir,
            manifest_path=str(manifest_path),
            note=note,
            status=CaptureStatus.CREATED,
            created_at=now_utc(),
            updated_at=now_utc(),
        )
        self._capture_store.create(capture)
        self._persist_manifest(capture)
        return capture

    def start_capture(self, capture_id: str) -> CaptureRecord:
        capture = self._capture_store.get(capture_id)
        if capture.status != CaptureStatus.CREATED:
            raise ConflictError(
                f"Capture {capture_id} 仅能从 CREATED 启动，当前状态为 {capture.status.value}"
            )
        running_on_gateway = [
            item
            for item in self._capture_store.list()
            if item.gateway_id == capture.gateway_id
            and item.capture_id != capture_id
            and item.status == CaptureStatus.RUNNING
        ]
        if running_on_gateway:
            raise ConflictError(
                f"网关 {capture.gateway_id} 已存在运行中的采集任务: {running_on_gateway[0].capture_id}"
            )

        def _start(record: CaptureRecord) -> CaptureRecord:
            record.status = CaptureStatus.RUNNING
            if record.started_at is None:
                record.started_at = now_utc()
            record.error_reason = None
            return record

        updated = self._capture_store.update(capture_id, _start)
        updated = self._sync_saved_frame_count(updated)
        self._persist_manifest(updated)
        return updated

    def stop_capture(self, capture_id: str) -> CaptureRecord:
        capture = self._capture_store.get(capture_id)
        if capture.status == CaptureStatus.CREATED:
            target_status = CaptureStatus.CANCELED
        elif capture.status == CaptureStatus.RUNNING:
            target_status = CaptureStatus.STOPPED
        else:
            raise ConflictError(
                f"Capture {capture_id} 在状态 {capture.status.value} 下不可停止"
            )

        def _stop(record: CaptureRecord) -> CaptureRecord:
            record.status = target_status
            record.ended_at = now_utc()
            return record

        updated = self._capture_store.update(capture_id, _stop)
        updated = self._sync_saved_frame_count(updated)
        self._persist_manifest(updated)
        return updated

    def get_capture(self, capture_id: str) -> CaptureRecord:
        capture = self._capture_store.get(capture_id)
        return self._sync_saved_frame_count(capture)

    def list_captures(
        self, status: str | None = None, gateway_id: str | None = None
    ) -> list[CaptureRecord]:
        captures = [self._sync_saved_frame_count(item) for item in self._capture_store.list()]
        if gateway_id is not None:
            captures = [item for item in captures if item.gateway_id == gateway_id]
        if status is None:
            return captures
        try:
            target_status = CaptureStatus(status)
        except ValueError as exc:
            raise ValidationError(f"无效的采集状态过滤值: {status}") from exc
        return [item for item in captures if item.status == target_status]

    def get_manifest(self, capture_id: str) -> dict[str, Any]:
        _ = self._capture_store.get(capture_id)
        manifest = self._capture_artifact_store.read_manifest(capture_id)
        if manifest is None:
            raise ValidationError(f"采集 manifest 不存在: {capture_id}")
        return manifest

    def sync_capture(
        self,
        capture_id: str,
        status: str | None = None,
        saved_frames: int | None = None,
        error_reason: str | None = None,
        frames: list[dict[str, Any]] | None = None,
    ) -> CaptureRecord:
        capture = self._capture_store.get(capture_id)
        parsed_status = capture.status
        if status is not None:
            try:
                parsed_status = CaptureStatus(status)
            except ValueError as exc:
                raise ValidationError(f"无效的采集状态值: {status}") from exc

        manifest = self._capture_artifact_store.read_manifest(capture_id) or self._build_manifest_payload(
            capture
        )
        if frames is not None:
            manifest["frames"] = [
                CaptureFrameRecord.model_validate(item).model_dump(mode="json")
                for item in frames
            ]
        frame_count = (
            saved_frames
            if saved_frames is not None
            else len(manifest.get("frames", []))
        )

        def _apply(record: CaptureRecord) -> CaptureRecord:
            record.status = parsed_status
            record.saved_frames = frame_count
            if parsed_status == CaptureStatus.RUNNING and record.started_at is None:
                record.started_at = now_utc()
            if parsed_status in {
                CaptureStatus.STOPPED,
                CaptureStatus.COMPLETED,
                CaptureStatus.FAILED,
                CaptureStatus.CANCELED,
            }:
                record.ended_at = now_utc()
            if error_reason is not None:
                record.error_reason = error_reason
            return record

        updated = self._capture_store.update(capture_id, _apply)
        manifest.update(
            {
                "status": updated.status.value,
                "saved_frames": updated.saved_frames,
                "started_at_utc": updated.started_at.isoformat()
                if updated.started_at
                else None,
                "ended_at_utc": updated.ended_at.isoformat() if updated.ended_at else None,
                "error_reason": updated.error_reason,
            }
        )
        self._capture_artifact_store.write_manifest(capture_id, manifest)
        return updated

    def get_frames(self, capture_id: str, offset: int, limit: int) -> dict[str, Any]:
        _ = self._capture_store.get(capture_id)
        return self._capture_artifact_store.list_frames(capture_id, offset=offset, limit=limit)
