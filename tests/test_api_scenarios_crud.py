from __future__ import annotations

from fastapi.testclient import TestClient

from app.api.main import app


def test_create_scenario():
    client = TestClient(app)
    resp = client.post("/scenario-assets", json={
        "name": "雨天测试",
        "recorder_log_path": "/data/rain.log",
        "map_name": "Town03",
        "duration_seconds": 60.0,
        "tags": ["雨天"],
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "雨天测试"
    assert data["id"].startswith("scene_")
    assert data["map_name"] == "Town03"
    assert data["duration_seconds"] == 60.0
    assert data["tags"] == ["雨天"]


def test_list_scenarios():
    client = TestClient(app)
    client.post("/scenario-assets", json={
        "name": "a", "recorder_log_path": "/a.log", "tags": ["雨天"]
    })
    client.post("/scenario-assets", json={
        "name": "b", "recorder_log_path": "/b.log", "tags": ["晴天"]
    })
    resp = client.get("/scenario-assets")
    assert resp.status_code == 200
    assert len(resp.json()) == 2

    resp = client.get("/scenario-assets?tag=雨天")
    assert len(resp.json()) == 1
    assert resp.json()[0]["name"] == "a"


def test_list_scenarios_filter_by_map():
    client = TestClient(app)
    client.post("/scenario-assets", json={
        "name": "a", "recorder_log_path": "/a.log", "map_name": "Town03"
    })
    client.post("/scenario-assets", json={
        "name": "b", "recorder_log_path": "/b.log", "map_name": "Town04"
    })
    resp = client.get("/scenario-assets?map_name=Town03")
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["map_name"] == "Town03"


def test_get_scenario():
    client = TestClient(app)
    create_resp = client.post("/scenario-assets", json={
        "name": "test", "recorder_log_path": "/t.log"
    })
    sid = create_resp.json()["id"]
    resp = client.get(f"/scenario-assets/{sid}")
    assert resp.status_code == 200
    assert resp.json()["id"] == sid
    assert resp.json()["name"] == "test"


def test_get_scenario_not_found():
    client = TestClient(app)
    resp = client.get("/scenario-assets/scene_nonexistent")
    assert resp.status_code == 404


def test_update_scenario():
    client = TestClient(app)
    create_resp = client.post("/scenario-assets", json={
        "name": "original", "recorder_log_path": "/o.log", "tags": ["旧标签"]
    })
    sid = create_resp.json()["id"]
    resp = client.patch(f"/scenario-assets/{sid}", json={
        "name": "updated", "tags": ["新标签"]
    })
    assert resp.status_code == 200
    assert resp.json()["name"] == "updated"
    assert resp.json()["tags"] == ["新标签"]


def test_update_scenario_not_found():
    client = TestClient(app)
    resp = client.patch("/scenario-assets/scene_nonexistent", json={
        "name": "x"
    })
    assert resp.status_code == 404


def test_delete_scenario():
    client = TestClient(app)
    create_resp = client.post("/scenario-assets", json={
        "name": "del", "recorder_log_path": "/d.log"
    })
    sid = create_resp.json()["id"]
    resp = client.delete(f"/scenario-assets/{sid}")
    assert resp.status_code == 204
    resp = client.get(f"/scenario-assets/{sid}")
    assert resp.status_code == 404


def test_delete_scenario_not_found():
    client = TestClient(app)
    resp = client.delete("/scenario-assets/scene_nonexistent")
    assert resp.status_code == 404
