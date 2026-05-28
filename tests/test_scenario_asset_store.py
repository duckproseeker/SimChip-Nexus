from app.storage.scenario_asset_store import ScenarioAssetStore


def test_create_and_get(tmp_path):
    store = ScenarioAssetStore(tmp_path / "scenarios.sqlite3")
    asset = store.create(
        name="雨天行人横穿-01",
        recorder_log_path="/data/recordings/rain_pedestrian.log",
        map_name="Town03",
        duration_seconds=120.5,
        tags=["雨天", "行人横穿"],
        description="corner case",
        file_size_bytes=5242880,
    )
    assert asset.name == "雨天行人横穿-01"
    assert asset.map_name == "Town03"
    assert asset.tags == ["雨天", "行人横穿"]
    fetched = store.get(asset.id)
    assert fetched.id == asset.id
    assert fetched.duration_seconds == 120.5


def test_list_with_tag_filter(tmp_path):
    store = ScenarioAssetStore(tmp_path / "scenarios.sqlite3")
    store.create(name="a", recorder_log_path="/a.log", tags=["雨天"])
    store.create(name="b", recorder_log_path="/b.log", tags=["晴天"])
    store.create(name="c", recorder_log_path="/c.log", tags=["雨天", "夜间"])
    results = store.list(tag="雨天")
    assert len(results) == 2
    assert all("雨天" in r.tags for r in results)


def test_list_with_map_filter(tmp_path):
    store = ScenarioAssetStore(tmp_path / "scenarios.sqlite3")
    store.create(name="a", recorder_log_path="/a.log", map_name="Town03")
    store.create(name="b", recorder_log_path="/b.log", map_name="Town04")
    results = store.list(map_name="Town03")
    assert len(results) == 1
    assert results[0].map_name == "Town03"


def test_update_tags(tmp_path):
    store = ScenarioAssetStore(tmp_path / "scenarios.sqlite3")
    asset = store.create(name="a", recorder_log_path="/a.log", tags=["旧标签"])
    store.update(asset.id, tags=["新标签1", "新标签2"])
    updated = store.get(asset.id)
    assert updated.tags == ["新标签1", "新标签2"]


def test_delete(tmp_path):
    store = ScenarioAssetStore(tmp_path / "scenarios.sqlite3")
    asset = store.create(name="a", recorder_log_path="/a.log")
    store.delete(asset.id)
    results = store.list()
    assert len(results) == 0
