from __future__ import annotations

from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.api import routes_scenarios
from app.api.main import app


def test_list_maps_success(monkeypatch) -> None:
    monkeypatch.setattr(
        routes_scenarios,
        "fetch_available_maps",
        lambda: [
            {"map_name": "/Game/Carla/Maps/Town01", "display_name": "Town01"},
            {"map_name": "/Game/Carla/Maps/Town02", "display_name": "Town02"},
        ],
    )

    client = TestClient(app)
    response = client.get("/maps")

    assert response.status_code == 200
    assert response.json()["success"] is True
    assert response.json()["data"]["maps"][0]["display_name"] == "Town01"


def test_list_maps_failure(monkeypatch) -> None:
    def raise_error() -> list[dict[str, str]]:
        raise HTTPException(
            status_code=503,
            detail={"code": "CARLA_MAPS_UNAVAILABLE", "message": "地图服务不可用"},
        )

    monkeypatch.setattr(routes_scenarios, "fetch_available_maps", raise_error)

    client = TestClient(app)
    response = client.get("/maps")

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "CARLA_MAPS_UNAVAILABLE"
