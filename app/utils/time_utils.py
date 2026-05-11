from __future__ import annotations

from datetime import datetime, timezone


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def to_iso8601(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()
