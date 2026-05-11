from __future__ import annotations

from app.core.models import (
    BenchmarkDefinitionRecord,
    BenchmarkPlanningMode,
    ProjectRecord,
    ProjectStatus,
)
from app.utils.time_utils import now_utc


def build_default_projects() -> list[ProjectRecord]:
    now = now_utc()
    return [
        ProjectRecord(
            project_id="baseline-validation",
            name="基线验证项目",
            vendor="算法工程 / 测试工程",
            processor="单场景吞吐与精度基线",
            description="用于新模型、新板卡或新版本首次接入后的链路验证，优先确认场景运行、指标回传和基础报告导出是否闭环。",
            benchmark_focus=["感知基线", "链路打通", "版本准入"],
            target_metrics=["FPS", "延迟", "mAP", "功耗", "温度", "场景通过率"],
            input_modes=["单场景验证", "设备绑定", "报告导出"],
            status=ProjectStatus.ACTIVE,
            created_at=now,
            updated_at=now,
        ),
        ProjectRecord(
            project_id="matrix-regression",
            name="矩阵回归项目",
            vendor="测试工程",
            processor="多地图 / 多天气 / 多传感器矩阵",
            description="用于版本回归与多维覆盖验证，重点观察不同地图、天气与传感器组合下的稳定性、吞吐和异常率。",
            benchmark_focus=["矩阵覆盖", "异常回归", "多场景压力"],
            target_metrics=["FPS", "延迟", "Recall", "功耗", "温度", "异常率"],
            input_modes=["批量场景执行", "多地图矩阵", "工程分析"],
            status=ProjectStatus.ACTIVE,
            created_at=now,
            updated_at=now,
        ),
        ProjectRecord(
            project_id="thermal-soak",
            name="热稳压测项目",
            vendor="测试工程 / 运维",
            processor="长时运行与热功耗观测",
            description="用于夜间长跑和设备热稳评估，关注功耗、温度、掉帧和持续运行稳定性，适合台架压测与上线前验收。",
            benchmark_focus=["长时稳定", "功耗趋势", "热稳回归"],
            target_metrics=["FPS", "延迟", "场景通过率", "功耗", "温度", "异常率"],
            input_modes=["长时运行", "设备遥测", "趋势报告"],
            status=ProjectStatus.PILOT,
            created_at=now,
            updated_at=now,
        ),
    ]


def build_default_benchmark_definitions() -> list[BenchmarkDefinitionRecord]:
    now = now_utc()
    return [
        BenchmarkDefinitionRecord(
            benchmark_definition_id="perception-baseline",
            name="感知基线评测",
            description="聚焦单场景吞吐、基础精度和平均延迟，用于新芯片或新模型上线前的首轮验收。",
            focus_metrics=["FPS", "avg_latency_ms", "mAP", "Recall", "场景通过率"],
            cadence="每次版本切换必跑",
            report_shape="运营总览 + 工程分析",
            project_ids=["baseline-validation"],
            default_project_id="baseline-validation",
            default_evaluation_profile_name="yolo_open_loop_v1",
            planning_mode=BenchmarkPlanningMode.SINGLE_SCENARIO,
            queue_note="选择 1 个代表性场景进入队列，适合版本首跑、链路验收和单场景基线对比。",
            created_at=now,
            updated_at=now,
        ),
        BenchmarkDefinitionRecord(
            benchmark_definition_id="stress-matrix",
            name="多场景压力回归",
            description="组合多地图、多天气、多传感器模板，观察吞吐回落、异常率和恢复能力。",
            focus_metrics=["FPS", "frame_drop_rate", "异常率", "场景通过率"],
            cadence="每日回归 / 发布前加严",
            report_shape="矩阵看板 + 失败清单",
            project_ids=["matrix-regression"],
            default_project_id="matrix-regression",
            default_evaluation_profile_name="yolo_open_loop_v1",
            planning_mode=BenchmarkPlanningMode.ALL_RUNNABLE,
            queue_note="自动把当前所有可执行场景各跑一遍，用于多场景压力回归和回归覆盖。",
            created_at=now,
            updated_at=now,
        ),
        BenchmarkDefinitionRecord(
            benchmark_definition_id="power-thermal",
            name="功耗热稳评测",
            description="长期运行下跟踪功耗、温度和稳定性指标，服务于台架持续压测与机柜部署验证。",
            focus_metrics=["功耗", "温度", "FPS", "异常率", "稳定性"],
            cadence="夜间长跑",
            report_shape="趋势报告 + 风险摘要",
            project_ids=["thermal-soak"],
            default_project_id="thermal-soak",
            default_evaluation_profile_name="yolo_open_loop_v1",
            planning_mode=BenchmarkPlanningMode.TIMED_SINGLE_SCENARIO,
            candidate_scenario_ids=[
                "town10_autonomous_demo",
                "free_drive_sensor_collection",
            ],
            supports_duration_seconds=True,
            default_duration_seconds=1800,
            queue_note="选择高负载场景并指定运行时长，适合持续压测功耗、温度和掉帧趋势。",
            created_at=now,
            updated_at=now,
        ),
        BenchmarkDefinitionRecord(
            benchmark_definition_id="custom-suite",
            name="自定义测试项目",
            description="由测试工程手动加入要入队的场景组合，适合问题复现、专项回归和临时验证。",
            focus_metrics=["场景通过率", "异常率", "FPS", "功耗", "温度"],
            cadence="按需",
            report_shape="任务清单 + 结果汇总",
            project_ids=["matrix-regression"],
            default_project_id="matrix-regression",
            default_evaluation_profile_name="yolo_open_loop_v1",
            planning_mode=BenchmarkPlanningMode.CUSTOM_MULTI_SCENARIO,
            queue_note="手动选择一个或多个场景进入队列，按当前顺序批量创建 run。",
            created_at=now,
            updated_at=now,
        ),
    ]
