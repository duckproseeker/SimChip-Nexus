from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

from app.core.config import Settings, get_settings
from app.core.models import ScenarioSourceRecord
from app.scenario.maps import map_family_key, normalize_map_tail
from app.scenario.official_runner import OFFICIAL_OPENSCENARIO_PRESETS, resolve_official_xosc_path
from app.utils.time_utils import now_utc

OFFICIAL_OPENSCENARIO_PROVIDER = "official_scenariorunner"
SCENARIO_RUNNER_ROUTES_PROVIDER = "scenario_runner_routes"
BENCH2DRIVE_PROVIDER = "bench2drive"
LEADERBOARD_PROVIDER = "leaderboard"

OFFICIAL_CORNER_CASE_LABELS: dict[str, list[str]] = {
    "osc_follow_leading_vehicle": ["following", "lead_vehicle_brake"],
    "osc_lane_change_simple": ["lane_change"],
    "osc_sync_arrival_intersection": ["intersection", "cross_traffic"],
    "osc_intersection_collision_avoidance": ["intersection", "collision_avoidance"],
    "osc_pedestrian_crossing_front": ["pedestrian_crossing"],
    "osc_cyclist_crossing": ["cyclist_crossing"],
    "osc_slalom": ["obstacle_avoidance"],
    "osc_changing_weather": ["weather_change"],
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stable_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _git_metadata(root: Path | None) -> dict[str, Any]:
    if root is None or not root.exists():
        return {}
    metadata: dict[str, Any] = {}
    commands = {
        "git_commit": ["git", "rev-parse", "HEAD"],
        "git_remote": ["git", "config", "--get", "remote.origin.url"],
    }
    for key, command in commands.items():
        try:
            completed = subprocess.run(
                command,
                cwd=root,
                capture_output=True,
                text=True,
                timeout=2.0,
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        if completed.returncode == 0 and completed.stdout.strip():
            metadata[key] = completed.stdout.strip()
    return metadata


def _tag_name(element: ElementTree.Element) -> str:
    return element.tag.rsplit("}", maxsplit=1)[-1]


def _iter_named(root: ElementTree.Element, name: str) -> list[ElementTree.Element]:
    return [item for item in root.iter() if _tag_name(item) == name]


def _parse_xml(path: Path) -> ElementTree.Element | None:
    try:
        return ElementTree.parse(path).getroot()
    except (ElementTree.ParseError, OSError):
        return None


def _official_map_name(root: ElementTree.Element | None) -> str:
    if root is None:
        return "Town01"
    for item in _iter_named(root, "LogicFile"):
        filepath = item.attrib.get("filepath", "").strip()
        if filepath:
            return normalize_map_tail(filepath)
    return "Town01"


def _official_compatibility(path: Path | None, root: ElementTree.Element | None) -> tuple[str, str | None]:
    if path is None or not path.exists():
        return "incompatible", "官方 OpenSCENARIO 文件不存在"
    if root is None:
        return "unsupported_openscenario_feature", "OpenSCENARIO XML 解析失败"
    return "ok", None


def discover_official_openscenario_sources(
    settings: Settings | None = None,
) -> list[ScenarioSourceRecord]:
    settings = settings or get_settings()
    if settings.scenario_runner_root is None:
        return []
    now = now_utc()
    provider_version = {
        **_git_metadata(settings.scenario_runner_root),
        "expected_carla_version": "0.9.x",
        "source_kind": "official_scenariorunner_xosc",
    }
    sources: list[ScenarioSourceRecord] = []
    for preset in OFFICIAL_OPENSCENARIO_PRESETS:
        path = resolve_official_xosc_path(preset.relative_xosc_path, settings)
        root = _parse_xml(path) if path is not None else None
        source_hash = sha256_file(path) if path is not None and path.exists() else ""
        status, message = _official_compatibility(path, root)
        map_name = _official_map_name(root)
        source_id = stable_hash(
            f"{OFFICIAL_OPENSCENARIO_PROVIDER}:{preset.relative_xosc_path}:{source_hash}"
        )[:24]
        sources.append(
            ScenarioSourceRecord(
                source_id=f"src_{source_id}",
                provider=OFFICIAL_OPENSCENARIO_PROVIDER,
                provider_version=provider_version,
                source_path=str(path or preset.relative_xosc_path),
                source_hash=source_hash,
                route_id=preset.scenario_id,
                scenario_type=preset.scenario_id,
                map_name=map_name,
                weather={"preset": "ClearNoon"},
                recommended_duration_seconds=30.0,
                corner_case_labels=OFFICIAL_CORNER_CASE_LABELS.get(
                    preset.scenario_id, ["openscenario_baseline"]
                ),
                compatibility_status=status,
                compatibility_message=message,
                parsed_metadata={
                    "display_name": preset.display_name,
                    "description": preset.description,
                    "relative_xosc_path": preset.relative_xosc_path,
                    "launch_mode": "openscenario",
                },
                discovered_at=now,
                updated_at=now,
            )
        )
    return sources


def _route_waypoints(route: ElementTree.Element) -> list[dict[str, float]]:
    waypoints: list[dict[str, float]] = []
    for item in route.iter():
        tag = _tag_name(item)
        if tag not in {"position", "waypoint"}:
            continue
        attrs = item.attrib
        try:
            x = float(attrs.get("x") or attrs.get("X") or attrs.get("pos_x") or 0.0)
            y = float(attrs.get("y") or attrs.get("Y") or attrs.get("pos_y") or 0.0)
            z = float(attrs.get("z") or attrs.get("Z") or attrs.get("pos_z") or 0.5)
            yaw = float(attrs.get("yaw") or attrs.get("Yaw") or 0.0)
        except ValueError:
            continue
        waypoints.append({"x": x, "y": y, "z": z, "roll": 0.0, "pitch": 0.0, "yaw": yaw})
    return waypoints


def _route_weather(route: ElementTree.Element) -> dict[str, Any]:
    for item in route.iter():
        if _tag_name(item).lower() in {"weather", "weathers"} and item.attrib:
            weather: dict[str, Any] = {"preset": item.attrib.get("preset", "ClearNoon")}
            for key, value in item.attrib.items():
                if key == "preset":
                    continue
                try:
                    weather[key] = float(value)
                except ValueError:
                    weather[key] = value
            return weather
    return {"preset": "ClearNoon"}


def _route_scenario_types(route: ElementTree.Element) -> list[str]:
    scenario_types: list[str] = []
    seen: set[str] = set()
    for item in route.iter():
        if _tag_name(item).lower() != "scenario":
            continue
        scenario_type = (
            item.attrib.get("type")
            or item.attrib.get("name")
            or item.attrib.get("scenario_type")
            or ""
        ).strip()
        if scenario_type and scenario_type not in seen:
            scenario_types.append(scenario_type)
            seen.add(scenario_type)
    return scenario_types


def _route_length_m(waypoints: list[dict[str, float]]) -> float:
    total = 0.0
    for previous, current in zip(waypoints, waypoints[1:], strict=False):
        dx = float(current["x"]) - float(previous["x"])
        dy = float(current["y"]) - float(previous["y"])
        total += (dx * dx + dy * dy) ** 0.5
    return total


def _find_route_xml_files(root: Path) -> list[Path]:
    if not root.exists():
        return []
    files = [
        path
        for path in root.rglob("*.xml")
        if "route" in path.name.lower() or "routes" in str(path.parent).lower()
    ]
    return sorted(path for path in files if path.is_file())


def _find_scenario_runner_route_xml_files(root: Path) -> list[Path]:
    data_root = root / "srunner" / "data"
    if not data_root.exists():
        return []
    return sorted(path for path in data_root.glob("*.xml") if path.is_file())


def discover_route_xml_sources(
    *,
    provider: str,
    root: Path | None,
    expected_leaderboard_version: str = "2.0",
    route_xml_files: list[Path] | None = None,
    source_kind: str = "leaderboard_route_xml",
) -> list[ScenarioSourceRecord]:
    if root is None or not root.exists():
        return []
    now = now_utc()
    provider_version = {
        **_git_metadata(root),
        "expected_carla_version": "0.9.16",
        "expected_leaderboard_version": expected_leaderboard_version,
        "source_kind": source_kind,
    }
    sources: list[ScenarioSourceRecord] = []
    for route_xml_path in route_xml_files if route_xml_files is not None else _find_route_xml_files(root):
        root_element = _parse_xml(route_xml_path)
        if root_element is None:
            continue
        source_hash = sha256_file(route_xml_path)
        routes = [item for item in root_element.iter() if _tag_name(item) == "route"]
        for route in routes:
            route_id = str(route.attrib.get("id") or "").strip()
            town = (
                route.attrib.get("town")
                or route.attrib.get("map")
                or route.attrib.get("town_name")
                or ""
            ).strip()
            if not route_id or not town:
                continue
            waypoints = _route_waypoints(route)
            scenario_types = _route_scenario_types(route)
            route_length_m = _route_length_m(waypoints)
            duration = max(20.0, min(300.0, route_length_m / 6.0)) if route_length_m else 60.0
            compatibility_status = "ok"
            compatibility_message = None
            if not waypoints:
                compatibility_status = "missing_route"
                compatibility_message = "route XML 未解析到 waypoint"
            source_id_hash = stable_hash(
                f"{provider}:{source_hash}:{route_id}:{map_family_key(town)}"
            )[:24]
            sources.append(
                ScenarioSourceRecord(
                    source_id=f"src_{source_id_hash}",
                    provider=provider,
                    provider_version={**provider_version, "route_file_hash": source_hash},
                    source_path=str(route_xml_path),
                    source_hash=source_hash,
                    route_id=route_id,
                    scenario_type=scenario_types[0] if scenario_types else "route",
                    map_name=normalize_map_tail(town),
                    weather=_route_weather(route),
                    recommended_duration_seconds=duration,
                    corner_case_labels=scenario_types or ["route"],
                    compatibility_status=compatibility_status,
                    compatibility_message=compatibility_message,
                    parsed_metadata={
                        "route_xml_path": str(route_xml_path),
                        "route_xml_hash": source_hash,
                        "route_id": route_id,
                        "waypoints": waypoints,
                        "scenario_types": scenario_types,
                        "route_length_m": route_length_m,
                        "launch_mode": "leaderboard_route",
                    },
                    discovered_at=now,
                    updated_at=now,
                )
            )
    return sources


def discover_scenario_runner_route_sources(settings: Settings | None = None) -> list[ScenarioSourceRecord]:
    settings = settings or get_settings()
    if settings.scenario_runner_root is None:
        return []
    return discover_route_xml_sources(
        provider=SCENARIO_RUNNER_ROUTES_PROVIDER,
        root=settings.scenario_runner_root,
        expected_leaderboard_version="scenario_runner",
        route_xml_files=_find_scenario_runner_route_xml_files(settings.scenario_runner_root),
        source_kind="scenario_runner_route_xml",
    )


def discover_scenario_sources(settings: Settings | None = None) -> list[ScenarioSourceRecord]:
    settings = settings or get_settings()
    return [
        *discover_official_openscenario_sources(settings),
        *discover_scenario_runner_route_sources(settings),
        *discover_route_xml_sources(
            provider=BENCH2DRIVE_PROVIDER,
            root=settings.bench2drive_root,
            expected_leaderboard_version="2.0",
        ),
        *discover_route_xml_sources(
            provider=LEADERBOARD_PROVIDER,
            root=settings.leaderboard_root,
            expected_leaderboard_version="2.0",
        ),
    ]
