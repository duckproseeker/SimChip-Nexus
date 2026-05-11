from __future__ import annotations

import logging
from fastapi import APIRouter, HTTPException

from app.api.schemas import ApiResponse, WeatherPayload
from app.api.carla_worker_runner import CarlaWorkerError, run_carla_worker
from app.core.config import get_settings

logger = logging.getLogger(__name__)

router = APIRouter(tags=["全局仿真控制"])


@router.put("/system/carla/weather", response_model=ApiResponse, summary="动态修改全局天气")
def update_carla_weather(payload: WeatherPayload) -> ApiResponse:
    settings = get_settings()
    try:
        worker_payload = run_carla_worker(
            "app.api.carla_weather_worker",
            payload.model_dump(exclude_unset=True),
            timeout_seconds=max(settings.carla_timeout_seconds, 5.0) + 2.0,
        )
    except CarlaWorkerError as exc:
        logger.error("CARLA weather worker failed: %s", exc.detail)
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    message = worker_payload.get("message") or f"Successfully updated global weather to {payload.preset}"
    return ApiResponse(success=True, data={"message": message})
