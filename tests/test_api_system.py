from __future__ import annotations

from fastapi.testclient import TestClient

from app.api.main import app
from app.api import routes_system
from app.core.config import get_settings
from app.orchestrator.queue import FileCommandQueue
from app.storage.executor_store import ExecutorStore


def test_system_status_reports_offline_executor_with_pending_queue() -> None:
    client = TestClient(app)

    run_response = client.post(
        "/runs",
        json={
            "descriptor": {
                "version": 1,
                "scenario_name": "osc_follow_leading_vehicle",
                "map_name": "Town01",
                "weather": {"preset": "ClearNoon"},
                "sync": {"enabled": True, "fixed_delta_seconds": 0.05},
                "ego_vehicle": {
                    "blueprint": "vehicle.tesla.model3",
                    "spawn_point": {
                        "x": 230.0,
                        "y": 195.0,
                        "z": 0.5,
                        "roll": 0.0,
                        "pitch": 0.0,
                        "yaw": 90.0,
                    },
                },
                "traffic": {"enabled": False, "num_vehicles": 0, "num_walkers": 0},
                "sensors": {"enabled": False},
                "termination": {"timeout_seconds": 20, "success_condition": "timeout"},
                "recorder": {"enabled": False},
                "metadata": {"author": "test", "tags": [], "description": "demo"},
            }
        },
    )
    run_id = run_response.json()["data"]["run_id"]
    client.post(f"/runs/{run_id}/start")

    response = client.get("/system/status")
    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["executor"]["alive"] is False
    assert payload["executor"]["pending_commands"] == 1
    assert payload["counts"]["runs"]["QUEUED"] == 1


def test_system_status_reports_live_executor_heartbeat() -> None:
    settings = get_settings()
    queue = FileCommandQueue(settings.commands_root)
    ExecutorStore(settings.executor_root).write_heartbeat(
        {
            "status": "READY",
            "active_run_id": None,
            "last_command_run_id": "run_demo",
            "updated_at_utc": "2026-03-07T00:00:00+00:00",
            "pending_commands": queue.count_pending(),
        }
    )

    client = TestClient(app)
    response = client.get("/system/status")
    assert response.status_code == 200
    assert "executor" in response.json()["data"]


def test_system_status_includes_pi_gateway_status(monkeypatch) -> None:
    monkeypatch.setattr(
        routes_system,
        "probe_pi_gateway",
        lambda settings: {
            "status": "OFFLINE",
            "configured": True,
            "reachable": False,
            "host": "192.168.110.236",
            "user": "kavin",
            "port": 22,
            "start_command_configured": True,
            "stop_command_configured": True,
            "last_probe_at_utc": "2026-03-23T00:00:00+00:00",
            "warning": "No route to host",
        },
    )

    client = TestClient(app)
    response = client.get("/system/status")

    assert response.status_code == 200
    payload = response.json()["data"]["pi_gateway"]
    assert payload["status"] == "OFFLINE"
    assert payload["reachable"] is False


def test_pi_gateway_start_route_returns_command_result(monkeypatch) -> None:
    monkeypatch.setattr(
        routes_system,
        "run_pi_gateway_command",
        lambda settings, action: {
            "action": action,
            "success": True,
            "exit_code": 0,
            "output": "pi_rtp_started",
            "status": {
                "status": "READY",
                "configured": True,
                "reachable": True,
                "host": "192.168.110.236",
                "user": "kavin",
                "port": 22,
                "start_command_configured": True,
                "stop_command_configured": True,
                "last_probe_at_utc": "2026-03-23T00:00:00+00:00",
                "warning": None,
            },
        },
    )

    client = TestClient(app)
    response = client.post("/system/pi-gateway/start")

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["action"] == "start"
    assert payload["success"] is True
