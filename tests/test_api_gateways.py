from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

from app.api import routes_gateways
from app.core.config import get_settings
from app.core.models import GatewayRecord, GatewayStatus
from fastapi.testclient import TestClient

from app.api.main import app
from app.storage.artifact_store import ArtifactStore
from app.storage.run_store import RunStore


VALID_DESCRIPTOR = {
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
    "termination": {"timeout_seconds": 10, "success_condition": "timeout"},
    "recorder": {"enabled": False},
    "metadata": {"author": "test", "tags": ["api"], "description": "api test"},
}


def test_register_list_and_heartbeat_gateway() -> None:
    client = TestClient(app)

    register_resp = client.post(
        "/gateways/register",
        json={
            "gateway_id": "rpi5-x1301-01",
            "name": "bench-a",
            "capabilities": {
                "video_input_modes": ["hdmi_x1301", "frame_stream"],
                "dut_output_modes": ["uvc_gadget"],
            },
            "agent_version": "0.1.0",
            "address": "192.168.110.236",
        },
    )
    assert register_resp.status_code == 200
    assert register_resp.json()["data"]["gateway_id"] == "rpi5-x1301-01"

    heartbeat_resp = client.post(
        "/gateways/rpi5-x1301-01/heartbeat",
        json={
            "status": "READY",
            "metrics": {"input_fps": 30.0, "output_fps": 29.7, "frame_drop_rate": 0.01},
        },
    )
    assert heartbeat_resp.status_code == 200
    assert heartbeat_resp.json()["data"]["status"] == "READY"

    list_resp = client.get("/gateways")
    assert list_resp.status_code == 200
    assert list_resp.json()["data"]["gateways"][0]["gateway_id"] == "rpi5-x1301-01"


def test_list_evaluation_profiles() -> None:
    client = TestClient(app)

    response = client.get("/evaluation-profiles")
    assert response.status_code == 200
    assert response.json()["data"]["profiles"][0]["profile_name"] == "yolo_open_loop_v1"


def test_gateway_heartbeat_persists_run_scoped_device_metrics() -> None:
    client = TestClient(app)

    register_resp = client.post(
        "/gateways/register",
        json={
            "gateway_id": "rpi5-x1301-01",
            "name": "bench-a",
            "capabilities": {"video_input_modes": ["hdmi_x1301"]},
        },
    )
    assert register_resp.status_code == 200

    create_resp = client.post("/runs", json={"descriptor": VALID_DESCRIPTOR})
    assert create_resp.status_code == 200
    run_id = create_resp.json()["data"]["run_id"]

    heartbeat_resp = client.post(
        f"/gateways/rpi5-x1301-01/heartbeat",
        json={
            "status": "READY",
            "metrics": {
                "output_fps": 13.2,
                "avg_latency_ms": 54.8,
                "processed_frames": 120,
            },
            "current_run_id": run_id,
        },
    )
    assert heartbeat_resp.status_code == 200

    settings = get_settings()
    snapshot = ArtifactStore(settings.artifacts_root).read_device_metrics(run_id)
    assert snapshot is not None
    assert snapshot["gateway_id"] == "rpi5-x1301-01"
    assert snapshot["gateway_status"] == "READY"
    assert snapshot["output_fps"] == 13.2
    assert snapshot["processed_frames"] == 120
    assert snapshot["gateway_last_heartbeat_at_utc"] is not None

    stored_run = RunStore(settings.runs_root).get(run_id)
    assert stored_run.run_id == run_id


def test_register_gateway_recovers_from_malformed_existing_file() -> None:
    settings = get_settings()
    malformed_path = Path(settings.gateways_root) / "rpi5-x1301-01.json"
    malformed_path.parent.mkdir(parents=True, exist_ok=True)
    malformed_path.write_text(
        '{"gateway_id":"rpi5-x1301-01","name":"broken"}\n{"extra":"data"}\n',
        encoding="utf-8",
    )

    client = TestClient(app)
    response = client.post(
        "/gateways/register",
        json={
            "gateway_id": "rpi5-x1301-01",
            "name": "bench-a",
            "capabilities": {"video_input_modes": ["hdmi_x1301"]},
        },
    )

    assert response.status_code == 200
    payload = json.loads(malformed_path.read_text(encoding="utf-8"))
    assert payload["gateway_id"] == "rpi5-x1301-01"
    assert payload["name"] == "bench-a"


def test_gateway_payload_marks_stale_but_reachable_pi_as_degraded(monkeypatch) -> None:
    settings = replace(
        get_settings(),
        duckpark_pi_host="192.168.110.236",
        duckpark_pi_user="kavin",
        hil_gateway_stale_seconds=15.0,
    )
    monkeypatch.setattr(routes_gateways, "get_settings", lambda: settings)
    monkeypatch.setattr(
        "app.hil.gateway_runtime_status.probe_pi_gateway",
        lambda current_settings: {
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
    )

    gateway = GatewayRecord(
        gateway_id="rpi5-x1301-01",
        name="bench-a",
        status=GatewayStatus.READY,
        capabilities={},
        metrics={},
        agent_version="0.1.0",
        address="192.168.110.236",
        current_run_id=None,
        last_heartbeat_at=datetime.now(timezone.utc) - timedelta(minutes=10),
        last_seen_at=datetime.now(timezone.utc),
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    payload = routes_gateways.gateway_to_payload(gateway)

    assert payload["status"] == "DEGRADED"
    assert payload["status_detail"] == "Pi chain reachable but gateway heartbeat is stale"
