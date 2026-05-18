#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import get_settings  # noqa: E402
from app.core.models import ScenarioRecordingRecord  # noqa: E402
from app.storage.scenario_recording_store import ScenarioRecordingStore  # noqa: E402
from app.utils.time_utils import now_utc  # noqa: E402


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _source_type(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".log":
        return "carla_recorder_log"
    if suffix == ".xosc":
        return "openscenario_xosc"
    if suffix == ".xml":
        return "route_xml"
    raise ValueError(f"Unsupported source file: {path}")


def _build_recording_id(source_path: Path, recorder_sha256: str) -> str:
    stem = "".join(ch if ch.isalnum() or ch in {"_", "-"} else "_" for ch in source_path.stem)
    return f"rec_import_{stem}_{recorder_sha256[:12]}".strip("_")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Internal importer for local ScenarioRecording assets. Direct .log imports are "
            "registered as replay assets. .xosc and route XML inputs must be paired with "
            "--recorder-log because they are source definitions, not replayable world-state logs."
        )
    )
    parser.add_argument("source", type=Path, help=".log, .xosc, or route XML file")
    parser.add_argument(
        "--recorder-log",
        type=Path,
        default=None,
        help="Existing CARLA recorder .log to bind when source is .xosc or route XML",
    )
    parser.add_argument("--name", default=None, help="Asset display name")
    parser.add_argument("--scenario-name", default=None, help="Scenario name")
    parser.add_argument("--map-name", default="UNKNOWN_MAP", help="CARLA map name")
    parser.add_argument("--duration-seconds", type=float, default=None)
    parser.add_argument("--recommended-start-seconds", type=float, default=None)
    parser.add_argument("--recommended-duration-seconds", type=float, default=None)
    parser.add_argument("--carla-version", default=None)
    parser.add_argument("--map-version", default=None)
    parser.add_argument("--tag", action="append", default=[])
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    source_path = args.source.expanduser().resolve()
    if not source_path.is_file():
        raise SystemExit(f"source file not found: {source_path}")

    source_type = _source_type(source_path)
    recorder_path = source_path if source_type == "carla_recorder_log" else args.recorder_log
    if recorder_path is None:
        raise SystemExit("--recorder-log is required for .xosc and route XML imports")
    recorder_path = recorder_path.expanduser().resolve()
    if not recorder_path.is_file():
        raise SystemExit(f"recorder log not found: {recorder_path}")

    settings = get_settings()
    store = ScenarioRecordingStore(settings.scenario_recordings_root)
    recorder_sha256 = _sha256_file(recorder_path)
    recording_id = _build_recording_id(source_path, recorder_sha256)
    timestamp = now_utc()
    record = ScenarioRecordingRecord(
        recording_id=recording_id,
        name=args.name or source_path.stem,
        source_run_id=f"offline_import_{recording_id}",
        source_run_status="IMPORTED",
        source_type=source_type,
        source_ref=str(source_path),
        scenario_name=args.scenario_name or source_path.stem,
        map_name=args.map_name,
        carla_version=args.carla_version,
        map_version=args.map_version,
        recorder_log_path=str(recorder_path),
        recorder_file_size_bytes=recorder_path.stat().st_size,
        recorder_file_sha256=recorder_sha256,
        duration_seconds=args.duration_seconds,
        recommended_start_seconds=args.recommended_start_seconds,
        recommended_duration_seconds=args.recommended_duration_seconds,
        tags=args.tag,
        determinism_level="world_state_replay_with_carla_live_sensors",
        created_at=timestamp,
        updated_at=timestamp,
    )
    created = store.create(record)
    print(created.model_dump_json(indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
