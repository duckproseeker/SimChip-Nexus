from __future__ import annotations

import json
from pathlib import Path

from app.core.errors import ConflictError, NotFoundError
from app.core.models import ProjectRecord
from app.platform.catalog import build_default_projects
from app.utils.file_utils import atomic_write_json, ensure_dir
from app.utils.time_utils import now_utc

LEGACY_PROJECT_IDS = {"jetson-nano", "fudan-fpai", "rk3568"}


class ProjectStore:
    def __init__(self, projects_root: Path) -> None:
        self._projects_root = ensure_dir(projects_root)

    def _project_path(self, project_id: str) -> Path:
        return self._projects_root / f"{project_id}.json"

    def _ensure_seeded(self) -> None:
        existing_paths = {path.stem: path for path in self._projects_root.glob("*.json")}
        default_projects = build_default_projects()

        if not existing_paths:
            for project in default_projects:
                self.create(project)
            return

        if any(project_id in LEGACY_PROJECT_IDS for project_id in existing_paths):
            for legacy_project_id in LEGACY_PROJECT_IDS:
                legacy_path = self._project_path(legacy_project_id)
                if legacy_path.exists():
                    legacy_path.unlink()
            existing_paths = {path.stem: path for path in self._projects_root.glob("*.json")}

        for project in default_projects:
            if project.project_id not in existing_paths:
                self.create(project)

    def create(self, project: ProjectRecord) -> ProjectRecord:
        path = self._project_path(project.project_id)
        if path.exists():
            raise ConflictError(f"Project already exists: {project.project_id}")
        atomic_write_json(path, project.model_dump(mode="json"))
        return project

    def save(self, project: ProjectRecord) -> ProjectRecord:
        path = self._project_path(project.project_id)
        project.updated_at = now_utc()
        atomic_write_json(path, project.model_dump(mode="json"))
        return project

    def get(self, project_id: str) -> ProjectRecord:
        self._ensure_seeded()
        path = self._project_path(project_id)
        if not path.exists():
            raise NotFoundError(f"Project not found: {project_id}")
        with path.open("r", encoding="utf-8") as handle:
            return ProjectRecord.model_validate(json.load(handle))

    def list(self) -> list[ProjectRecord]:
        self._ensure_seeded()
        items: list[ProjectRecord] = []
        for path in sorted(self._projects_root.glob("*.json")):
            with path.open("r", encoding="utf-8") as handle:
                items.append(ProjectRecord.model_validate(json.load(handle)))
        return items
