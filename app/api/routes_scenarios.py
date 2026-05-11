from __future__ import annotations

import hashlib
import shutil

from fastapi import APIRouter, HTTPException

from app.api.carla_worker_runner import CarlaWorkerError, run_carla_worker
from app.api.routes_runs import get_run_manager, raise_http_error, run_to_payload
from app.api.schemas import (
    ApiResponse,
    RunResponse,
    ScenarioLaunchRequest,
    SensorProfileListPayload,
    SensorProfileListResponse,
    SensorProfileResponse,
    SensorProfileSaveRequest,
)
from app.core.config import get_settings
from app.core.errors import AppError
from app.scenario.environment_presets import list_environment_presets
from app.scenario.launch_builder import (
    build_generated_scenario_source,
    build_launch_descriptor,
    write_launch_artifacts,
)
from app.scenario.library import get_scenario_catalog_item, list_scenario_catalog
from app.scenario.maps import fallback_runtime_map_options
from app.scenario.sensor_profiles import (
    build_sensor_config_from_profile,
    get_sensor_profile,
    load_sensor_profiles,
    save_sensor_profile,
)
from app.scenario.template_registry import normalize_template_params

router = APIRouter(tags=["场景管理"])


def _derive_traffic_seed(run_id: str) -> int:
    return int(hashlib.sha1(run_id.encode("utf-8")).hexdigest()[:8], 16) % 2147483647


def _explicit_traffic_payload(request: ScenarioLaunchRequest) -> dict[str, int] | None:
    if "traffic" not in request.model_fields_set:
        return None
    traffic_fields = set(getattr(request.traffic, "model_fields_set", set()))
    if not traffic_fields:
        return None
    return request.traffic.model_dump(
        mode="json",
        exclude_none=True,
        include=traffic_fields,
    )


def _default_hil_config_for_launch(catalog_item: dict[str, object]) -> dict[str, str] | None:
    if not str(catalog_item.get("scenario_id") or "").strip():
        return None
    return {
        "mode": "camera_open_loop",
        "video_source": "hdmi_x1301",
        "dut_input_mode": "uvc_camera",
        "result_ingest_mode": "http_push",
    }


def fetch_available_maps() -> list[dict[str, str]]:
    settings = get_settings()
    try:
        worker_payload = run_carla_worker(
            "app.api.carla_maps_worker",
            {},
            timeout_seconds=max(settings.carla_timeout_seconds, 5.0) + 2.0,
        )
        maps = worker_payload.get("maps")
        if isinstance(maps, list):
            return maps
    except CarlaWorkerError as exc:
        fallback_items = fallback_runtime_map_options()
        if fallback_items:
            return fallback_items
        raise HTTPException(
            status_code=503,
            detail={
                "code": "CARLA_MAPS_UNAVAILABLE",
                "message": exc.detail,
            },
        ) from exc
    return fallback_runtime_map_options()


def _sensor_profile_list_payload(settings_root) -> SensorProfileListPayload:
    return SensorProfileListPayload(items=load_sensor_profiles(settings_root))


@router.get(
    "/scenarios",
    response_model=ApiResponse,
    summary="查询场景目录",
    description="返回由平台 native runtime 驱动的场景目录、环境预设和传感器模板。sample_descriptors 仅保留兼容字段，正常情况下为空。",
)
def list_scenarios() -> ApiResponse:
    project_root = get_settings().project_root
    sample_files = sorted((project_root / "configs" / "scenarios").glob("sample_*.yaml"))
    return ApiResponse(
        success=True,
        data={
            "catalog": list_scenario_catalog(),
            "environment_presets": list_environment_presets(),
            "sensor_profiles": load_sensor_profiles(get_settings().sensor_profiles_root),
            "sample_descriptors": [str(path) for path in sample_files],
        },
    )


@router.get(
    "/scenarios/catalog",
    response_model=ApiResponse,
    summary="查询场景库目录",
    description="返回由平台 native runtime 驱动的场景目录。",
)
def list_scenario_catalog_endpoint() -> ApiResponse:
    return ApiResponse(success=True, data={"items": list_scenario_catalog()})


@router.get(
    "/scenarios/environment-presets",
    response_model=ApiResponse,
    summary="查询环境参数预设",
    description="返回用于运行前配置和运行中环境调参的预设。",
)
def get_environment_presets() -> ApiResponse:
    return ApiResponse(success=True, data={"items": list_environment_presets()})


@router.get(
    "/scenarios/sensor-profiles",
    response_model=SensorProfileListResponse,
    summary="查询传感器配置模板",
    description="返回 YAML 传感器模板，格式参考 CARLA official agent sensors() 配置。",
)
def get_sensor_profiles() -> SensorProfileListResponse:
    settings = get_settings()
    return SensorProfileListResponse(
        success=True,
        data=_sensor_profile_list_payload(settings.sensor_profiles_root),
    )


@router.put(
    "/scenarios/sensor-profiles/{profile_name}",
    response_model=SensorProfileResponse,
    summary="创建或更新传感器配置模板",
    description="用于运维界面维护与车型绑定的 YAML 传感器模板。场景运行仍只引用 profile_name。",
)
def save_sensor_profile_endpoint(
    profile_name: str, request: SensorProfileSaveRequest
) -> SensorProfileResponse:
    normalized_path_name = profile_name.strip()
    if not normalized_path_name:
        raise HTTPException(
            status_code=422,
            detail={"code": "VALIDATION_ERROR", "message": "profile_name must not be empty"},
        )
    if normalized_path_name != request.profile_name:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "VALIDATION_ERROR",
                "message": "path profile_name 必须与请求体 profile_name 一致",
            },
        )

    settings = get_settings()
    try:
        profile = save_sensor_profile(
            settings.sensor_profiles_root,
            profile_name=request.profile_name,
            display_name=request.display_name,
            description=request.description,
            sensors=[
                sensor.model_dump(mode="json", exclude_none=True) for sensor in request.sensors
            ],
            metadata=request.metadata,
            vehicle_model=request.vehicle_model,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": "VALIDATION_ERROR", "message": str(exc)},
        ) from exc

    return SensorProfileResponse(success=True, data=profile)


@router.get(
    "/maps",
    response_model=ApiResponse,
    summary="查询 CARLA 可用地图",
    description="直接从当前配置的 CARLA server 读取可加载地图列表，用于前端下拉选择。",
)
def list_maps() -> ApiResponse:
    return ApiResponse(success=True, data={"maps": fetch_available_maps()})


@router.post(
    "/scenarios/launch",
    response_model=RunResponse,
    summary="按场景启动配置创建运行",
    description="前端只提交场景、地图、天气、传感器和背景交通参数。后端生成 per-run 的 native runtime 输入并创建 run，可按需自动加入执行队列。",
)
def launch_scenario(request: ScenarioLaunchRequest) -> RunResponse:
    manager = get_run_manager()
    catalog_item = get_scenario_catalog_item(request.scenario_id)
    if catalog_item is None:
        available_ids = sorted(item["scenario_id"] for item in list_scenario_catalog())
        raise HTTPException(
            status_code=422,
            detail={
                "code": "VALIDATION_ERROR",
                "message": (f"未知场景: '{request.scenario_id}'。" f"可用场景: {available_ids}"),
            },
        )

    settings = get_settings()
    run_id = manager.build_run_id()
    launch_request = request.model_dump(mode="json", exclude_none=True)
    explicit_traffic = _explicit_traffic_payload(request)
    if explicit_traffic is None:
        launch_request.pop("traffic", None)
    else:
        launch_request["traffic"] = explicit_traffic
    launch_capabilities = catalog_item.get("launch_capabilities", {})
    resolved_map_name = (
        request.map_name
        if launch_capabilities.get("map_editable", False)
        else str(catalog_item.get("default_map_name") or "").strip() or None
    )
    try:
        resolved_template_params = normalize_template_params(
            catalog_item.get("parameter_schema", []),
            request.template_params,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": "VALIDATION_ERROR", "message": str(exc)},
        ) from exc

    requested_sensor_profile_name = (
        request.sensor_profile_name
        if launch_capabilities.get("sensor_profile_editable", False)
        else None
    )
    template_sensor_profile_name = (
        str(
            catalog_item.get("descriptor_template", {}).get("sensors", {}).get("profile_name") or ""
        ).strip()
        or None
    )
    resolved_sensor_profile_name = requested_sensor_profile_name or template_sensor_profile_name
    resolved_sensors = None
    if resolved_sensor_profile_name is not None:
        if get_sensor_profile(settings.sensor_profiles_root, resolved_sensor_profile_name) is None:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "VALIDATION_ERROR",
                    "message": f"未知传感器模板: '{resolved_sensor_profile_name}'",
                },
            )
        resolved_sensors = build_sensor_config_from_profile(
            settings.sensor_profiles_root,
            resolved_sensor_profile_name,
        )

    descriptor = build_launch_descriptor(
        catalog_item,
        map_name=resolved_map_name,
        weather=(
            request.weather.model_dump(mode="json", exclude_none=True)
            if request.weather is not None
            else None
        ),
        traffic=explicit_traffic,
        sensors=resolved_sensors,
        timeout_seconds=request.timeout_seconds,
        metadata=(
            request.metadata.model_dump(mode="json", exclude_none=True)
            if request.metadata is not None
            else None
        ),
    )
    descriptor_traffic = descriptor.get("traffic", {})
    if (
        isinstance(descriptor_traffic, dict)
        and bool(descriptor_traffic.get("enabled"))
        and descriptor_traffic.get("seed") is None
    ):
        derived_seed = _derive_traffic_seed(run_id)
        descriptor_traffic["seed"] = derived_seed
        descriptor["traffic"] = descriptor_traffic
        launch_request.setdefault("traffic", {})
        launch_request["traffic"]["seed"] = derived_seed

    artifacts = None
    run_created = False
    try:
        resolved_hil_config = _default_hil_config_for_launch(catalog_item)
        artifacts = write_launch_artifacts(
            settings=settings,
            run_id=run_id,
            catalog_item=catalog_item,
            descriptor=descriptor,
            launch_request=launch_request,
            template_params=resolved_template_params,
        )
        generated_source = build_generated_scenario_source(
            catalog_item,
            artifacts,
            resolved_template_params,
        )
        run = manager.create_run(
            descriptor_payload=descriptor,
            run_id=run_id,
            hil_config=resolved_hil_config,
            execution_backend=str(catalog_item.get("execution_backend") or "native"),
            scenario_source=generated_source,
            config_snapshot_extra={
                "launch_request": launch_request,
                "resolved_template_params": resolved_template_params,
                "scenario_template": {
                    "scenario_id": catalog_item["scenario_id"],
                    "display_name": catalog_item["display_name"],
                },
            },
        )
        run_created = True
        if request.auto_start:
            run = manager.start_run(run.run_id)
    except AppError as exc:
        if artifacts is not None and not run_created:
            shutil.rmtree(artifacts.build_dir, ignore_errors=True)
        raise_http_error(exc)
    except RuntimeError as exc:
        if artifacts is not None and not run_created:
            shutil.rmtree(artifacts.build_dir, ignore_errors=True)
        raise HTTPException(
            status_code=422,
            detail={"code": "SCENARIO_LAUNCH_BUILD_FAILED", "message": str(exc)},
        ) from exc

    return RunResponse(success=True, data=run_to_payload(run))
