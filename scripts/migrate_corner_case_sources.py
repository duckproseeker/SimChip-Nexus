#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib import error, parse, request

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.scenario.maps import map_family_key  # noqa: E402

DEFAULT_PROVIDERS = (
    "official_scenariorunner",
    "scenario_runner_routes",
    "leaderboard",
)
DEFAULT_TAGS = ("third_party", "corner_case")
VISIBLE_VEHICLE_MOTION_LABELS = {
    "lane_change",
    "following",
    "lead_vehicle_brake",
    "ControlLoss",
    "DynamicObjectCrossing",
    "VehicleTurningRoute",
    "VehicleTurningRoutePedestrian",
    "StaticCutIn",
    "ParkingCutIn",
    "MergerIntoSlowTraffic",
}
TERMINAL_SUCCESS = {"COMPLETED"}
TERMINAL_FAILURE = {"FAILED", "CANCELED"}


@dataclass
class MigrationSelection:
    selected: list[dict[str, Any]] = field(default_factory=list)
    skipped: list[dict[str, Any]] = field(default_factory=list)


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_text_list(values: list[str] | tuple[str, ...] | None) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for value in values or []:
        item = str(value).strip()
        if item and item not in seen:
            normalized.append(item)
            seen.add(item)
    return normalized


def _labels(source: dict[str, Any]) -> list[str]:
    labels = source.get("corner_case_labels")
    if isinstance(labels, list):
        return _normalize_text_list([str(item) for item in labels])
    return []


def _source_ref(source: dict[str, Any]) -> str:
    source_path = str(source.get("source_path") or "").strip()
    route_id = str(source.get("route_id") or "").strip()
    scenario_type = str(source.get("scenario_type") or "").strip()
    suffix = route_id or scenario_type or str(source.get("source_id") or "").strip()
    return f"{source_path}#{suffix}" if suffix else source_path


def _source_name(source: dict[str, Any]) -> str:
    provider = str(source.get("provider") or "third_party").strip()
    route_id = str(source.get("route_id") or "").strip()
    scenario_type = str(source.get("scenario_type") or "").strip()
    map_name = str(source.get("map_name") or "").strip()
    identity = scenario_type or route_id or str(source.get("source_id") or "").strip()
    parts = [provider, identity, map_name]
    return " / ".join(part for part in parts if part)


def _label_bucket(source: dict[str, Any], requested_labels: set[str]) -> str:
    source_labels = _labels(source)
    if requested_labels:
        for label in source_labels:
            if label in requested_labels:
                return label
    if source_labels:
        return source_labels[0]
    return str(source.get("scenario_type") or source.get("source_id") or "unlabeled")


def _source_matches_filters(
    source: dict[str, Any],
    *,
    providers: set[str],
    map_names: set[str],
    labels: set[str],
) -> bool:
    provider = str(source.get("provider") or "").strip()
    if providers and provider not in providers:
        return False
    if map_names:
        source_map = str(source.get("map_name") or "").strip()
        if source_map not in map_names and map_family_key(source_map) not in {
            map_family_key(item) for item in map_names
        }:
            return False
    if labels and labels.isdisjoint(set(_labels(source))):
        return False
    return True


def _route_length_m(source: dict[str, Any]) -> float:
    metadata = source.get("parsed_metadata")
    if not isinstance(metadata, dict):
        return 0.0
    raw_value = metadata.get("route_length_m")
    try:
        return float(raw_value)
    except (TypeError, ValueError):
        return 0.0


def _quality_profile_allows(source: dict[str, Any], quality_profile: str) -> bool:
    if quality_profile == "all":
        return True
    provider = str(source.get("provider") or "").strip()
    source_labels = set(_labels(source))
    if source_labels.intersection(VISIBLE_VEHICLE_MOTION_LABELS):
        return True
    if provider == "scenario_runner_routes" and _route_length_m(source) >= 30.0:
        return True
    return False


def select_migration_sources(
    sources: list[dict[str, Any]],
    *,
    available_maps: set[str],
    providers: list[str],
    map_names: list[str],
    labels: list[str],
    quality_profile: str,
    existing_source_refs: set[str] | None = None,
    max_per_label: int,
    max_total: int | None,
) -> MigrationSelection:
    provider_filter = set(_normalize_text_list(providers))
    map_filter = set(_normalize_text_list(map_names))
    label_filter = set(_normalize_text_list(labels))
    available_families = {map_family_key(item) for item in available_maps}
    selected: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    label_counts: dict[str, int] = {}
    existing_refs = existing_source_refs or set()

    for source in sources:
        source_id = str(source.get("source_id") or "").strip()
        if not _source_matches_filters(
            source,
            providers=provider_filter,
            map_names=map_filter,
            labels=label_filter,
        ):
            continue

        map_name = str(source.get("map_name") or "").strip()
        if map_family_key(map_name) not in available_families:
            skipped.append(
                {
                    "source_id": source_id,
                    "provider": source.get("provider"),
                    "map_name": map_name,
                    "labels": _labels(source),
                    "reason": "map_unavailable",
                }
            )
            continue

        if not _quality_profile_allows(source, quality_profile):
            skipped.append(
                {
                    "source_id": source_id,
                    "provider": source.get("provider"),
                    "map_name": map_name,
                    "labels": _labels(source),
                    "reason": "quality_profile",
                    "quality_profile": quality_profile,
                }
            )
            continue

        source_ref = _source_ref(source)
        if source_ref and source_ref in existing_refs:
            skipped.append(
                {
                    "source_id": source_id,
                    "provider": source.get("provider"),
                    "map_name": map_name,
                    "labels": _labels(source),
                    "source_ref": source_ref,
                    "reason": "already_published",
                }
            )
            continue

        bucket = _label_bucket(source, label_filter)
        if max_per_label > 0 and label_counts.get(bucket, 0) >= max_per_label:
            skipped.append(
                {
                    "source_id": source_id,
                    "provider": source.get("provider"),
                    "map_name": map_name,
                    "labels": _labels(source),
                    "reason": "max_per_label",
                    "label": bucket,
                }
            )
            continue

        selected.append(source)
        label_counts[bucket] = label_counts.get(bucket, 0) + 1
        if max_total is not None and max_total > 0 and len(selected) >= max_total:
            break

    return MigrationSelection(selected=selected, skipped=skipped)


def build_publish_payload(source: dict[str, Any], run_id: str) -> dict[str, Any]:
    provider = str(source.get("provider") or "third_party").strip()
    recommended_duration = source.get("recommended_duration_seconds")
    payload: dict[str, Any] = {
        "run_id": run_id,
        "name": _source_name(source),
        "source_type": provider,
        "source_ref": _source_ref(source),
        "recommended_start_seconds": 0.0,
        "tags": [*DEFAULT_TAGS, provider],
        "corner_case_labels": _labels(source),
    }
    if isinstance(recommended_duration, int | float) and recommended_duration > 0:
        payload["recommended_duration_seconds"] = float(recommended_duration)
    return payload


def summarize_report(report: dict[str, Any]) -> dict[str, int]:
    results = report.get("results") if isinstance(report.get("results"), list) else []
    skipped = report.get("skipped") if isinstance(report.get("skipped"), list) else []
    return {
        "selected": len(results),
        "skipped": len(skipped),
        "published": sum(1 for item in results if item.get("status") == "published"),
        "failed": sum(1 for item in results if item.get("status") == "failed"),
        "planned": sum(1 for item in results if item.get("status") == "planned"),
    }


class ApiClient:
    def __init__(self, base_url: str, timeout_seconds: int) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        *,
        timeout_seconds: int | None = None,
    ) -> Any:
        data = None
        headers: dict[str, str] = {}
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = request.Request(f"{self.base_url}{path}", data=data, headers=headers, method=method)
        try:
            with request.urlopen(req, timeout=timeout_seconds or self.timeout_seconds) as resp:
                body = resp.read()
                content_type = resp.headers.get("Content-Type", "")
                if "application/json" in content_type:
                    return json.loads(body.decode("utf-8"))
                return body
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"{method} {path} failed with HTTP {exc.code}: {detail}") from exc


def fetch_sources(client: ApiClient) -> list[dict[str, Any]]:
    payload = client.request("POST", "/scenario-sources/rescan", {})
    sources = payload.get("data", {}).get("sources", [])
    if not isinstance(sources, list):
        raise RuntimeError("/scenario-sources/rescan returned an invalid sources payload")
    return [item for item in sources if isinstance(item, dict)]


def fetch_available_maps(client: ApiClient) -> set[str]:
    payload = client.request("GET", "/maps")
    maps = payload.get("data", {}).get("maps", [])
    if not isinstance(maps, list):
        raise RuntimeError("/maps returned an invalid maps payload")
    map_names: set[str] = set()
    for item in maps:
        if not isinstance(item, dict):
            continue
        map_name = str(item.get("map_name") or "").strip()
        if map_name:
            map_names.add(map_name)
        variants = item.get("available_variants")
        if isinstance(variants, list):
            map_names.update(str(value).strip() for value in variants if str(value).strip())
    return map_names


def fetch_existing_third_party_source_refs(client: ApiClient) -> set[str]:
    query = parse.urlencode({"tag": "third_party"})
    payload = client.request("GET", f"/scenario-recordings?{query}")
    recordings = payload.get("data", {}).get("recordings", [])
    if not isinstance(recordings, list):
        raise RuntimeError("/scenario-recordings returned an invalid recordings payload")
    source_refs: set[str] = set()
    for item in recordings:
        if not isinstance(item, dict):
            continue
        source_ref = str(item.get("source_ref") or "").strip()
        if source_ref:
            source_refs.add(source_ref)
    return source_refs


def wait_for_run_completion(
    client: ApiClient,
    run_id: str,
    *,
    timeout_seconds: int,
    poll_interval_seconds: float,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    last_run: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        payload = client.request("GET", f"/runs/{run_id}")
        run = payload.get("data", {})
        if not isinstance(run, dict):
            raise RuntimeError(f"/runs/{run_id} returned an invalid run payload")
        last_run = run
        status = str(run.get("status") or "")
        print(f"[corner-migration] run {run_id} status={status}", flush=True)
        if status in TERMINAL_SUCCESS:
            return run
        if status in TERMINAL_FAILURE:
            raise RuntimeError(f"run {run_id} ended with status={status}: {run.get('error_reason')}")
        time.sleep(poll_interval_seconds)
    raise RuntimeError(f"run {run_id} did not complete within {timeout_seconds}s; last={last_run}")


def _write_report(report: dict[str, Any], report_path: Path) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")


def _default_report_path() -> Path:
    return PROJECT_ROOT / "run_data" / "migration_reports" / f"corner_case_migration_{_timestamp()}.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Internal batch migration from third-party scenario sources to ScenarioRecording assets."
    )
    parser.add_argument(
        "--base-url",
        default=os.environ.get("DUCKPARK_API_BASE_URL", "http://127.0.0.1:8000"),
    )
    parser.add_argument("--provider", action="append", default=[])
    parser.add_argument("--map-name", action="append", default=[])
    parser.add_argument("--label", action="append", default=[])
    parser.add_argument("--available-map", action="append", default=[])
    parser.add_argument("--sensor-profile-name", default="front_rgb")
    parser.add_argument("--fixed-delta-seconds", type=float, default=0.05)
    parser.add_argument(
        "--quality-profile",
        choices=("visible_vehicle_motion", "all"),
        default="visible_vehicle_motion",
        help="Default keeps only sources likely to produce visible lane-change/vehicle-motion replay.",
    )
    parser.add_argument("--max-per-label", type=int, default=1)
    parser.add_argument("--max-total", type=int, default=0)
    parser.add_argument("--timeout-seconds", type=int, default=20)
    parser.add_argument("--run-timeout-seconds", type=int, default=900)
    parser.add_argument("--poll-interval-seconds", type=float, default=3.0)
    parser.add_argument("--report-path", type=Path, default=None)
    parser.add_argument("--execute", action="store_true", help="Create runs and publish recordings.")
    parser.add_argument(
        "--include-existing",
        action="store_true",
        help="Allow sources that already have a third_party ScenarioRecording with the same source_ref.",
    )
    parser.add_argument(
        "--no-wait",
        action="store_true",
        help="Only create materialization runs. Publishing requires waiting for completion.",
    )
    parser.add_argument(
        "--no-auto-start",
        action="store_true",
        help="Create materialization runs without starting them.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    client = ApiClient(args.base_url, args.timeout_seconds)
    sources = fetch_sources(client)
    available_maps = set(args.available_map) if args.available_map else fetch_available_maps(client)
    existing_source_refs = (
        set() if args.include_existing else fetch_existing_third_party_source_refs(client)
    )
    providers = args.provider or list(DEFAULT_PROVIDERS)
    selection = select_migration_sources(
        sources,
        available_maps=available_maps,
        providers=providers,
        map_names=args.map_name,
        labels=args.label,
        quality_profile=args.quality_profile,
        existing_source_refs=existing_source_refs,
        max_per_label=max(0, args.max_per_label),
        max_total=args.max_total if args.max_total > 0 else None,
    )
    report: dict[str, Any] = {
        "created_at_utc": _iso_now(),
        "base_url": args.base_url,
        "dry_run": not args.execute,
        "filters": {
            "providers": providers,
            "map_names": args.map_name,
            "labels": args.label,
            "quality_profile": args.quality_profile,
            "skip_existing": not args.include_existing,
            "max_per_label": args.max_per_label,
            "max_total": args.max_total,
        },
        "available_maps": sorted(available_maps),
        "existing_source_ref_count": len(existing_source_refs),
        "skipped": selection.skipped,
        "results": [],
    }

    for source in selection.selected:
        source_id = str(source.get("source_id") or "")
        result: dict[str, Any] = {
            "source_id": source_id,
            "provider": source.get("provider"),
            "map_name": source.get("map_name"),
            "labels": _labels(source),
            "source_ref": _source_ref(source),
        }
        try:
            if not args.execute:
                result["status"] = "planned"
                report["results"].append(result)
                continue

            launch_payload = {
                "sensor_profile_name": args.sensor_profile_name,
                "fixed_delta_seconds": args.fixed_delta_seconds,
                "auto_start": not args.no_auto_start,
                "materialization_agent_type": "route_follower",
                "metadata": {
                    "author": "corner-case-migration",
                    "tags": [*DEFAULT_TAGS, str(source.get("provider") or "third_party")],
                    "description": f"Materialize third-party corner case source {source_id}",
                },
            }
            launch = client.request(
                "POST",
                f"/scenario-sources/{source_id}/launch-recording",
                launch_payload,
                timeout_seconds=max(args.timeout_seconds, 60),
            )
            data = launch.get("data", {})
            run = data.get("run", {}) if isinstance(data, dict) else {}
            materialization = data.get("materialization", {}) if isinstance(data, dict) else {}
            run_id = str(run.get("run_id") or "")
            result["run_id"] = run_id
            result["materialization_id"] = materialization.get("materialization_id")
            if args.no_wait or args.no_auto_start:
                result["status"] = "run_created"
                report["results"].append(result)
                continue
            if not run_id:
                raise RuntimeError("launch-recording response did not include run_id")
            wait_for_run_completion(
                client,
                run_id,
                timeout_seconds=args.run_timeout_seconds,
                poll_interval_seconds=args.poll_interval_seconds,
            )
            publish_payload = build_publish_payload(source, run_id)
            published = client.request(
                "POST",
                "/scenario-recordings/from-run",
                publish_payload,
                timeout_seconds=max(args.timeout_seconds, 60),
            )
            recording = published.get("data", {})
            result.update(
                {
                    "status": "published",
                    "recording_id": recording.get("recording_id"),
                    "recorder_file_sha256": recording.get("recorder_file_sha256"),
                    "publish_payload": publish_payload,
                }
            )
        except Exception as exc:  # noqa: BLE001
            result["status"] = "failed"
            result["error"] = str(exc)
        report["results"].append(result)

    report["summary"] = summarize_report(report)
    report_path = args.report_path.expanduser().resolve() if args.report_path else _default_report_path()
    _write_report(report, report_path)
    print(json.dumps({"report_path": str(report_path), **report["summary"]}, ensure_ascii=False))
    return 1 if report["summary"]["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
