from __future__ import annotations

from app.scenario.maps import (
    collapse_available_maps,
    is_supported_runtime_map,
    prefer_optimized_map_request,
)


def test_collapse_available_maps_prefers_optimized_variant() -> None:
    items = collapse_available_maps(
        ["/Game/Carla/Maps/Town01", "/Game/Carla/Maps/Town01_Opt", "Town02"]
    )

    assert items[0]["display_name"] == "Town01"
    assert items[0]["map_name"] == "Town01_Opt"
    assert items[0]["preferred_variant"] == "optimized"
    assert items[0]["available_variants"] == ["Town01", "Town01_Opt"]
    assert items[1]["display_name"] == "Town02"


def test_prefer_optimized_map_request_keeps_non_optimized_unknown_map() -> None:
    assert prefer_optimized_map_request("Town01") == "Town01_Opt"
    assert prefer_optimized_map_request("AnnotationColorLandscape") == "AnnotationColorLandscape"


def test_collapse_available_maps_filters_annotation_color_landscape() -> None:
    items = collapse_available_maps(
        [
            "/Game/Carla/Maps/Town01",
            "/Game/Carla/Maps/AnnotationColorLandscape",
            "Town02_Opt",
        ]
    )

    assert [item["display_name"] for item in items] == ["Town01", "Town02"]
    assert is_supported_runtime_map("Town01_Opt") is True
    assert is_supported_runtime_map("AnnotationColorLandscape") is False
