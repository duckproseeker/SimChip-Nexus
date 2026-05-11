from __future__ import annotations

from typing import Any

from app.core.errors import NotFoundError
from app.core.models import GatewayRecord, GatewayStatus
from app.storage.artifact_store import ArtifactStore
from app.storage.gateway_store import GatewayStore
from app.utils.time_utils import now_utc, to_iso8601


def _build_device_metrics_snapshot(gateway: GatewayRecord) -> dict[str, Any]:
    snapshot = dict(gateway.metrics or {})
    snapshot["gateway_id"] = gateway.gateway_id
    snapshot["gateway_name"] = gateway.name
    snapshot["gateway_status"] = gateway.status.value
    snapshot["gateway_address"] = gateway.address
    snapshot["gateway_last_heartbeat_at_utc"] = to_iso8601(gateway.last_heartbeat_at)
    snapshot["gateway_last_seen_at_utc"] = to_iso8601(gateway.last_seen_at)
    return snapshot


class GatewayRegistry:
    """Registry for HIL gateways and their latest heartbeat state."""

    def __init__(
        self,
        gateway_store: GatewayStore,
        *,
        artifact_store: ArtifactStore | None = None,
    ) -> None:
        self._gateway_store = gateway_store
        self._artifact_store = artifact_store

    def register_gateway(
        self,
        gateway_id: str,
        name: str,
        capabilities: dict,
        agent_version: str | None = None,
        address: str | None = None,
    ) -> GatewayRecord:
        now = now_utc()

        try:
            gateway = self._gateway_store.get(gateway_id)
            gateway.name = name
            gateway.capabilities = capabilities
            gateway.agent_version = agent_version
            gateway.address = address
            gateway.last_seen_at = now
            return self._gateway_store.save(gateway)
        except NotFoundError:
            gateway = GatewayRecord(
                gateway_id=gateway_id,
                name=name,
                status=GatewayStatus.UNKNOWN,
                capabilities=capabilities,
                agent_version=agent_version,
                address=address,
                last_seen_at=now,
                created_at=now,
                updated_at=now,
            )
            return self._gateway_store.create_or_update(gateway)

    def record_heartbeat(
        self,
        gateway_id: str,
        status: str,
        metrics: dict,
        current_run_id: str | None = None,
    ) -> GatewayRecord:
        gateway_status = GatewayStatus(status)
        now = now_utc()

        def _apply(gateway: GatewayRecord) -> GatewayRecord:
            gateway.status = gateway_status
            gateway.metrics = metrics
            gateway.current_run_id = current_run_id
            gateway.last_heartbeat_at = now
            gateway.last_seen_at = now
            return gateway

        gateway = self._gateway_store.update(gateway_id, _apply)

        normalized_run_id = str(current_run_id or "").strip()
        if (
            normalized_run_id
            and self._artifact_store is not None
            and self._artifact_store.run_dir(normalized_run_id).exists()
        ):
            self._artifact_store.write_device_metrics(
                normalized_run_id,
                _build_device_metrics_snapshot(gateway),
            )

        return gateway

    def list_gateways(self) -> list[GatewayRecord]:
        gateways = self._gateway_store.list()
        return sorted(gateways, key=lambda item: item.updated_at, reverse=True)

    def get_gateway(self, gateway_id: str) -> GatewayRecord:
        return self._gateway_store.get(gateway_id)
