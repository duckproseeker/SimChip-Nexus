from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.api.main import app


def register_gateway(client: TestClient) -> None:
    response = client.post(
        "/gateways/register",
        json={
            "gateway_id": "rpi5-x1301-01",
            "name": "bench-a",
            "capabilities": {
                "video_input_modes": ["hdmi_x1301", "frame_stream"],
                "dut_output_modes": ["uvc_gadget"],
            },
        },
    )
    assert response.status_code == 200


def test_create_start_stop_capture_and_query_manifest() -> None:
    client = TestClient(app)
    register_gateway(client)

    create_resp = client.post(
        "/captures",
        json={
            "gateway_id": "rpi5-x1301-01",
            "source": "hdmi_x1301",
            "save_format": "jpg",
            "sample_fps": 2,
            "max_frames": 300,
            "save_dir": "/data/captures/cap_001",
            "note": "Town01 smoke capture",
        },
    )
    assert create_resp.status_code == 200
    capture_payload = create_resp.json()["data"]
    capture_id = capture_payload["capture_id"]

    assert capture_payload["status"] == "CREATED"
    assert capture_payload["saved_frames"] == 0
    assert capture_payload["manifest_path"].endswith(f"{capture_id}/manifest.json")

    start_resp = client.post(f"/captures/{capture_id}/start")
    assert start_resp.status_code == 200
    assert start_resp.json()["data"]["status"] == "RUNNING"
    assert start_resp.json()["data"]["started_at_utc"] is not None

    manifest_path = Path(start_resp.json()["data"]["manifest_path"])
    manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest_payload["frames"] = [
        {
            "frame_index": 0,
            "captured_at_utc": "2026-03-07T10:00:12.200000+00:00",
            "relative_path": "frames/frame_000000.jpg",
            "width": 1920,
            "height": 1080,
            "size_bytes": 184332,
        },
        {
            "frame_index": 1,
            "captured_at_utc": "2026-03-07T10:00:12.700000+00:00",
            "relative_path": "frames/frame_000001.jpg",
            "width": 1920,
            "height": 1080,
            "size_bytes": 186100,
        },
    ]
    manifest_payload["saved_frames"] = 2
    manifest_path.write_text(
        json.dumps(manifest_payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    get_resp = client.get(f"/captures/{capture_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["data"]["saved_frames"] == 2

    list_resp = client.get("/captures?gateway_id=rpi5-x1301-01")
    assert list_resp.status_code == 200
    assert list_resp.json()["data"]["captures"][0]["capture_id"] == capture_id

    sync_resp = client.post(
        f"/captures/{capture_id}/sync",
        json={
            "status": "RUNNING",
            "saved_frames": 2,
            "frames": manifest_payload["frames"],
        },
    )
    assert sync_resp.status_code == 200
    assert sync_resp.json()["data"]["saved_frames"] == 2

    frames_resp = client.get(f"/captures/{capture_id}/frames?offset=0&limit=1")
    assert frames_resp.status_code == 200
    assert frames_resp.json()["data"]["total"] == 2
    assert len(frames_resp.json()["data"]["items"]) == 1
    assert frames_resp.json()["data"]["items"][0]["relative_path"] == "frames/frame_000000.jpg"

    manifest_resp = client.get(f"/captures/{capture_id}/manifest")
    assert manifest_resp.status_code == 200
    assert manifest_resp.json()["data"]["saved_frames"] == 2
    assert manifest_resp.json()["data"]["frames"][1]["frame_index"] == 1

    stop_resp = client.post(f"/captures/{capture_id}/stop")
    assert stop_resp.status_code == 200
    assert stop_resp.json()["data"]["status"] == "STOPPED"
    assert stop_resp.json()["data"]["ended_at_utc"] is not None


def test_create_capture_requires_existing_gateway() -> None:
    client = TestClient(app)

    response = client.post(
        "/captures",
        json={
            "gateway_id": "missing-gateway",
            "source": "hdmi_x1301",
            "save_format": "jpg",
            "sample_fps": 2,
            "max_frames": 10,
            "save_dir": "/data/captures/cap_missing",
        },
    )

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "NOT_FOUND"


def test_start_capture_rejects_second_running_capture_on_same_gateway() -> None:
    client = TestClient(app)
    register_gateway(client)

    first = client.post(
        "/captures",
        json={
            "gateway_id": "rpi5-x1301-01",
            "source": "hdmi_x1301",
            "save_format": "jpg",
            "sample_fps": 2,
            "max_frames": 10,
            "save_dir": "/data/captures/cap_a",
        },
    ).json()["data"]["capture_id"]
    second = client.post(
        "/captures",
        json={
            "gateway_id": "rpi5-x1301-01",
            "source": "hdmi_x1301",
            "save_format": "jpg",
            "sample_fps": 2,
            "max_frames": 10,
            "save_dir": "/data/captures/cap_b",
        },
    ).json()["data"]["capture_id"]

    assert client.post(f"/captures/{first}/start").status_code == 200

    response = client.post(f"/captures/{second}/start")
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "CONFLICT"
