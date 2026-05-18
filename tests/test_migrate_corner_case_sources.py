from __future__ import annotations

from scripts.migrate_corner_case_sources import (
    build_publish_payload,
    select_migration_sources,
    summarize_report,
)


def _source(
    source_id: str,
    *,
    provider: str,
    map_name: str,
    labels: list[str],
    duration: float = 30.0,
) -> dict[str, object]:
    return {
        "source_id": source_id,
        "provider": provider,
        "source_path": f"/third-party/{source_id}.xml",
        "route_id": source_id,
        "scenario_type": labels[0] if labels else "route",
        "map_name": map_name,
        "recommended_duration_seconds": duration,
        "corner_case_labels": labels,
    }


def test_select_migration_sources_skips_unavailable_maps_and_caps_labels() -> None:
    sources = [
        _source(
            "official_pedestrian",
            provider="official_scenariorunner",
            map_name="Town01",
            labels=["pedestrian_crossing"],
        ),
        _source(
            "leaderboard_pedestrian",
            provider="leaderboard",
            map_name="Town12",
            labels=["pedestrian_crossing"],
        ),
        _source(
            "official_pedestrian_duplicate",
            provider="official_scenariorunner",
            map_name="Town01_Opt",
            labels=["pedestrian_crossing"],
        ),
        _source(
            "official_cyclist",
            provider="official_scenariorunner",
            map_name="Town04",
            labels=["cyclist_crossing"],
        ),
    ]

    selection = select_migration_sources(
        sources,
        available_maps={"Town01_Opt", "Town04_Opt"},
        providers=["official_scenariorunner", "leaderboard"],
        map_names=[],
        labels=[],
        quality_profile="all",
        max_per_label=1,
        max_total=None,
    )

    assert [item["source_id"] for item in selection.selected] == [
        "official_pedestrian",
        "official_cyclist",
    ]
    skipped_by_id = {item["source_id"]: item["reason"] for item in selection.skipped}
    assert skipped_by_id["leaderboard_pedestrian"] == "map_unavailable"
    assert skipped_by_id["official_pedestrian_duplicate"] == "max_per_label"


def test_select_migration_sources_defaults_to_visible_vehicle_motion() -> None:
    sources = [
        _source(
            "official_pedestrian",
            provider="official_scenariorunner",
            map_name="Town01",
            labels=["pedestrian_crossing"],
        ),
        _source(
            "official_lane_change",
            provider="official_scenariorunner",
            map_name="Town04",
            labels=["lane_change"],
        ),
        {
            **_source(
                "route_motion",
                provider="scenario_runner_routes",
                map_name="Town10HD_Opt",
                labels=["route"],
            ),
            "parsed_metadata": {"route_length_m": 120.0},
        },
    ]

    selection = select_migration_sources(
        sources,
        available_maps={"Town01_Opt", "Town04_Opt", "Town10HD_Opt"},
        providers=["official_scenariorunner", "scenario_runner_routes"],
        map_names=[],
        labels=[],
        quality_profile="visible_vehicle_motion",
        max_per_label=1,
        max_total=None,
    )

    assert [item["source_id"] for item in selection.selected] == [
        "official_lane_change",
        "route_motion",
    ]
    assert selection.skipped[0]["source_id"] == "official_pedestrian"
    assert selection.skipped[0]["reason"] == "quality_profile"


def test_select_migration_sources_skips_existing_before_label_cap() -> None:
    existing = _source(
        "existing_lane_change",
        provider="official_scenariorunner",
        map_name="Town04",
        labels=["lane_change"],
    )
    replacement = _source(
        "new_lane_change",
        provider="official_scenariorunner",
        map_name="Town04",
        labels=["lane_change"],
    )

    selection = select_migration_sources(
        [existing, replacement],
        available_maps={"Town04_Opt"},
        providers=["official_scenariorunner"],
        map_names=[],
        labels=[],
        quality_profile="visible_vehicle_motion",
        existing_source_refs={"/third-party/existing_lane_change.xml#existing_lane_change"},
        max_per_label=1,
        max_total=None,
    )

    assert [item["source_id"] for item in selection.selected] == ["new_lane_change"]
    assert selection.skipped[0]["source_id"] == "existing_lane_change"
    assert selection.skipped[0]["reason"] == "already_published"


def test_build_publish_payload_uses_third_party_lineage() -> None:
    source = _source(
        "route_001",
        provider="scenario_runner_routes",
        map_name="Town10HD_Opt",
        labels=["DynamicObjectCrossing"],
        duration=45.0,
    )

    payload = build_publish_payload(source, "run_materialized")

    assert payload["run_id"] == "run_materialized"
    assert payload["source_type"] == "scenario_runner_routes"
    assert payload["source_ref"] == "/third-party/route_001.xml#route_001"
    assert payload["recommended_start_seconds"] == 0.0
    assert payload["recommended_duration_seconds"] == 45.0
    assert payload["tags"] == ["third_party", "corner_case", "scenario_runner_routes"]
    assert payload["corner_case_labels"] == ["DynamicObjectCrossing"]


def test_summarize_report_counts_statuses() -> None:
    report = {
        "skipped": [{"source_id": "skip"}],
        "results": [
            {"status": "planned"},
            {"status": "published"},
            {"status": "failed"},
        ],
    }

    assert summarize_report(report) == {
        "selected": 3,
        "skipped": 1,
        "published": 1,
        "failed": 1,
        "planned": 1,
    }
