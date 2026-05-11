from __future__ import annotations

import json
import uuid
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from app.core.config import get_settings
from app.core.errors import AppError, ConflictError, ValidationError
from app.core.models import (
    BenchmarkPlanningMode,
    BenchmarkTaskMatrixEntry,
    BenchmarkTaskRecord,
    BenchmarkTaskStatus,
    CaptureRecord,
    ReportRecord,
    ReportStatus,
    RunRecord,
)
from app.hil.evaluation_profiles import list_evaluation_profiles
from app.hil.gateway_runtime_status import resolve_gateway_status
from app.hil.pi_gateway_runtime import probe_pi_gateway
from app.orchestrator.run_manager import RunManager
from app.scenario.environment_presets import list_environment_presets
from app.scenario.library import list_scenario_catalog
from app.scenario.maps import display_map_name
from app.scenario.sensor_profiles import build_sensor_config_from_profile, load_sensor_profiles
from app.storage.artifact_store import ArtifactStore
from app.storage.benchmark_definition_store import BenchmarkDefinitionStore
from app.storage.benchmark_task_store import BenchmarkTaskStore
from app.storage.capture_store import CaptureStore
from app.storage.gateway_store import GatewayStore
from app.storage.project_store import ProjectStore
from app.storage.report_store import ReportStore
from app.storage.run_store import RunStore
from app.utils.file_utils import ensure_dir
from app.utils.time_utils import now_utc, to_iso8601


def _clone_json(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=False))


def _average(values: list[float | None]) -> float | None:
    valid = [value for value in values if isinstance(value, float | int)]
    if not valid:
        return None
    return sum(valid) / len(valid)


def _metric_number(source: dict[str, Any] | None, keys: list[str]) -> float | None:
    if not source:
        return None

    for key in keys:
        value = source.get(key)
        if isinstance(value, float | int):
            return float(value)
        if isinstance(value, str):
            try:
                return float(value)
            except ValueError:
                continue

    lowered_keys = {key.lower() for key in keys}
    for key, value in source.items():
        if key.lower() not in lowered_keys:
            continue
        if isinstance(value, float | int):
            return float(value)
        if isinstance(value, str):
            try:
                return float(value)
            except ValueError:
                continue
    return None


def _optional_markdown_metric(
    label: str, value: Any, *, unit: str = "", code: bool = True
) -> str | None:
    if value is None or value == "":
        return None
    rendered = f"{value}{unit}"
    if code:
        rendered = f"`{rendered}`"
    return f"- {label}: {rendered}"


def _metadata_tag_value(metadata: dict[str, Any] | None, prefix: str) -> str | None:
    if not metadata:
        return None

    tags = metadata.get("tags")
    if not isinstance(tags, list):
        return None

    needle = f"{prefix}:"
    for tag in tags:
        if not isinstance(tag, str) or not tag.startswith(needle):
            continue
        value = tag[len(needle) :].strip()
        return value or None
    return None


def _is_effectively_online_gateway(
    gateway: Any,
    *,
    settings: Any,
    checked_at: Any,
    pi_gateway_status: dict[str, Any],
) -> bool:
    effective_status, _, _ = resolve_gateway_status(
        gateway,
        settings,
        checked_at=checked_at,
        pi_gateway_status=pi_gateway_status,
    )
    return effective_status in {"READY", "BUSY", "DEGRADED"}


def _run_matches_project(run: RunRecord, project_id: str) -> bool:
    metadata = run.descriptor.get("metadata", {})
    if not isinstance(metadata, dict):
        return False

    return (
        _metadata_tag_value(metadata, "project") == project_id
        or _metadata_tag_value(metadata, "chip") == project_id
    )


def _dedupe_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        normalized = value.strip()
        if not normalized or normalized in seen:
            continue
        result.append(normalized)
        seen.add(normalized)
    return result


def _derive_task_status(runs: list[RunRecord]) -> BenchmarkTaskStatus:
    if not runs:
        return BenchmarkTaskStatus.CREATED

    statuses = {run.status.value for run in runs}
    if statuses == {"CREATED"}:
        return BenchmarkTaskStatus.CREATED
    active_statuses = {"CREATED", "QUEUED", "STARTING", "RUNNING", "PAUSED", "STOPPING"}
    if statuses & active_statuses:
        return BenchmarkTaskStatus.RUNNING

    if statuses == {"COMPLETED"}:
        return BenchmarkTaskStatus.COMPLETED
    if statuses <= {"FAILED"}:
        return BenchmarkTaskStatus.FAILED
    if statuses <= {"CANCELED"}:
        return BenchmarkTaskStatus.CANCELED
    if statuses & {"FAILED", "CANCELED"}:
        return BenchmarkTaskStatus.PARTIAL_FAILED
    return BenchmarkTaskStatus.CREATED


class PlatformService:
    def __init__(
        self,
        *,
        project_store: ProjectStore,
        benchmark_definition_store: BenchmarkDefinitionStore,
        benchmark_task_store: BenchmarkTaskStore,
        report_store: ReportStore,
        capture_store: CaptureStore,
        run_store: RunStore,
        run_manager: RunManager,
        artifact_store: ArtifactStore,
        gateway_store: GatewayStore,
        sensor_profiles_root: Path,
        report_artifacts_root: Path,
    ) -> None:
        self._project_store = project_store
        self._benchmark_definition_store = benchmark_definition_store
        self._benchmark_task_store = benchmark_task_store
        self._report_store = report_store
        self._capture_store = capture_store
        self._run_store = run_store
        self._run_manager = run_manager
        self._artifact_store = artifact_store
        self._gateway_store = gateway_store
        self._sensor_profiles_root = sensor_profiles_root
        self._report_artifacts_root = ensure_dir(report_artifacts_root)

    def list_projects(self):
        return self._project_store.list()

    def get_project(self, project_id: str):
        return self._project_store.get(project_id)

    def _definition_project_id(self, definition) -> str | None:
        if getattr(definition, "default_project_id", None):
            return definition.default_project_id
        if len(definition.project_ids) == 1:
            return definition.project_ids[0]
        return None

    def _definition_belongs_to_project(self, definition, project_id: str) -> bool:
        resolved_project_id = self._definition_project_id(definition)
        if resolved_project_id is not None:
            return resolved_project_id == project_id
        return project_id in definition.project_ids

    def _resolve_task_project(self, definition, project_id: str | None):
        requested_project_id = project_id.strip() if project_id and project_id.strip() else None
        resolved_project_id = requested_project_id or self._definition_project_id(definition)
        if not resolved_project_id:
            raise ValidationError(f"模板 {definition.benchmark_definition_id} 缺少默认归档项目")
        project = self._project_store.get(resolved_project_id)
        if project.project_id not in definition.project_ids:
            raise ValidationError(
                f"项目 {resolved_project_id} 不在基准任务 {definition.benchmark_definition_id} 的适用范围内"
            )
        return project

    def get_project_workspace(self, project_id: str) -> dict[str, Any]:
        project = self._project_store.get(project_id)
        benchmark_definitions = [
            item
            for item in self._benchmark_definition_store.list()
            if self._definition_belongs_to_project(item, project.project_id)
        ]
        benchmark_tasks = self.list_benchmark_tasks(project_id=project.project_id)

        runs_by_id: dict[str, RunRecord] = {}
        for task in benchmark_tasks:
            for run_id in task.run_ids:
                if run_id in runs_by_id:
                    continue
                try:
                    runs_by_id[run_id] = self._run_store.get(run_id)
                except AppError:
                    continue

        for run in self._run_store.list():
            if _run_matches_project(run, project.project_id):
                runs_by_id.setdefault(run.run_id, run)

        recent_runs = sorted(runs_by_id.values(), key=lambda item: item.updated_at, reverse=True)
        gateways = sorted(
            self._gateway_store.list(), key=lambda item: item.updated_at, reverse=True
        )
        settings = get_settings()
        checked_at = now_utc()
        pi_gateway_status = probe_pi_gateway(settings)
        runnable_scenarios = self._runnable_scenarios()
        active_run_count = len(
            [
                run
                for run in recent_runs
                if run.status.value
                in {"CREATED", "QUEUED", "STARTING", "RUNNING", "PAUSED", "STOPPING"}
            ]
        )
        online_gateway_count = len(
            [
                gateway
                for gateway in gateways
                if _is_effectively_online_gateway(
                    gateway,
                    settings=settings,
                    checked_at=checked_at,
                    pi_gateway_status=pi_gateway_status,
                )
            ]
        )

        return {
            "project": project,
            "summary": {
                "benchmark_definition_count": len(benchmark_definitions),
                "benchmark_task_count": len(benchmark_tasks),
                "recent_run_count": len(recent_runs),
                "active_run_count": active_run_count,
                "online_gateway_count": online_gateway_count,
                "total_gateway_count": len(gateways),
            },
            "benchmark_definitions": benchmark_definitions,
            "benchmark_tasks": benchmark_tasks[:6],
            "recent_runs": recent_runs[:8],
            "gateways": gateways[:6],
            "scenario_presets": runnable_scenarios,
        }

    def list_benchmark_definitions(self):
        return self._benchmark_definition_store.list()

    def get_benchmark_definition(self, benchmark_definition_id: str):
        return self._benchmark_definition_store.get(benchmark_definition_id)

    def _scenario_catalog_index(
        self, *, include_hidden: bool = True
    ) -> dict[str, dict[str, Any]]:
        return {
            item["scenario_id"]: item
            for item in list_scenario_catalog(include_hidden=include_hidden)
        }

    def _runnable_scenarios(self) -> list[dict[str, Any]]:
        return [
            item
            for item in list_scenario_catalog()
            if str(item.get("execution_support") or "").strip() in {"native"}
        ]

    def _environment_preset_index(self) -> dict[str, dict[str, Any]]:
        return {item["preset_id"]: item for item in list_environment_presets()}

    def _sensor_profile_index(self) -> dict[str, dict[str, Any]]:
        return {
            item["profile_name"]: item for item in load_sensor_profiles(self._sensor_profiles_root)
        }

    def _evaluation_profile_index(self) -> dict[str, dict[str, Any]]:
        return {item["profile_name"]: item for item in list_evaluation_profiles()}

    def _sync_task(self, task: BenchmarkTaskRecord) -> BenchmarkTaskRecord:
        before = task.model_dump(mode="json")
        runs = [self._run_store.get(run_id) for run_id in task.run_ids]
        counts = Counter(run.status.value for run in runs)
        task.counts_by_status = dict(counts)
        task.planned_run_count = len(task.run_ids)
        task.status = _derive_task_status(runs)

        started_times = [run.started_at for run in runs if run.started_at is not None]
        ended_times = [run.ended_at for run in runs if run.ended_at is not None]
        task.started_at = min(started_times) if started_times else None
        task.ended_at = (
            max(ended_times)
            if ended_times and all(run.ended_at is not None for run in runs)
            else None
        )
        task.summary = self._build_task_summary(task, runs)
        after = task.model_dump(mode="json")
        if after != before:
            return self._benchmark_task_store.save(task)
        return task

    def _build_task_summary(
        self, task: BenchmarkTaskRecord, runs: list[RunRecord]
    ) -> dict[str, Any]:
        metrics_payloads = [self._artifact_store.read_metrics(run.run_id) or {} for run in runs]
        run_device_metrics = {
            run.run_id: self._artifact_store.read_device_metrics(run.run_id) or {}
            for run in runs
        }
        fps_values = []
        for metrics in metrics_payloads:
            achieved_tick_rate_hz = metrics.get("achieved_tick_rate_hz")
            if isinstance(achieved_tick_rate_hz, float | int) and achieved_tick_rate_hz > 0:
                fps_values.append(float(achieved_tick_rate_hz))

        terminal_runs = [
            run for run in runs if run.status.value in {"COMPLETED", "FAILED", "CANCELED"}
        ]
        completed_runs = [run for run in runs if run.status.value == "COMPLETED"]
        anomaly_runs = [run for run in runs if run.status.value in {"FAILED", "CANCELED"}]

        gateway_metrics: dict[str, Any] = {}
        if task.hil_config and task.hil_config.get("gateway_id"):
            try:
                gateway = self._gateway_store.get(str(task.hil_config["gateway_id"]))
                gateway_metrics = gateway.metrics
            except Exception:
                gateway_metrics = {}

        scenario_breakdown: dict[str, dict[str, Any]] = defaultdict(
            lambda: {"total_runs": 0, "completed": 0, "failed": 0, "canceled": 0}
        )
        for run in runs:
            entry = scenario_breakdown[run.scenario_name]
            entry["total_runs"] += 1
            if run.status.value == "COMPLETED":
                entry["completed"] += 1
            elif run.status.value == "FAILED":
                entry["failed"] += 1
            elif run.status.value == "CANCELED":
                entry["canceled"] += 1

        active_run = next(
            (
                run
                for run in runs
                if run.status.value in {"STARTING", "RUNNING", "PAUSED", "STOPPING"}
            ),
            None,
        )
        if active_run is not None and run_device_metrics.get(active_run.run_id):
            gateway_metrics = run_device_metrics[active_run.run_id]
        else:
            latest_run_snapshot = max(
                [snapshot for snapshot in run_device_metrics.values() if snapshot],
                key=lambda snapshot: str(snapshot.get("gateway_last_heartbeat_at_utc") or ""),
                default=None,
            )
            if latest_run_snapshot is not None:
                gateway_metrics = latest_run_snapshot
        next_run = next(
            (run for run in runs if run.status.value in {"CREATED", "QUEUED"}),
            None,
        )
        ordered_runs: list[dict[str, Any]] = []
        for index, _run_id in enumerate(task.run_ids):
            run = runs[index]
            matrix_entry = (
                task.scenario_matrix[index] if index < len(task.scenario_matrix) else None
            )
            ordered_runs.append(
                {
                    "position": index + 1,
                    "run_id": run.run_id,
                    "scenario_id": matrix_entry.scenario_id if matrix_entry else None,
                    "scenario_display_name": (
                        matrix_entry.scenario_display_name
                        if matrix_entry is not None
                        else run.scenario_name
                    ),
                    "display_map_name": (
                        matrix_entry.display_map_name if matrix_entry is not None else run.map_name
                    ),
                    "execution_backend": (
                        matrix_entry.execution_backend
                        if matrix_entry is not None
                        else run.execution_backend
                    ),
                    "status": run.status.value,
                    "is_active": active_run is not None and active_run.run_id == run.run_id,
                    "is_next": next_run is not None and next_run.run_id == run.run_id,
                    "started_at_utc": to_iso8601(run.started_at),
                    "ended_at_utc": to_iso8601(run.ended_at),
                    "error_reason": run.error_reason,
                }
            )

        return {
            "counts": {
                "total_runs": len(runs),
                "created_runs": len([run for run in runs if run.status.value == "CREATED"]),
                "queued_runs": len([run for run in runs if run.status.value == "QUEUED"]),
                "completed_runs": len(completed_runs),
                "failed_runs": len([run for run in runs if run.status.value == "FAILED"]),
                "canceled_runs": len([run for run in runs if run.status.value == "CANCELED"]),
                "running_runs": len(
                    [
                        run
                        for run in runs
                        if run.status.value in {"STARTING", "RUNNING", "PAUSED", "STOPPING"}
                    ]
                ),
            },
            "metrics": {
                "fps": _average(fps_values)
                or _metric_number(
                    gateway_metrics,
                    ["output_fps", "inference_fps", "render_fps", "input_fps", "fps"],
                ),
                "latency_ms": _metric_number(
                    gateway_metrics,
                    ["avg_latency_ms", "latency_ms", "p95_latency_ms"],
                ),
                "map": _metric_number(gateway_metrics, ["map50", "mAP", "map"]),
                "power_w": _metric_number(
                    gateway_metrics,
                    ["power_w", "soc_power_w", "board_power_w", "total_power_w"],
                ),
                "temperature_c": _metric_number(
                    gateway_metrics,
                    ["temperature_c", "soc_temp_c", "cpu_temp_c", "board_temp_c"],
                ),
                "frame_drop_rate": _metric_number(
                    gateway_metrics, ["frame_drop_rate", "drop_rate"]
                ),
                "pass_rate": (
                    (len(completed_runs) / len(terminal_runs)) * 100 if terminal_runs else None
                ),
                "anomaly_rate": ((len(anomaly_runs) / len(runs)) * 100 if runs else None),
            },
            "scenario_breakdown": dict(scenario_breakdown),
            "gateway_snapshot": gateway_metrics,
            "execution_queue": {
                "active_run_id": active_run.run_id if active_run is not None else None,
                "next_run_id": next_run.run_id if next_run is not None else None,
                "completed_run_ids": [
                    run.run_id for run in runs if run.status.value == "COMPLETED"
                ],
                "failed_run_ids": [run.run_id for run in runs if run.status.value == "FAILED"],
                "canceled_run_ids": [run.run_id for run in runs if run.status.value == "CANCELED"],
                "queued_run_ids": [
                    run.run_id for run in runs if run.status.value in {"CREATED", "QUEUED"}
                ],
                "ordered_runs": ordered_runs,
            },
        }

    def list_benchmark_tasks(
        self, project_id: str | None = None, status: str | None = None
    ) -> list[BenchmarkTaskRecord]:
        items = [self._sync_task(item) for item in self._benchmark_task_store.list()]
        if project_id is not None:
            items = [item for item in items if item.project_id == project_id]
        if status is not None:
            items = [item for item in items if item.status.value == status]
        return sorted(items, key=lambda item: item.updated_at, reverse=True)

    def get_benchmark_task(self, benchmark_task_id: str) -> BenchmarkTaskRecord:
        return self._sync_task(self._benchmark_task_store.get(benchmark_task_id))

    def list_captures(
        self, status: str | None = None, gateway_id: str | None = None
    ) -> list[CaptureRecord]:
        items = self._capture_store.list()
        if status is not None:
            items = [item for item in items if item.status.value == status]
        if gateway_id is not None:
            items = [item for item in items if item.gateway_id == gateway_id]
        return sorted(items, key=lambda item: item.updated_at, reverse=True)

    def create_benchmark_task(
        self,
        *,
        project_id: str | None,
        benchmark_definition_id: str,
        dut_model: str | None,
        scenario_matrix: list[dict[str, Any]],
        selected_scenario_ids: list[str] | None,
        run_duration_seconds: int | None,
        hil_config: dict[str, Any] | None,
        evaluation_profile_name: str | None,
        auto_start: bool,
    ) -> BenchmarkTaskRecord:
        definition = self._benchmark_definition_store.get(benchmark_definition_id)
        project = self._resolve_task_project(definition, project_id)

        if hil_config and hil_config.get("gateway_id"):
            self._gateway_store.get(str(hil_config["gateway_id"]))

        evaluation_profile = None
        resolved_evaluation_profile_name = (
            evaluation_profile_name or definition.default_evaluation_profile_name
        )
        if resolved_evaluation_profile_name:
            evaluation_profile = self._evaluation_profile_index().get(
                resolved_evaluation_profile_name
            )
            if evaluation_profile is None:
                raise ValidationError(f"未知评测协议: {resolved_evaluation_profile_name}")

        resolved_selected_scenario_ids = _dedupe_strings(selected_scenario_ids or [])
        resolved_requested_duration_seconds = run_duration_seconds
        if not scenario_matrix:
            (
                scenario_matrix,
                resolved_selected_scenario_ids,
                resolved_requested_duration_seconds,
            ) = self._resolve_task_matrix_from_definition(
                definition=definition,
                selected_scenario_ids=resolved_selected_scenario_ids,
                run_duration_seconds=run_duration_seconds,
            )
        elif not resolved_selected_scenario_ids:
            resolved_selected_scenario_ids = _dedupe_strings(
                [str(row.get("scenario_id", "")).strip() for row in scenario_matrix]
            )

        if not scenario_matrix:
            raise ValidationError("当前模板没有生成任何可执行队列")

        scenario_catalog = self._scenario_catalog_index(include_hidden=True)
        normalized_dut_model = dut_model.strip() if dut_model and dut_model.strip() else None

        now = now_utc()
        benchmark_task_id = f"task_{now.strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:8]}"
        created_run_ids: list[str] = []
        normalized_matrix: list[BenchmarkTaskMatrixEntry] = []

        for row in scenario_matrix:
            scenario_id = str(row["scenario_id"]).strip()
            requested_map_name = str(
                row.get("map_name")
                or scenario_catalog.get(scenario_id, {}).get("default_map_name", "")
            ).strip()
            environment_preset_id = str(row.get("environment_preset_id") or "").strip()
            sensor_profile_name = str(row.get("sensor_profile_name") or "").strip()
            requested_timeout_seconds_raw = row.get("timeout_seconds")
            requested_timeout_seconds = (
                int(requested_timeout_seconds_raw)
                if isinstance(requested_timeout_seconds_raw, int | float)
                else None
            )

            scenario = scenario_catalog.get(scenario_id)
            if scenario is None:
                raise ValidationError(f"未知场景: {scenario_id}")
            execution_support = str(scenario.get("execution_support", "")).strip()
            execution_backend = (
                str(
                    scenario.get("execution_backend", execution_support or "native")
                ).strip()
                or "native"
            )
            launch_capabilities = scenario.get("launch_capabilities", {})
            if execution_support not in {"native"}:
                raise ValidationError(f"场景 {scenario_id} 当前不可执行")

            resolved_map_name = requested_map_name or str(scenario["default_map_name"])
            descriptor = _clone_json(scenario["descriptor_template"])
            descriptor["map_name"] = resolved_map_name

            environment_preset = None
            if environment_preset_id:
                environment_preset = self._environment_preset_index().get(environment_preset_id)
                if environment_preset is None:
                    raise ValidationError(f"未知环境预设: {environment_preset_id}")
                descriptor["weather"] = _clone_json(environment_preset["weather"])

            sensor_profile = None
            template_sensor_profile_name = str(
                descriptor.get("sensors", {}).get("profile_name") or ""
            ).strip()
            if sensor_profile_name:
                if sensor_profile_name == template_sensor_profile_name:
                    sensor_profile = None
                elif launch_capabilities.get("sensor_profile_editable", False):
                    sensor_profile = self._sensor_profile_index().get(sensor_profile_name)
                    if sensor_profile is None:
                        raise ValidationError(f"未知传感器模板: {sensor_profile_name}")
                    resolved_sensor_config = build_sensor_config_from_profile(
                        self._sensor_profiles_root,
                        sensor_profile_name,
                    )
                    if resolved_sensor_config is None:
                        raise ValidationError(f"未知传感器模板: {sensor_profile_name}")
                    descriptor["sensors"] = resolved_sensor_config
                else:
                    raise ValidationError(
                        f"场景 {scenario_id} 当前不支持平台侧传感器模板注入"
                    )
            elif "sensors" not in descriptor:
                descriptor["sensors"] = {"enabled": False, "sensors": []}

            termination = dict(descriptor.get("termination") or {})
            resolved_timeout_seconds = int(
                requested_timeout_seconds or termination.get("timeout_seconds") or 30
            )
            termination["timeout_seconds"] = resolved_timeout_seconds
            descriptor["termination"] = termination

            metadata = dict(descriptor.get("metadata") or {})
            existing_tags = list(metadata.get("tags") or [])
            metadata["author"] = "chip-benchmark-platform"
            metadata["dut_model"] = normalized_dut_model
            metadata["description"] = " / ".join(
                part
                for part in [
                    project.name,
                    normalized_dut_model,
                    scenario["display_name"],
                    display_map_name(resolved_map_name),
                ]
                if part
            )
            metadata["tags"] = list(
                dict.fromkeys(
                    [
                        *existing_tags,
                        f"project:{project.project_id}",
                        f"benchmark:{definition.benchmark_definition_id}",
                        f"task:{benchmark_task_id}",
                        f"scenario:{scenario['scenario_name']}",
                        f"execution_backend:{execution_backend}",
                    ]
                )
            )
            descriptor["metadata"] = metadata

            run = self._run_manager.create_run(
                descriptor_payload=descriptor,
                hil_config=hil_config,
                evaluation_profile=evaluation_profile,
            )
            created_run_ids.append(run.run_id)

            normalized_matrix.append(
                BenchmarkTaskMatrixEntry(
                    scenario_id=scenario["scenario_id"],
                    scenario_name=scenario["scenario_name"],
                    scenario_display_name=scenario["display_name"],
                    execution_backend=execution_backend,
                    requested_map_name=requested_map_name,
                    resolved_map_name=resolved_map_name,
                    display_map_name=display_map_name(resolved_map_name),
                    environment_preset_id=(
                        environment_preset["preset_id"]
                        if environment_preset is not None
                        else "scenario_default"
                    ),
                    environment_name=(
                        environment_preset["display_name"]
                        if environment_preset is not None
                        else str(descriptor["weather"].get("preset", "Scenario Default"))
                    ),
                    sensor_profile_name=(
                        sensor_profile["profile_name"]
                        if sensor_profile is not None
                        else str(descriptor.get("sensors", {}).get("profile_name") or "disabled")
                    ),
                    requested_timeout_seconds=requested_timeout_seconds,
                    resolved_timeout_seconds=resolved_timeout_seconds,
                )
            )

        if auto_start and created_run_ids:
            # Only activate the queue head. The remaining runs stay in CREATED and are
            # surfaced by the benchmark-task execution queue until CARLA is free again.
            self._run_manager.start_run(created_run_ids[0])

        task = BenchmarkTaskRecord(
            benchmark_task_id=benchmark_task_id,
            project_id=project.project_id,
            project_name=project.name,
            dut_model=normalized_dut_model,
            benchmark_definition_id=definition.benchmark_definition_id,
            benchmark_name=definition.name,
            planned_run_count=len(created_run_ids),
            counts_by_status={"CREATED": len(created_run_ids)},
            run_ids=created_run_ids,
            scenario_matrix=normalized_matrix,
            planning_mode=definition.planning_mode,
            selected_scenario_ids=resolved_selected_scenario_ids,
            requested_duration_seconds=resolved_requested_duration_seconds,
            hil_config=hil_config,
            evaluation_profile_name=resolved_evaluation_profile_name,
            auto_start=auto_start,
            created_at=now,
            updated_at=now,
        )
        self._benchmark_task_store.create(task)
        return self.get_benchmark_task(benchmark_task_id)

    def rerun_benchmark_task(
        self, benchmark_task_id: str, *, auto_start: bool = True
    ) -> BenchmarkTaskRecord:
        task = self.get_benchmark_task(benchmark_task_id)
        replay_matrix: list[dict[str, Any]] = []

        for entry in task.scenario_matrix:
            replay_matrix.append(
                {
                    "scenario_id": entry.scenario_id,
                    "map_name": entry.requested_map_name or None,
                    "environment_preset_id": (
                        None
                        if entry.environment_preset_id == "scenario_default"
                        else entry.environment_preset_id
                    ),
                    "sensor_profile_name": (
                        None
                        if entry.sensor_profile_name == "disabled"
                        else entry.sensor_profile_name
                    ),
                    "timeout_seconds": (
                        entry.requested_timeout_seconds
                        if entry.requested_timeout_seconds is not None
                        else (
                            entry.resolved_timeout_seconds
                            if task.planning_mode == BenchmarkPlanningMode.TIMED_SINGLE_SCENARIO
                            else None
                        )
                    ),
                }
            )

        return self.create_benchmark_task(
            project_id=task.project_id,
            benchmark_definition_id=task.benchmark_definition_id,
            dut_model=task.dut_model,
            scenario_matrix=replay_matrix,
            selected_scenario_ids=task.selected_scenario_ids,
            run_duration_seconds=task.requested_duration_seconds,
            hil_config=task.hil_config,
            evaluation_profile_name=task.evaluation_profile_name,
            auto_start=auto_start,
        )

    def stop_benchmark_task(self, benchmark_task_id: str) -> BenchmarkTaskRecord:
        task = self.get_benchmark_task(benchmark_task_id)
        handled = False

        for run_id in task.run_ids:
            run = self._run_store.get(run_id)
            if run.status.value in {"COMPLETED", "FAILED", "CANCELED"}:
                continue
            self._run_manager.cancel_run(run_id)
            handled = True

        if not handled:
            raise ConflictError(f"批量任务 {benchmark_task_id} 当前没有可停止的场景")

        return self.get_benchmark_task(benchmark_task_id)

    def _resolve_task_matrix_from_definition(
        self,
        *,
        definition,
        selected_scenario_ids: list[str],
        run_duration_seconds: int | None,
    ) -> tuple[list[dict[str, Any]], list[str], int | None]:
        runnable_scenarios = self._runnable_scenarios()
        runnable_index = {item["scenario_id"]: item for item in runnable_scenarios}

        candidate_ids = _dedupe_strings(definition.candidate_scenario_ids)
        if candidate_ids:
            allowed_ids = [
                scenario_id for scenario_id in candidate_ids if scenario_id in runnable_index
            ]
        else:
            allowed_ids = [item["scenario_id"] for item in runnable_scenarios]

        def ensure_allowed(values: list[str]) -> list[str]:
            normalized = _dedupe_strings(values)
            if not normalized:
                return []
            invalid = [scenario_id for scenario_id in normalized if scenario_id not in allowed_ids]
            if invalid:
                raise ValidationError(
                    f"模板 {definition.benchmark_definition_id} 不允许选择场景: {', '.join(invalid)}"
                )
            return normalized

        if definition.planning_mode == BenchmarkPlanningMode.SINGLE_SCENARIO:
            resolved_ids = ensure_allowed(selected_scenario_ids)
            if len(resolved_ids) != 1:
                raise ValidationError("感知基线评测需要且仅允许选择 1 个场景")
            return [{"scenario_id": resolved_ids[0]}], resolved_ids, None

        if definition.planning_mode == BenchmarkPlanningMode.TIMED_SINGLE_SCENARIO:
            resolved_ids = ensure_allowed(selected_scenario_ids)
            if len(resolved_ids) != 1:
                raise ValidationError("功耗热稳评测需要且仅允许选择 1 个高负载场景")
            resolved_duration_seconds = run_duration_seconds or definition.default_duration_seconds
            if not resolved_duration_seconds:
                raise ValidationError("功耗热稳评测需要提供运行时长")
            return (
                [
                    {
                        "scenario_id": resolved_ids[0],
                        "timeout_seconds": int(resolved_duration_seconds),
                    }
                ],
                resolved_ids,
                int(resolved_duration_seconds),
            )

        if definition.planning_mode == BenchmarkPlanningMode.ALL_RUNNABLE:
            resolved_ids = allowed_ids
            return (
                [{"scenario_id": scenario_id} for scenario_id in resolved_ids],
                resolved_ids,
                None,
            )

        resolved_ids = ensure_allowed(selected_scenario_ids)
        if not resolved_ids:
            raise ValidationError("自定义测试项目至少需要选择 1 个场景")
        return (
            [{"scenario_id": scenario_id} for scenario_id in resolved_ids],
            resolved_ids,
            None,
        )

    def list_reports(
        self,
        benchmark_task_id: str | None = None,
        project_id: str | None = None,
    ) -> list[ReportRecord]:
        items = self._report_store.list()
        if benchmark_task_id is not None:
            items = [item for item in items if item.benchmark_task_id == benchmark_task_id]
        if project_id is not None:
            items = [item for item in items if item.project_id == project_id]
        return sorted(items, key=lambda item: item.updated_at, reverse=True)

    def get_reports_workspace(self) -> dict[str, Any]:
        projects = self.list_projects()
        project_ids = {project.project_id for project in projects}
        benchmark_tasks = [
            task for task in self.list_benchmark_tasks() if task.project_id in project_ids
        ]
        reports = [report for report in self.list_reports() if report.project_id in project_ids]
        recent_failures = sorted(
            [run for run in self._run_store.list() if run.status.value in {"FAILED", "CANCELED"}],
            key=lambda item: item.updated_at,
            reverse=True,
        )
        exportable_tasks = [
            task
            for task in benchmark_tasks
            if task.status.value in {"COMPLETED", "PARTIAL_FAILED", "FAILED", "CANCELED"}
        ]
        reported_task_ids = {report.benchmark_task_id for report in reports}
        pending_report_tasks = [
            task for task in exportable_tasks if task.benchmark_task_id not in reported_task_ids
        ]

        return {
            "summary": {
                "project_count": len(projects),
                "report_count": len(reports),
                "benchmark_task_count": len(benchmark_tasks),
                "exportable_task_count": len(exportable_tasks),
                "pending_report_task_count": len(pending_report_tasks),
                "recent_failure_count": len(recent_failures),
            },
            "projects": projects,
            "reports": reports,
            "benchmark_tasks": benchmark_tasks,
            "exportable_tasks": exportable_tasks,
            "pending_report_tasks": pending_report_tasks,
            "recent_failures": recent_failures[:8],
        }

    def get_devices_workspace(self) -> dict[str, Any]:
        gateways = sorted(
            self._gateway_store.list(), key=lambda item: item.updated_at, reverse=True
        )
        settings = get_settings()
        checked_at = now_utc()
        pi_gateway_status = probe_pi_gateway(settings)
        captures = self.list_captures()
        benchmark_tasks = self.list_benchmark_tasks()
        online_gateways = [
            gateway
            for gateway in gateways
            if _is_effectively_online_gateway(
                gateway,
                settings=settings,
                checked_at=checked_at,
                pi_gateway_status=pi_gateway_status,
            )
        ]
        running_captures = [capture for capture in captures if capture.status.value == "RUNNING"]

        return {
            "summary": {
                "online_device_count": len(online_gateways),
                "running_capture_count": len(running_captures),
                "avg_input_fps": _average(
                    [
                        _metric_number(gateway.metrics, ["input_fps", "fps", "camera_fps"])
                        for gateway in gateways
                    ]
                ),
                "avg_output_fps": _average(
                    [
                        _metric_number(
                            gateway.metrics, ["output_fps", "inference_fps", "render_fps"]
                        )
                        for gateway in gateways
                    ]
                ),
                "avg_frame_drop_rate": _average(
                    [
                        _metric_number(gateway.metrics, ["frame_drop_rate", "drop_rate"])
                        for gateway in gateways
                    ]
                ),
                "avg_power_w": _average(
                    [
                        _metric_number(
                            gateway.metrics,
                            ["power_w", "soc_power_w", "board_power_w", "total_power_w"],
                        )
                        for gateway in gateways
                    ]
                ),
                "avg_temperature_c": _average(
                    [
                        _metric_number(
                            gateway.metrics,
                            ["temperature_c", "soc_temp_c", "cpu_temp_c", "board_temp_c"],
                        )
                        for gateway in gateways
                    ]
                ),
            },
            "gateways": gateways,
            "captures": captures[:8],
            "benchmark_tasks": benchmark_tasks[:6],
        }

    def get_device_workspace(self, gateway_id: str) -> dict[str, Any]:
        gateway = self._gateway_store.get(gateway_id)
        captures = self.list_captures(gateway_id=gateway_id)
        benchmark_tasks = [
            task
            for task in self.list_benchmark_tasks()
            if isinstance(task.hil_config, dict)
            and str(task.hil_config.get("gateway_id") or "").strip() == gateway_id
        ]

        return {
            "gateway": gateway,
            "summary": {
                "capture_count": len(captures),
                "active_capture_count": len(
                    [
                        capture
                        for capture in captures
                        if capture.status.value in {"CREATED", "RUNNING"}
                    ]
                ),
                "linked_benchmark_task_count": len(benchmark_tasks),
                "input_fps": _metric_number(gateway.metrics, ["input_fps", "fps", "camera_fps"]),
                "output_fps": _metric_number(
                    gateway.metrics, ["output_fps", "inference_fps", "render_fps"]
                ),
                "latency_ms": _metric_number(
                    gateway.metrics, ["avg_latency_ms", "latency_ms", "p95_latency_ms"]
                ),
                "frame_drop_rate": _metric_number(
                    gateway.metrics, ["frame_drop_rate", "drop_rate"]
                ),
                "power_w": _metric_number(
                    gateway.metrics,
                    ["power_w", "soc_power_w", "board_power_w", "total_power_w"],
                ),
                "temperature_c": _metric_number(
                    gateway.metrics,
                    ["temperature_c", "soc_temp_c", "cpu_temp_c", "board_temp_c"],
                ),
            },
            "captures": captures,
            "benchmark_tasks": benchmark_tasks[:6],
        }

    def get_report(self, report_id: str) -> ReportRecord:
        return self._report_store.get(report_id)

    def export_report(self, benchmark_task_id: str) -> ReportRecord:
        task = self.get_benchmark_task(benchmark_task_id)
        now = now_utc()
        report_id = f"report_{now.strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:8]}"
        artifact_dir = ensure_dir(self._report_artifacts_root / report_id)
        json_path = artifact_dir / "report.json"
        markdown_path = artifact_dir / "report.md"

        report_payload = {
            "report_id": report_id,
            "benchmark_task_id": task.benchmark_task_id,
            "project_id": task.project_id,
            "project_name": task.project_name,
            "dut_model": task.dut_model,
            "benchmark_definition_id": task.benchmark_definition_id,
            "benchmark_name": task.benchmark_name,
            "status": task.status.value,
            "created_at_utc": now.isoformat(),
            "summary": task.summary,
            "run_ids": task.run_ids,
            "scenario_matrix": [item.model_dump(mode="json") for item in task.scenario_matrix],
        }

        with json_path.open("w", encoding="utf-8") as handle:
            json.dump(report_payload, handle, ensure_ascii=False, indent=2)

        metrics = task.summary.get("metrics", {})
        gateway_snapshot = task.summary.get("gateway_snapshot", {})
        counts = task.summary.get("counts", {})
        markdown_lines = [
            f"# {task.project_name} / {task.benchmark_name}",
            "",
            f"- 报告 ID: `{report_id}`",
            f"- 任务 ID: `{task.benchmark_task_id}`",
            f"- DUT 型号: `{task.dut_model or '未登记'}`",
            f"- 状态: `{task.status.value}`",
            f"- 计划运行数: `{counts.get('total_runs', task.planned_run_count)}`",
            f"- 已完成: `{counts.get('completed_runs', 0)}`",
            f"- 失败: `{counts.get('failed_runs', 0)}`",
            f"- 取消: `{counts.get('canceled_runs', 0)}`",
            "",
            "## 核心指标",
            "",
            f"- FPS: `{metrics.get('fps')}`",
            f"- 延迟(ms): `{metrics.get('latency_ms')}`",
            f"- mAP: `{metrics.get('map')}`",
            f"- 功耗(W): `{metrics.get('power_w')}`",
            f"- 温度(°C): `{metrics.get('temperature_c')}`",
            f"- 场景通过率(%): `{metrics.get('pass_rate')}`",
            f"- 异常率(%): `{metrics.get('anomaly_rate')}`",
            "",
        ]
        dut_snapshot_lines = [
            _optional_markdown_metric("Gateway ID", gateway_snapshot.get("gateway_id")),
            _optional_markdown_metric("Gateway 状态", gateway_snapshot.get("gateway_status")),
            _optional_markdown_metric(
                "模型",
                gateway_snapshot.get("dut_model_name") or gateway_snapshot.get("model_name"),
            ),
            _optional_markdown_metric("DUT 状态", gateway_snapshot.get("dut_status")),
            _optional_markdown_metric(
                "推理输出 FPS",
                _metric_number(
                    gateway_snapshot,
                    ["output_fps", "inference_fps", "render_fps"],
                ),
            ),
            _optional_markdown_metric(
                "平均延迟(ms)",
                _metric_number(
                    gateway_snapshot,
                    ["avg_latency_ms", "latency_ms", "p95_latency_ms"],
                ),
            ),
            _optional_markdown_metric(
                "P95 延迟(ms)",
                _metric_number(gateway_snapshot, ["p95_latency_ms"]),
            ),
            _optional_markdown_metric(
                "功耗(W)",
                _metric_number(
                    gateway_snapshot,
                    ["power_w", "soc_power_w", "board_power_w", "total_power_w"],
                ),
            ),
            _optional_markdown_metric(
                "温度(°C)",
                _metric_number(
                    gateway_snapshot,
                    ["temperature_c", "soc_temp_c", "cpu_temp_c", "board_temp_c"],
                ),
            ),
            _optional_markdown_metric("处理帧数", gateway_snapshot.get("processed_frames")),
            _optional_markdown_metric("检测目标数", gateway_snapshot.get("detection_count")),
            _optional_markdown_metric("相机设备", gateway_snapshot.get("dut_camera_device")),
            _optional_markdown_metric("输入话题", gateway_snapshot.get("dut_input_topic")),
            _optional_markdown_metric("输出话题", gateway_snapshot.get("dut_output_topic")),
            _optional_markdown_metric(
                "最近心跳",
                gateway_snapshot.get("gateway_last_heartbeat_at_utc"),
            ),
            _optional_markdown_metric("最近结果时间", gateway_snapshot.get("dut_received_at_utc")),
            _optional_markdown_metric("错误原因", gateway_snapshot.get("dut_error_reason")),
        ]
        dut_snapshot_lines = [line for line in dut_snapshot_lines if line is not None]
        if dut_snapshot_lines:
            markdown_lines.extend(["## DUT 推理快照", ""])
            markdown_lines.extend(dut_snapshot_lines)
            markdown_lines.append("")

        markdown_lines.extend(["## 场景矩阵", ""])
        for entry in task.scenario_matrix:
            markdown_lines.append(
                f"- {entry.scenario_display_name}: {entry.display_map_name} / {entry.environment_name} / {entry.sensor_profile_name}"
            )

        with markdown_path.open("w", encoding="utf-8") as handle:
            handle.write("\n".join(markdown_lines))
            handle.write("\n")

        report = ReportRecord(
            report_id=report_id,
            benchmark_task_id=task.benchmark_task_id,
            project_id=task.project_id,
            benchmark_definition_id=task.benchmark_definition_id,
            dut_model=task.dut_model,
            title=" / ".join(
                part
                for part in [task.project_name, task.dut_model or "未登记 DUT", task.benchmark_name]
                if part
            ),
            status=ReportStatus.READY,
            artifact_dir=str(artifact_dir),
            json_path=str(json_path),
            markdown_path=str(markdown_path),
            summary=task.summary,
            created_at=now,
            updated_at=now,
        )
        self._report_store.create(report)
        return report
