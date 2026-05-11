from __future__ import annotations

import argparse
import faulthandler
import logging
import traceback

from app.core.config import get_settings
from app.core.logging import setup_logging
from app.executor.native_runtime_controller import NativeRuntimeController
from app.storage.artifact_store import ArtifactStore
from app.storage.run_store import RunStore

logger = logging.getLogger(__name__)


def _build_controller() -> NativeRuntimeController:
    settings = get_settings()
    return NativeRuntimeController(
        settings=settings,
        run_store=RunStore(settings.runs_root),
        artifact_store=ArtifactStore(settings.artifacts_root),
        heartbeat_callback=None,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run one CARLA native runtime job")
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args(argv)

    setup_logging()
    faulthandler.enable(all_threads=True)

    try:
        _build_controller().execute_run(args.run_id)
    except Exception:  # noqa: BLE001
        logger.error("Executor run worker failed:\n%s", traceback.format_exc())
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
