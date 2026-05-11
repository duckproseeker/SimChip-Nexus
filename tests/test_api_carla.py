from __future__ import annotations

from fastapi.testclient import TestClient

from app.api import routes_carla
from app.api.carla_worker_runner import CarlaWorkerError
from app.api.main import app


def test_update_carla_weather_returns_worker_success(monkeypatch) -> None:
    monkeypatch.setattr(
        routes_carla,
        "run_carla_worker",
        lambda *args, **kwargs: {
            "ok": True,
            "message": "Successfully updated global weather to ClearSunset",
        },
    )

    client = TestClient(app)
    response = client.put("/system/carla/weather", json={"preset": "ClearSunset"})

    assert response.status_code == 200
    assert response.json()["data"]["message"] == "Successfully updated global weather to ClearSunset"


def test_update_carla_weather_survives_worker_failure(monkeypatch) -> None:
    def raise_worker_error(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise CarlaWorkerError(
            status_code=503,
            detail="CARLA connection or operation failed: time-out",
        )

    monkeypatch.setattr(routes_carla, "run_carla_worker", raise_worker_error)

    client = TestClient(app)
    response = client.put("/system/carla/weather", json={"preset": "HardRainSunset"})

    assert response.status_code == 503
    assert response.json()["detail"] == "CARLA connection or operation failed: time-out"
