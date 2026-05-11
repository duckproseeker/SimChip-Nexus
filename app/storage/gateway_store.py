from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

from app.core.errors import NotFoundError
from app.core.models import GatewayRecord
from app.utils.file_utils import atomic_write_json, ensure_dir
from app.utils.time_utils import now_utc

GatewayUpdater = Callable[[GatewayRecord], GatewayRecord]


class GatewayStore:
    """File-based persistence for HIL gateway records."""

    def __init__(self, gateways_root: Path) -> None:
        self._gateways_root = ensure_dir(gateways_root)

    def _gateway_path(self, gateway_id: str) -> Path:
        return self._gateways_root / f"{gateway_id}.json"

    def get(self, gateway_id: str) -> GatewayRecord:
        path = self._gateway_path(gateway_id)
        if not path.exists():
            raise NotFoundError(f"Gateway not found: {gateway_id}")

        try:
            with path.open("r", encoding="utf-8") as handle:
                payload = json.load(handle)
        except json.JSONDecodeError as exc:
            raise NotFoundError(f"Gateway not found: {gateway_id}") from exc
        return GatewayRecord.model_validate(payload)

    def list(self) -> list[GatewayRecord]:
        gateways: list[GatewayRecord] = []
        for path in sorted(self._gateways_root.glob("*.json")):
            try:
                with path.open("r", encoding="utf-8") as handle:
                    payload = json.load(handle)
            except json.JSONDecodeError:
                continue
            gateways.append(GatewayRecord.model_validate(payload))
        return gateways

    def save(self, gateway: GatewayRecord) -> GatewayRecord:
        path = self._gateway_path(gateway.gateway_id)
        gateway.updated_at = now_utc()
        atomic_write_json(path, gateway.model_dump(mode="json"))
        return gateway

    def create_or_update(self, gateway: GatewayRecord) -> GatewayRecord:
        return self.save(gateway)

    def update(self, gateway_id: str, updater: GatewayUpdater) -> GatewayRecord:
        gateway = self.get(gateway_id)
        updated = updater(gateway)
        return self.save(updated)
