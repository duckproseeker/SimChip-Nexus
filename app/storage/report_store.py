from __future__ import annotations

import json
from pathlib import Path

from app.core.errors import ConflictError, NotFoundError
from app.core.models import ReportRecord
from app.utils.file_utils import atomic_write_json, ensure_dir
from app.utils.time_utils import now_utc


class ReportStore:
    def __init__(self, reports_root: Path) -> None:
        self._reports_root = ensure_dir(reports_root)

    def _report_path(self, report_id: str) -> Path:
        return self._reports_root / f"{report_id}.json"

    def create(self, report: ReportRecord) -> ReportRecord:
        path = self._report_path(report.report_id)
        if path.exists():
            raise ConflictError(f"Report already exists: {report.report_id}")
        atomic_write_json(path, report.model_dump(mode="json"))
        return report

    def save(self, report: ReportRecord) -> ReportRecord:
        path = self._report_path(report.report_id)
        report.updated_at = now_utc()
        atomic_write_json(path, report.model_dump(mode="json"))
        return report

    def get(self, report_id: str) -> ReportRecord:
        path = self._report_path(report_id)
        if not path.exists():
            raise NotFoundError(f"Report not found: {report_id}")
        with path.open("r", encoding="utf-8") as handle:
            return ReportRecord.model_validate(json.load(handle))

    def list(self) -> list[ReportRecord]:
        items: list[ReportRecord] = []
        for path in sorted(self._reports_root.glob("*.json")):
            with path.open("r", encoding="utf-8") as handle:
                items.append(ReportRecord.model_validate(json.load(handle)))
        return items
