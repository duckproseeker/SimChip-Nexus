from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from typing import Any, Callable

from app.core.errors import NotFoundError
from app.core.models import EventLevel
from app.hil.gateway_runtime_status import gateway_matches_configured_pi, resolve_gateway_status
from app.hil.pi_gateway_runtime import probe_pi_gateway
from app.storage.gateway_store import GatewayStore
from app.utils.time_utils import now_utc


@dataclass(frozen=True)
class HilRuntimeStep:
    step_id: str
    label: str
    start_command: str | None = None
    stop_command: str | None = None


@dataclass(frozen=True)
class HilRuntimeStartDecision:
    payload: dict[str, Any]
    allow_host_carla: bool = True
    allow_host_display: bool = True
    allow_pi_pipeline: bool = True
    allow_jetson_pipeline: bool = True
    message: str | None = None
    level: EventLevel = EventLevel.INFO

    def allows_step(self, step_id: str) -> bool:
        if step_id == "host_carla":
            return self.allow_host_carla
        if step_id == "host_display":
            return self.allow_host_display
        if step_id == "pi_pipeline":
            return self.allow_pi_pipeline
        if step_id == "jetson_pipeline":
            return self.allow_jetson_pipeline
        return True

    def has_restrictions(self) -> bool:
        return not all(
            [
                self.allow_host_carla,
                self.allow_host_display,
                self.allow_pi_pipeline,
                self.allow_jetson_pipeline,
            ]
        )

    def allows_any_steps(self) -> bool:
        return any(
            [
                self.allow_host_carla,
                self.allow_host_display,
                self.allow_pi_pipeline,
                self.allow_jetson_pipeline,
            ]
        )


class HilRuntimeOrchestrator:
    def __init__(
        self,
        settings: Any,
        *,
        event_callback: Callable[[str, str, str], None] | Callable[..., None] | None = None,
        log_callback: Callable[[str, str], None] | None = None,
    ) -> None:
        self._settings = settings
        self._event_callback = event_callback
        self._log_callback = log_callback
        self._gateway_store = GatewayStore(self._settings.gateways_root)

    def applies_to_run(self, run: Any) -> bool:
        if not self._settings.hil_orchestration_enabled:
            return False
        hil_config = run.hil_config or {}
        return bool(hil_config) and str(hil_config.get("mode") or "").strip().lower() == "camera_open_loop"

    def start_pipeline(
        self,
        run_id: str,
        run: Any,
        descriptor: Any,
    ) -> list[HilRuntimeStep]:
        if not self.applies_to_run(run):
            return []

        steps = self._resolve_steps()
        if not any(step.start_command for step in steps):
            self._emit_event(
                run_id,
                "HIL_RUNTIME_SKIPPED",
                "当前 run 绑定了 HIL，但没有配置可执行的 sidecar 启动命令",
                level=EventLevel.WARNING,
            )
            return []

        start_decision = self._resolve_start_decision(run_id, run)
        if start_decision.has_restrictions() and start_decision.message:
            self._emit_event(
                run_id,
                "HIL_RUNTIME_DEGRADED" if start_decision.allows_any_steps() else "HIL_RUNTIME_SKIPPED",
                start_decision.message,
                payload=start_decision.payload,
                level=start_decision.level,
            )
            self._append_log(
                run_id,
                (
                    "[hil_runtime] start degraded: "
                    f"reason={start_decision.message} payload={start_decision.payload}"
                ),
            )
            if not start_decision.allows_any_steps():
                return []

        env = self._build_command_env(run_id, run, descriptor)
        started_steps: list[HilRuntimeStep] = []
        for step in steps:
            if not start_decision.allows_step(step.step_id):
                self._emit_event(
                    run_id,
                    "HIL_RUNTIME_STEP_SKIPPED",
                    self._step_skip_message(step, start_decision),
                    payload={"step_id": step.step_id, **start_decision.payload},
                    level=start_decision.level,
                )
                self._append_log(
                    run_id,
                    (
                        f"[hil_runtime:{step.step_id}] start skipped: "
                        f"reason={start_decision.message or 'step disallowed'} "
                        f"payload={start_decision.payload}"
                    ),
                )
                continue
            if not step.start_command:
                self._emit_event(
                    run_id,
                    "HIL_RUNTIME_STEP_SKIPPED",
                    f"{step.label} 未配置启动命令，跳过",
                    payload={"step_id": step.step_id},
                    level=EventLevel.WARNING,
                )
                continue

            self._emit_event(
                run_id,
                "HIL_RUNTIME_STEP_STARTING",
                f"正在启动 {step.label}",
                payload={"step_id": step.step_id},
            )
            self._run_shell_command(run_id, step, step.start_command, env, phase="start")
            started_steps.append(step)
            self._emit_event(
                run_id,
                "HIL_RUNTIME_STEP_READY",
                f"{step.label} 已启动",
                payload={"step_id": step.step_id},
            )
        return started_steps

    def _resolve_start_decision(self, run_id: str, run: Any) -> HilRuntimeStartDecision:
        hil_config = run.hil_config or {}
        gateway_id = str(hil_config.get("gateway_id") or "").strip()
        if not gateway_id:
            return HilRuntimeStartDecision(
                allow_host_carla=True,
                allow_host_display=True,
                allow_pi_pipeline=False,
                allow_jetson_pipeline=False,
                message="当前 run 未选择树莓派网关，已跳过 Pi 注入链路并继续启动 Host CARLA / 跟随视角",
                payload={
                    "gateway_id": None,
                    "hil_mode": str(hil_config.get("mode") or ""),
                    "reason_code": "gateway_not_selected",
                },
                level=EventLevel.INFO,
            )

        try:
            gateway = self._gateway_store.get(gateway_id)
        except NotFoundError:
            return HilRuntimeStartDecision(
                allow_host_carla=True,
                allow_host_display=True,
                allow_pi_pipeline=False,
                allow_jetson_pipeline=False,
                message=f"指定树莓派网关不存在，已跳过 Pi 注入链路并继续启动 Host CARLA / 跟随视角: {gateway_id}",
                payload={
                    "gateway_id": gateway_id,
                    "reason_code": "gateway_not_found",
                },
                level=EventLevel.WARNING,
            )

        pi_gateway_status = probe_pi_gateway(self._settings)
        checked_at = now_utc()
        effective_status, heartbeat_age_seconds, status_detail = resolve_gateway_status(
            gateway,
            self._settings,
            checked_at=checked_at,
            pi_gateway_status=pi_gateway_status,
        )
        payload = {
            "gateway_id": gateway_id,
            "gateway_record_status": gateway.status.value,
            "gateway_effective_status": effective_status,
            "gateway_status_detail": status_detail,
            "gateway_current_run_id": gateway.current_run_id,
            "heartbeat_age_seconds": heartbeat_age_seconds,
            "gateway_checked_at_utc": checked_at.isoformat(),
            "pi_gateway_status": pi_gateway_status,
            "configured_pi_match": gateway_matches_configured_pi(gateway, self._settings),
        }

        if not payload["configured_pi_match"]:
            return HilRuntimeStartDecision(
                allow_host_carla=True,
                allow_host_display=True,
                allow_pi_pipeline=False,
                allow_jetson_pipeline=False,
                message="选中的树莓派网关与当前平台配置的 Pi 主机不匹配，已跳过 Pi 注入链路并继续启动 Host CARLA / 跟随视角",
                payload={**payload, "reason_code": "gateway_host_mismatch"},
                level=EventLevel.WARNING,
            )

        if not pi_gateway_status.get("configured"):
            return HilRuntimeStartDecision(
                allow_host_carla=True,
                allow_host_display=True,
                allow_pi_pipeline=False,
                allow_jetson_pipeline=False,
                message="平台未完成树莓派链路配置，已跳过 Pi 注入链路并继续启动 Host CARLA / 跟随视角",
                payload={**payload, "reason_code": "pi_gateway_not_configured"},
                level=EventLevel.WARNING,
            )

        if not pi_gateway_status.get("reachable"):
            return HilRuntimeStartDecision(
                allow_host_carla=True,
                allow_host_display=True,
                allow_pi_pipeline=False,
                allow_jetson_pipeline=False,
                message="树莓派网关当前不可达，已跳过 Pi 注入链路并继续启动 Host CARLA / 跟随视角",
                payload={**payload, "reason_code": "pi_gateway_unreachable"},
                level=EventLevel.WARNING,
            )

        if effective_status != "READY":
            return HilRuntimeStartDecision(
                allow_host_carla=True,
                allow_host_display=True,
                allow_pi_pipeline=False,
                allow_jetson_pipeline=False,
                message=(
                    "树莓派网关未处于 READY 状态，已跳过 Pi 注入链路并继续启动 Host CARLA / 跟随视角"
                    f" (当前: {effective_status})"
                ),
                payload={**payload, "reason_code": "gateway_not_ready"},
                level=EventLevel.WARNING,
            )

        return HilRuntimeStartDecision(
            allow_host_carla=True,
            allow_host_display=True,
            allow_pi_pipeline=True,
            allow_jetson_pipeline=True,
            message=None,
            payload={**payload, "reason_code": "gateway_ready"},
            level=EventLevel.INFO,
        )

    def _step_skip_message(
        self,
        step: HilRuntimeStep,
        decision: HilRuntimeStartDecision,
    ) -> str:
        if step.step_id == "host_carla":
            return "树莓派网关未就绪，已跳过 Host CARLA 自动拉起"
        if step.step_id == "pi_pipeline":
            return "树莓派网关未就绪，已跳过 Pi HDMI RTP Pipeline"
        if step.step_id == "jetson_pipeline":
            return "树莓派网关未就绪，已跳过 Jetson Inference Pipeline"
        if decision.message:
            return f"{step.label} 已因降级策略跳过"
        return f"{step.label} 已跳过"

    def stop_pipeline(
        self,
        run_id: str,
        run: Any,
        descriptor: Any,
        started_steps: list[HilRuntimeStep],
    ) -> None:
        if not self.applies_to_run(run):
            return

        env = self._build_command_env(run_id, run, descriptor)
        for step in reversed(started_steps):
            if self._should_preserve_step_on_stop(step, run, descriptor):
                self._emit_event(
                    run_id,
                    "HIL_RUNTIME_STEP_STOP_SKIPPED",
                    f"{step.label} 按当前演示策略保留运行态",
                    payload={"step_id": step.step_id},
                    level=EventLevel.INFO,
                )
                continue
            if not step.stop_command:
                self._emit_event(
                    run_id,
                    "HIL_RUNTIME_STEP_STOP_SKIPPED",
                    f"{step.label} 未配置停止命令，保留运行态",
                    payload={"step_id": step.step_id},
                    level=EventLevel.WARNING,
                )
                continue

            self._emit_event(
                run_id,
                "HIL_RUNTIME_STEP_STOPPING",
                f"正在停止 {step.label}",
                payload={"step_id": step.step_id},
            )
            try:
                self._run_shell_command(
                    run_id,
                    step,
                    step.stop_command,
                    env,
                    phase="stop",
                )
            except RuntimeError as exc:
                self._emit_event(
                    run_id,
                    "HIL_RUNTIME_STEP_STOP_FAILED",
                    f"{step.label} 停止失败，run 将继续结束",
                    payload={"step_id": step.step_id, "error": str(exc)},
                    level=EventLevel.WARNING,
                )
            else:
                self._emit_event(
                    run_id,
                    "HIL_RUNTIME_STEP_STOPPED",
                    f"{step.label} 已停止",
                    payload={"step_id": step.step_id},
                )

    def _resolve_steps(self) -> list[HilRuntimeStep]:
        return [
            HilRuntimeStep(
                step_id="host_carla",
                label="Host CARLA",
                start_command=self._command_or_default(
                    self._settings.hil_host_carla_start_command,
                    self._default_host_carla_start_command(),
                ),
                stop_command=self._command_or_default(
                    self._settings.hil_host_carla_stop_command,
                    self._default_host_carla_stop_command(),
                ),
            ),
            HilRuntimeStep(
                step_id="host_display",
                label="Host Native Follow Display",
                start_command=self._command_or_default(
                    self._settings.hil_host_display_start_command,
                    self._default_host_display_start_command(),
                ),
                stop_command=self._command_or_default(
                    self._settings.hil_host_display_stop_command,
                    self._default_host_display_stop_command(),
                ),
            ),
            HilRuntimeStep(
                step_id="pi_pipeline",
                label="Pi HDMI RTP Pipeline",
                start_command=self._normalize_command(self._settings.hil_pi_start_command),
                stop_command=self._normalize_command(self._settings.hil_pi_stop_command),
            ),
            HilRuntimeStep(
                step_id="jetson_pipeline",
                label="Jetson Inference Pipeline",
                start_command=self._normalize_command(self._settings.hil_jetson_start_command),
                stop_command=self._normalize_command(self._settings.hil_jetson_stop_command),
            ),
        ]

    @staticmethod
    def _normalize_command(command: str | None) -> str | None:
        if command is None:
            return None
        normalized = command.strip()
        return normalized or None

    def _command_or_default(self, configured: str | None, default: str | None) -> str | None:
        normalized = self._normalize_command(configured)
        if normalized is not None:
            return normalized
        return default

    @staticmethod
    def _should_preserve_step_on_stop(step: HilRuntimeStep, run: Any, descriptor: Any) -> bool:
        if step.step_id != "host_carla":
            return False
        success_condition = str(
            getattr(getattr(descriptor, "termination", None), "success_condition", "") or ""
        ).strip().lower()
        if success_condition in {"manual_stop", "manual_stop_only", "user_stop"}:
            return True
        return str(getattr(run, "scenario_name", "") or "").strip() == "town10_autonomous_demo"

    def _default_host_carla_start_command(self) -> str | None:
        if not self._settings.hil_runtime_root.exists():
            return None
        return "bash hil_runtime/host/scripts/start_carla_headed.sh"

    def _default_host_carla_stop_command(self) -> str | None:
        return None

    def _default_host_display_start_command(self) -> str | None:
        if not self._settings.hil_runtime_root.exists():
            return None
        return (
            "CARLA_FRONT_RGB_PREVIEW_BACKGROUND=1 "
            "bash hil_runtime/host/scripts/start_carla_front_rgb_preview.sh "
            "--display-mode native_follow "
            "--map-name \"$DUCKPARK_HIL_MAP_NAME\" "
            "--no-spawn-ego-if-missing "
            "--no-enable-autopilot "
            "--traffic-vehicles 0 "
            "--wait-for-role-seconds 90"
        )

    def _default_host_display_stop_command(self) -> str | None:
        if not self._settings.hil_runtime_root.exists():
            return None
        return (
            "docker exec \"${CARLA_FRONT_RGB_PREVIEW_CONTAINER:-ros2-dev}\" "
            "pkill -f 'python3 hil_runtime/host/scripts/carla_front_rgb_preview.py' "
            ">/dev/null 2>&1 || true"
        )

    def _build_command_env(
        self,
        run_id: str,
        run: Any,
        descriptor: Any,
    ) -> dict[str, str]:
        hil_config = run.hil_config or {}
        env = os.environ.copy()
        env["PROJECT_ROOT"] = str(self._settings.project_root)
        env["DUCKPARK_SRC_ROOT"] = str(self._settings.project_root.parent)
        env["DUCKPARK_PLATFORM_ROOT"] = str(self._settings.project_root)
        env["DUCKPARK_HIL_RUNTIME_ROOT"] = str(self._settings.hil_runtime_root)
        env["DUCKPARK_HIL_RUN_ID"] = run_id
        env["DUCKPARK_HIL_SCENARIO_NAME"] = str(run.scenario_name)
        env["DUCKPARK_HIL_MAP_NAME"] = str(run.map_name)
        env["DUCKPARK_HIL_GATEWAY_ID"] = str(hil_config.get("gateway_id") or "")
        env["DUCKPARK_HIL_MODE"] = str(hil_config.get("mode") or "")
        env["DUCKPARK_HIL_VIDEO_SOURCE"] = str(hil_config.get("video_source") or "")
        env["DUCKPARK_HIL_DUT_INPUT_MODE"] = str(hil_config.get("dut_input_mode") or "")
        env["DUCKPARK_HIL_RESULT_INGEST_MODE"] = str(
            hil_config.get("result_ingest_mode") or ""
        )
        env["DUCKPARK_HIL_TIMEOUT_SECONDS"] = str(descriptor.termination.timeout_seconds)
        env["DUCKPARK_HIL_FIXED_DELTA_SECONDS"] = str(descriptor.sync.fixed_delta_seconds)
        env["DUCKPARK_HIL_WEATHER_PRESET"] = str(descriptor.weather.preset)
        env["DUCKPARK_HIL_PLATFORM_BASE_URL"] = (
            self._settings.hil_platform_base_url
            or f"http://127.0.0.1:{self._settings.api_port}"
        )
        return env

    def _run_shell_command(
        self,
        run_id: str,
        step: HilRuntimeStep,
        command: str,
        env: dict[str, str],
        *,
        phase: str,
    ) -> None:
        self._append_log(
            run_id,
            f"[hil_runtime:{step.step_id}] {phase} command: {command}",
        )
        try:
            completed = subprocess.run(
                ["bash", "-lc", command],
                cwd=str(self._settings.hil_runtime_workdir),
                env=env,
                capture_output=True,
                text=True,
                timeout=self._settings.hil_command_timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            self._append_log(
                run_id,
                (
                    f"[hil_runtime:{step.step_id}] {phase} timeout after "
                    f"{self._settings.hil_command_timeout_seconds:.1f}s"
                ),
            )
            raise RuntimeError(
                f"{step.label} {phase} command timed out after "
                f"{self._settings.hil_command_timeout_seconds:.1f}s"
            ) from exc

        if completed.stdout:
            for line in completed.stdout.splitlines():
                self._append_log(run_id, f"[hil_runtime:{step.step_id}] stdout {line}")
        if completed.stderr:
            for line in completed.stderr.splitlines():
                self._append_log(run_id, f"[hil_runtime:{step.step_id}] stderr {line}")
        if completed.returncode != 0:
            raise RuntimeError(
                f"{step.label} {phase} command failed with exit code {completed.returncode}"
            )

    def _append_log(self, run_id: str, line: str) -> None:
        if self._log_callback is not None:
            self._log_callback(run_id, line)

    def _emit_event(
        self,
        run_id: str,
        event_type: str,
        message: str,
        *,
        payload: dict[str, Any] | None = None,
        level: EventLevel = EventLevel.INFO,
    ) -> None:
        if self._event_callback is None:
            return
        self._event_callback(
            run_id,
            event_type,
            message,
            payload=payload or {"emitted_at_utc": now_utc().isoformat()},
            level=level,
        )
