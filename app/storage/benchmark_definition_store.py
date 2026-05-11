from __future__ import annotations

import json
from pathlib import Path

from app.core.errors import ConflictError, NotFoundError
from app.core.models import BenchmarkDefinitionRecord
from app.platform.catalog import build_default_benchmark_definitions
from app.utils.file_utils import atomic_write_json, ensure_dir
from app.utils.time_utils import now_utc

LEGACY_PROJECT_IDS = {"jetson-nano", "fudan-fpai", "rk3568"}
SYNCED_FIELDS = (
    "project_ids",
    "default_project_id",
    "planning_mode",
    "candidate_scenario_ids",
    "supports_duration_seconds",
    "default_duration_seconds",
    "queue_note",
)


class BenchmarkDefinitionStore:
    def __init__(self, benchmark_definitions_root: Path) -> None:
        self._benchmark_definitions_root = ensure_dir(benchmark_definitions_root)

    def _definition_path(self, benchmark_definition_id: str) -> Path:
        return self._benchmark_definitions_root / f"{benchmark_definition_id}.json"

    def _ensure_seeded(self) -> None:
        existing_paths = {
            path.stem: path for path in self._benchmark_definitions_root.glob("*.json")
        }
        default_definitions = build_default_benchmark_definitions()

        if not existing_paths:
            for definition in default_definitions:
                self.create(definition)
            return

        for definition in default_definitions:
            if definition.benchmark_definition_id not in existing_paths:
                self.create(definition)
                continue

            with existing_paths[definition.benchmark_definition_id].open(
                "r", encoding="utf-8"
            ) as handle:
                current = BenchmarkDefinitionRecord.model_validate(json.load(handle))
            changed = False
            if set(current.project_ids).issubset(LEGACY_PROJECT_IDS):
                current.project_ids = definition.project_ids
                changed = True
            for field_name in SYNCED_FIELDS:
                if getattr(current, field_name) == getattr(definition, field_name):
                    continue
                setattr(current, field_name, getattr(definition, field_name))
                changed = True
            if changed:
                self.save(current)

    def create(self, definition: BenchmarkDefinitionRecord) -> BenchmarkDefinitionRecord:
        path = self._definition_path(definition.benchmark_definition_id)
        if path.exists():
            raise ConflictError(
                f"Benchmark definition already exists: {definition.benchmark_definition_id}"
            )
        atomic_write_json(path, definition.model_dump(mode="json"))
        return definition

    def save(self, definition: BenchmarkDefinitionRecord) -> BenchmarkDefinitionRecord:
        path = self._definition_path(definition.benchmark_definition_id)
        definition.updated_at = now_utc()
        atomic_write_json(path, definition.model_dump(mode="json"))
        return definition

    def get(self, benchmark_definition_id: str) -> BenchmarkDefinitionRecord:
        self._ensure_seeded()
        path = self._definition_path(benchmark_definition_id)
        if not path.exists():
            raise NotFoundError(
                f"Benchmark definition not found: {benchmark_definition_id}"
            )
        with path.open("r", encoding="utf-8") as handle:
            return BenchmarkDefinitionRecord.model_validate(json.load(handle))

    def list(self) -> list[BenchmarkDefinitionRecord]:
        self._ensure_seeded()
        items: list[BenchmarkDefinitionRecord] = []
        for path in sorted(self._benchmark_definitions_root.glob("*.json")):
            with path.open("r", encoding="utf-8") as handle:
                items.append(BenchmarkDefinitionRecord.model_validate(json.load(handle)))
        return items
