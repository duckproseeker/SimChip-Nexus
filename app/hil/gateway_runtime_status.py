from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.core.config import Settings
from app.core.models import GatewayRecord
from app.hil.pi_gateway_runtime import probe_pi_gateway


def gateway_matches_configured_pi(gateway: GatewayRecord, settings: Settings) -> bool:
    configured_host = (settings.duckpark_pi_host or "").strip()
    gateway_address = (gateway.address or "").strip()
    return bool(configured_host and gateway_address and configured_host == gateway_address)


def heartbeat_age_seconds(
    gateway: GatewayRecord,
    *,
    checked_at: datetime | None = None,
) -> float | None:
    if gateway.last_heartbeat_at is None:
        return None

    reference = checked_at or datetime.now(timezone.utc)
    return (
        reference.astimezone(timezone.utc) - gateway.last_heartbeat_at.astimezone(timezone.utc)
    ).total_seconds()


def resolve_gateway_status(
    gateway: GatewayRecord,
    settings: Settings,
    *,
    checked_at: datetime | None = None,
    pi_gateway_status: dict[str, Any] | None = None,
) -> tuple[str, float | None, str | None]:
    age_seconds = heartbeat_age_seconds(gateway, checked_at=checked_at)
    raw_status = gateway.status.value

    if age_seconds is None:
        return "OFFLINE", None, "gateway heartbeat missing"

    if age_seconds <= settings.hil_gateway_stale_seconds:
        return raw_status, age_seconds, None

    if gateway_matches_configured_pi(gateway, settings):
        runtime_status = pi_gateway_status or probe_pi_gateway(settings)
        if runtime_status.get("reachable"):
            return "DEGRADED", age_seconds, "Pi chain reachable but gateway heartbeat is stale"

    return "OFFLINE", age_seconds, "gateway heartbeat is stale"
