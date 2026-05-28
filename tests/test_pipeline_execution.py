import time

from starlette.testclient import TestClient

from app.api.main import app

client = TestClient(app)


def _create_pipeline_with_nodes(name: str, nodes: list[dict], edges: list[dict] | None = None) -> str:
    """Helper: create a pipeline then update it with nodes/edges."""
    create_resp = client.post("/pipelines", json={"name": name})
    assert create_resp.status_code == 200
    pid = create_resp.json()["data"]["pipeline_id"]

    update_resp = client.put(f"/pipelines/{pid}", json={
        "nodes": nodes,
        "edges": edges or [],
    })
    assert update_resp.status_code == 200
    return pid


def test_execute_minimal_pipeline():
    """A valid scene_replay-only pipeline should execute successfully."""
    nodes = [
        {"node_id": "s1", "type": "scene_replay", "position": {"x": 0, "y": 0}, "data": {"scenario_id": "scene_abc"}},
    ]
    pid = _create_pipeline_with_nodes("test-exec", nodes)

    exec_resp = client.post(f"/pipelines/{pid}/execute")
    assert exec_resp.status_code == 200
    data = exec_resp.json()["data"]
    assert "execution_id" in data


def test_execute_invalid_pipeline_rejected():
    """A pipeline with only a camera node (no scene_replay) should be rejected with 422."""
    nodes = [
        {"node_id": "cam1", "type": "camera", "position": {"x": 0, "y": 0}, "data": {}},
    ]
    pid = _create_pipeline_with_nodes("invalid", nodes)

    exec_resp = client.post(f"/pipelines/{pid}/execute")
    assert exec_resp.status_code == 422
    assert "validation_errors" in exec_resp.json()["detail"]


def test_get_execution_status():
    """After executing a valid pipeline, the execution record should be retrievable."""
    nodes = [
        {"node_id": "s1", "type": "scene_replay", "position": {"x": 0, "y": 0}, "data": {}},
    ]
    pid = _create_pipeline_with_nodes("status-test", nodes)

    exec_resp = client.post(f"/pipelines/{pid}/execute")
    assert exec_resp.status_code == 200
    eid = exec_resp.json()["data"]["execution_id"]

    # Allow background thread to finish its initial save
    time.sleep(0.1)

    status_resp = client.get(f"/pipeline-executions/{eid}")
    assert status_resp.status_code == 200
    assert status_resp.json()["data"]["execution_id"] == eid
