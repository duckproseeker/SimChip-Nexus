from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.api.main import app
from app.api.routes_scenario_sources import get_scenario_source_store
from app.core.config import get_settings
from app.core.models import ScenarioSourceRecord
from app.scenario.source_discovery import (
    SCENARIO_RUNNER_ROUTES_PROVIDER,
    discover_route_xml_sources,
    discover_scenario_runner_route_sources,
)
from app.storage.artifact_store import ArtifactStore
from app.utils.time_utils import now_utc


def _write_sensor_profile() -> None:
    root = get_settings().sensor_profiles_root
    root.mkdir(parents=True, exist_ok=True)
    (root / "front_rgb.yaml").write_text(
        """
profile_name: front_rgb
display_name: Front RGB
description: test profile
sensors:
  - id: front_rgb
    type: sensor.camera.rgb
    x: 1.5
    y: 0.0
    z: 1.4
    width: 800
    height: 600
    fov: 90
metadata:
  vehicle_model: test
""",
        encoding="utf-8",
    )


def _source_record() -> ScenarioSourceRecord:
    now = now_utc()
    return ScenarioSourceRecord(
        source_id="src_test_route",
        provider="bench2drive",
        provider_version={
            "git_commit": "abc123",
            "git_remote": "https://example.test/bench2drive.git",
            "expected_carla_version": "0.9.16",
            "expected_leaderboard_version": "2.0",
            "route_file_hash": "routehash",
        },
        source_path="/tmp/routes.xml",
        source_hash="routehash",
        route_id="route_001",
        scenario_type="CutIn",
        map_name="Town03",
        weather={"preset": "ClearNoon"},
        recommended_duration_seconds=20.0,
        corner_case_labels=["CutIn"],
        compatibility_status="ok",
        parsed_metadata={
            "route_xml_path": "/tmp/routes.xml",
            "route_xml_hash": "routehash",
            "route_id": "route_001",
            "waypoints": [
                {"x": 1.0, "y": 2.0, "z": 0.5, "roll": 0.0, "pitch": 0.0, "yaw": 10.0},
                {"x": 15.0, "y": 2.0, "z": 0.5, "roll": 0.0, "pitch": 0.0, "yaw": 10.0},
            ],
            "scenario_types": ["CutIn"],
            "route_length_m": 14.0,
            "launch_mode": "leaderboard_route",
        },
        discovered_at=now,
        updated_at=now,
    )


def test_route_xml_discovery_creates_one_source_per_route(tmp_path: Path) -> None:
    root = tmp_path / "bench2drive"
    routes = root / "leaderboard" / "data" / "routes.xml"
    routes.parent.mkdir(parents=True)
    routes.write_text(
        """
<routes>
  <route id="0" town="Town03">
    <weather preset="WetNoon" cloudiness="30" />
    <waypoints>
      <position x="0" y="0" z="0.5" yaw="0" />
      <position x="30" y="0" z="0.5" yaw="0" />
    </waypoints>
    <scenarios>
      <scenario type="CutIn" />
    </scenarios>
  </route>
  <route id="1" town="Town05">
    <waypoints>
      <position x="1" y="2" z="0.5" yaw="90" />
    </waypoints>
  </route>
</routes>
""",
        encoding="utf-8",
    )

    sources = discover_route_xml_sources(provider="bench2drive", root=root)

    assert len(sources) == 2
    assert {item.route_id for item in sources} == {"0", "1"}
    first = next(item for item in sources if item.route_id == "0")
    assert first.map_name == "Town03"
    assert first.weather["preset"] == "WetNoon"
    assert "CutIn" in first.corner_case_labels
    assert first.compatibility_status == "ok"


def test_scenario_runner_route_discovery_scans_srunner_data_only(
    tmp_path: Path, monkeypatch
) -> None:
    scenario_runner_root = tmp_path / "scenario_runner"
    data_routes = scenario_runner_root / "srunner" / "data" / "routes_town10.xml"
    example_route = scenario_runner_root / "srunner" / "examples" / "RouteObstacles.xml"
    data_routes.parent.mkdir(parents=True)
    example_route.parent.mkdir(parents=True)
    data_routes.write_text(
        """
<routes>
  <route id="town10_route" town="Town10HD_Opt">
    <waypoints>
      <position x="0" y="0" z="0.5" yaw="0" />
      <position x="20" y="0" z="0.5" yaw="0" />
    </waypoints>
    <scenarios>
      <scenario type="DynamicObjectCrossing" />
    </scenarios>
  </route>
</routes>
""",
        encoding="utf-8",
    )
    example_route.write_text(
        """
<routes>
  <route id="example_route" town="Town03">
    <waypoints><position x="1" y="2" z="0.5" yaw="90" /></waypoints>
  </route>
</routes>
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("SCENARIO_RUNNER_ROOT", str(scenario_runner_root))
    get_settings.cache_clear()

    sources = discover_scenario_runner_route_sources()

    assert len(sources) == 1
    assert sources[0].provider == SCENARIO_RUNNER_ROUTES_PROVIDER
    assert sources[0].route_id == "town10_route"
    assert sources[0].map_name == "Town10HD_Opt"
    assert sources[0].provider_version["source_kind"] == "scenario_runner_route_xml"


def test_launch_recording_materialization_writes_lineage(monkeypatch) -> None:
    _write_sensor_profile()
    store = get_scenario_source_store()
    source = store.replace_sources([_source_record()])[0]
    monkeypatch.setattr("app.api.routes_scenario_sources._run_preflight", lambda **_: None)

    client = TestClient(app)
    response = client.post(
        f"/scenario-sources/{source.source_id}/launch-recording",
        json={
            "sensor_profile_name": "front_rgb",
            "fixed_delta_seconds": 0.05,
            "auto_start": False,
            "materialization_agent_type": "route_follower",
            "metadata": {"tags": ["materialize"], "description": "test materialization"},
        },
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    run = payload["run"]
    materialization = payload["materialization"]
    assert run["status"] == "CREATED"
    assert materialization["source_id"] == source.source_id
    assert materialization["run_id"] == run["run_id"]
    assert run["scenario_source"]["launch_mode"] == "leaderboard_route"
    assert run["scenario_source"]["materialization"] is True
    assert run["scenario_source"]["source_id"] == source.source_id
    assert run["scenario_source"]["sensor_profile_id"] == "front_rgb"
    assert run["scenario_source"]["fixed_delta_seconds"] == 0.05
    assert run["scenario_source"]["materialization_agent"]["type"] == "route_follower"
    assert run["hil_config"] is None
    assert run["recorder"]["enabled"] is True
    assert run["sensors"]["profile_name"] == "front_rgb"
    assert run["scenario_source"]["fixed_delta_seconds"] == 0.05


def test_publish_materialized_run_links_recording(monkeypatch) -> None:
    _write_sensor_profile()
    store = get_scenario_source_store()
    source = store.replace_sources([_source_record()])[0]
    monkeypatch.setattr("app.api.routes_scenario_sources._run_preflight", lambda **_: None)
    client = TestClient(app)
    launch_response = client.post(
        f"/scenario-sources/{source.source_id}/launch-recording",
        json={
            "sensor_profile_name": "front_rgb",
            "fixed_delta_seconds": 0.05,
            "auto_start": False,
            "materialization_agent_type": "route_follower",
        },
    )
    assert launch_response.status_code == 200
    run = launch_response.json()["data"]["run"]
    materialization = launch_response.json()["data"]["materialization"]
    artifact_store = ArtifactStore(get_settings().artifacts_root)
    recorder_path = artifact_store.run_dir(run["run_id"]) / "recorder" / f"{run['run_id']}.log"
    recorder_path.parent.mkdir(parents=True, exist_ok=True)
    recorder_path.write_bytes(b"materialized recorder")

    publish_response = client.post(
        "/scenario-recordings/from-run",
        json={"run_id": run["run_id"], "corner_case_labels": ["CutIn"]},
    )

    assert publish_response.status_code == 200
    recording = publish_response.json()["data"]
    assert recording["source_id"] == source.source_id
    assert recording["source_provider"] == "bench2drive"
    assert recording["materialization_id"] == materialization["materialization_id"]

    materializations_response = client.get(
        f"/scenario-sources/{source.source_id}/materializations"
    )
    assert materializations_response.status_code == 200
    linked = materializations_response.json()["data"][0]
    assert linked["recording_id"] == recording["recording_id"]
    assert linked["status"] == "published_asset_available"
