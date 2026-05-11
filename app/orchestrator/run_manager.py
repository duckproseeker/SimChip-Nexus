from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from pydantic import ValidationError as PydanticValidationError

from app.core.errors import ConflictError, ValidationError
from app.core.models import EventLevel, RunEvent, RunRecord, RunStatus
from app.orchestrator.queue import FileCommandQueue
from app.scenario.library import get_scenario_catalog_item, list_scenario_catalog
from app.scenario.validators import load_descriptor_from_yaml, validate_descriptor
from app.storage.artifact_store import ArtifactStore
from app.storage.gateway_store import GatewayStore
from app.storage.run_store import RunStore
from app.utils.time_utils import now_utc

SUPPORTED_EXECUTION_BACKENDS = {"native"}
ACTIVE_RUN_CONFLICT_STATUSES = {
    RunStatus.QUEUED,
    RunStatus.STARTING,
    RunStatus.RUNNING,
    RunStatus.PAUSED,
    RunStatus.STOPPING,
}


class RunManager:
    """Control-plane orchestrator: create/list/query runs and issue lifecycle commands."""

    def __init__(
        self,
        run_store: RunStore,
        artifact_store: ArtifactStore,
        command_queue: FileCommandQueue,
        gateway_store: GatewayStore | None = None,
    ) -> None:
        self._run_store = run_store
        self._artifact_store = artifact_store
        self._command_queue = command_queue
        self._gateway_store = gateway_store

    def _emit_event(
        self,
        run_id: str,
        event_type: str,
        message: str,
        payload: dict[str, Any] | None = None,
        level: EventLevel = EventLevel.INFO,
    ) -> None:
        event = RunEvent(
            timestamp=now_utc(),
            run_id=run_id,
            level=level,
            event_type=event_type,
            message=message,
            payload=payload or {},
        )
        self._artifact_store.append_event(event)
        self._artifact_store.append_run_log(
            run_id,
            f"[{event.timestamp.isoformat()}] {event.level.value} {event.event_type} {event.message}",
        )

    def _persist_status(self, run: RunRecord) -> None:
        self._artifact_store.write_status(run)

    def build_run_id(self) -> str:
        return f"run_{now_utc().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:8]}"

    @staticmethod
    def _resolved_gateway_id(hil_config: dict[str, Any] | None) -> str:
        if not hil_config:
            return ""
        gateway_value = hil_config.get("gateway_id")
        if gateway_value is None:
            return ""
        return str(gateway_value).strip()

    def create_run(
        self,
        descriptor_payload: dict[str, Any] | None = None,
        descriptor_path: str | None = None,
        hil_config: dict[str, Any] | None = None,
        evaluation_profile: dict[str, Any] | None = None,
        *,
        run_id: str | None = None,
        execution_backend: str | None = None,
        scenario_source: dict[str, Any] | None = None,
        config_snapshot_extra: dict[str, Any] | None = None,
    ) -> RunRecord:
        if descriptor_payload is None and descriptor_path is None:
            raise ValidationError("必须提供 descriptor 或 descriptor_path")

        try:
            if descriptor_path is not None:
                descriptor = load_descriptor_from_yaml(Path(descriptor_path))
            else:
                assert descriptor_payload is not None
                descriptor = validate_descriptor(descriptor_payload)
        except (ValueError, PydanticValidationError) as exc:
            raise ValidationError(f"场景描述校验失败: {exc}") from exc

        scenario_catalog_item = get_scenario_catalog_item(descriptor.scenario_name)
        if scenario_catalog_item is None:
            available_scenarios = sorted(
                item["scenario_id"] for item in list_scenario_catalog()
            )
            raise ValidationError(
                f"未知场景: '{descriptor.scenario_name}'。"
                f"可用场景: {available_scenarios}"
            )
        execution_support = str(scenario_catalog_item.get("execution_support", "")).strip()
        if execution_support not in SUPPORTED_EXECUTION_BACKENDS:
            raise ValidationError(
                f"场景 {descriptor.scenario_name} 当前不可执行，execution_support={execution_support}"
            )
        execution_backend_value = str(
            execution_backend
            or scenario_catalog_item.get(
                "execution_backend", execution_support or "native"
            )
        ).strip() or "native"
        if execution_backend_value not in SUPPORTED_EXECUTION_BACKENDS:
            raise ValidationError(
                f"场景 {descriptor.scenario_name} 当前不可执行，execution_backend={execution_backend_value}"
            )
        scenario_source_value = (
            dict(scenario_source)
            if isinstance(scenario_source, dict)
            else scenario_catalog_item.get("source")
        )

        if hil_config and self._gateway_store is not None:
            gateway_id = self._resolved_gateway_id(hil_config)
            if gateway_id:
                self._gateway_store.get(gateway_id)

        run_id = run_id or self.build_run_id()
        artifact_dir = self._artifact_store.init_run(run_id)

        run = RunRecord(
            run_id=run_id,
            status=RunStatus.CREATED,
            created_at=now_utc(),
            updated_at=now_utc(),
            scenario_name=descriptor.scenario_name,
            map_name=descriptor.map_name,
            descriptor=descriptor.to_dict(),
            hil_config=hil_config,
            evaluation_profile=evaluation_profile,
            artifact_dir=str(artifact_dir),
            execution_backend=execution_backend_value,
            scenario_source=scenario_source_value,
        )
        self._run_store.create(run)
        config_snapshot = {
            "descriptor": descriptor.to_dict(),
            "hil_config": hil_config,
            "evaluation_profile": evaluation_profile,
            "execution_backend": execution_backend_value,
            "scenario_source": scenario_source_value,
        }
        if config_snapshot_extra:
            config_snapshot.update(config_snapshot_extra)
        self._artifact_store.write_config_snapshot(run_id, config_snapshot)
        self._persist_status(run)

        self._emit_event(
            run_id,
            "RUN_CREATED",
            "运行已创建并完成 descriptor 校验",
            payload={
                "scenario_name": descriptor.scenario_name,
                "map_name": descriptor.map_name,
                "execution_backend": execution_backend_value,
                "gateway_id": self._resolved_gateway_id(hil_config) or None,
                "evaluation_profile": (evaluation_profile or {}).get("profile_name"),
            },
        )
        return run

    def start_run(self, run_id: str) -> RunRecord:
        run = self._run_store.get(run_id)
        if run.status != RunStatus.CREATED:
            raise ConflictError(
                f"Run {run_id} 仅能从 CREATED 启动，当前状态为 {run.status.value}"
            )

        conflicting_run = next(
            (
                candidate
                for candidate in self._run_store.list()
                if candidate.run_id != run_id and candidate.status in ACTIVE_RUN_CONFLICT_STATUSES
            ),
            None,
        )
        if conflicting_run is not None:
            raise ConflictError(
                "当前已有活跃运行占用 CARLA："
                f"{conflicting_run.run_id} ({conflicting_run.status.value})。"
                "请先停止或取消当前运行，再启动新的场景。"
            )

        run = self._run_store.transition(run_id, RunStatus.QUEUED)
        self._persist_status(run)
        command = self._command_queue.enqueue_start(run_id)

        self._emit_event(
            run_id,
            "RUN_QUEUED",
            "运行已进入队列，等待 executor 执行",
            payload={"command_id": command.command_id},
        )
        return run

    def stop_run(self, run_id: str) -> RunRecord:
        run = self._run_store.get(run_id)

        if run.status in {RunStatus.CREATED, RunStatus.QUEUED}:
            run = self._run_store.transition(
                run_id, RunStatus.CANCELED, set_ended_at=True
            )
            self._persist_status(run)
            self._emit_event(run_id, "SCENARIO_STOP_REQUESTED", "运行尚未开始，已取消")
            self._emit_event(run_id, "SCENARIO_COMPLETED", "运行在启动前被停止")
            return run

        if run.status in {
            RunStatus.STARTING,
            RunStatus.RUNNING,
            RunStatus.PAUSED,
            RunStatus.STOPPING,
        }:
            run = self._run_store.mark_stop_requested(run_id)
            self._persist_status(run)
            self._emit_event(run_id, "SCENARIO_STOP_REQUESTED", "收到停止请求")
            return run

        raise ConflictError(f"Run {run_id} 在状态 {run.status.value} 下不可停止")

    def cancel_run(self, run_id: str) -> RunRecord:
        run = self._run_store.get(run_id)

        if run.status in {RunStatus.CREATED, RunStatus.QUEUED}:
            run = self._run_store.transition(
                run_id, RunStatus.CANCELED, set_ended_at=True
            )
            self._persist_status(run)
            self._emit_event(run_id, "SCENARIO_STOP_REQUESTED", "运行尚未开始，已取消")
            self._emit_event(run_id, "SCENARIO_COMPLETED", "运行在启动前被取消")
            return run

        if run.status in {
            RunStatus.STARTING,
            RunStatus.RUNNING,
            RunStatus.PAUSED,
            RunStatus.STOPPING,
        }:
            run = self._run_store.mark_stop_requested(run_id, cancel_requested=True)
            self._persist_status(run)
            self._emit_event(run_id, "SCENARIO_STOP_REQUESTED", "收到取消请求")
            return run

        raise ConflictError(f"Run {run_id} 在状态 {run.status.value} 下不可取消")

    def get_run(self, run_id: str) -> RunRecord:
        return self._run_store.get(run_id)

    def list_runs(self, status: str | None = None) -> list[RunRecord]:
        if status is None:
            return self._run_store.list()

        try:
            parsed_status = RunStatus(status)
        except ValueError as exc:
            raise ValidationError(f"无效的状态过滤值: {status}") from exc

        return self._run_store.list(status=parsed_status)

    def get_events(self, run_id: str) -> list[dict[str, Any]]:
        _ = self._run_store.get(run_id)
        return self._artifact_store.read_events(run_id)
