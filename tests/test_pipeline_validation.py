from app.api.routes_pipelines import validate_pipeline_graph


def _node(node_id: str, node_type: str) -> dict:
    return {"node_id": node_id, "type": node_type, "position": {"x": 0, "y": 0}, "data": {}}


def _edge(source: str, source_handle: str, target: str, target_handle: str) -> dict:
    return {"edge_id": f"{source}-{target}", "source": source, "source_handle": source_handle,
            "target": target, "target_handle": target_handle}


def test_valid_minimal_graph():
    nodes = [_node("s1", "scene_replay")]
    edges = []
    errors = validate_pipeline_graph(nodes, edges)
    assert errors == []


def test_valid_full_chain():
    nodes = [
        _node("s1", "scene_replay"),
        _node("cam1", "camera"),
        _node("rtp1", "rtp_output"),
        _node("dut1", "dut"),
    ]
    edges = [
        _edge("s1", "scene", "cam1", "scene"),
        _edge("cam1", "sensor_data", "rtp1", "sensor_data"),
        _edge("rtp1", "stream", "dut1", "stream"),
    ]
    errors = validate_pipeline_graph(nodes, edges)
    assert errors == []


def test_missing_scene_node():
    nodes = [_node("cam1", "camera")]
    edges = []
    errors = validate_pipeline_graph(nodes, edges)
    assert any("scene_replay" in e for e in errors)


def test_type_mismatch_rejected():
    nodes = [
        _node("s1", "scene_replay"),
        _node("rtp1", "rtp_output"),
    ]
    edges = [_edge("s1", "scene", "rtp1", "sensor_data")]
    errors = validate_pipeline_graph(nodes, edges)
    assert any("mismatch" in e.lower() or "不匹配" in e for e in errors)


def test_cycle_detected():
    nodes = [
        _node("s1", "scene_replay"),
        _node("env1", "env_override"),
    ]
    edges = [
        _edge("s1", "scene", "env1", "scene"),
        _edge("env1", "scene", "s1", "scene"),
    ]
    errors = validate_pipeline_graph(nodes, edges)
    assert any("cycle" in e.lower() or "环路" in e for e in errors)
