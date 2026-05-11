from __future__ import annotations

from pathlib import Path

from app.scenario.descriptor import ScenarioDescriptor


class RecorderManager:
    def __init__(self) -> None:
        self._active = False
        self._output_path: Path | None = None

    @property
    def output_path(self) -> Path | None:
        return self._output_path

    def start(
        self,
        run_id: str,
        descriptor: ScenarioDescriptor,
        carla_client: object,
        run_dir: Path,
    ) -> None:
        self._active = False
        self._output_path = None

        if not descriptor.recorder.enabled:
            return

        recorder_path = run_dir / "recorder" / f"{run_id}.log"
        carla_client.start_recorder(recorder_path)
        self._output_path = recorder_path
        self._active = True

    def stop(self, carla_client: object) -> None:
        if not self._active:
            return
        carla_client.stop_recorder()
        self._active = False
