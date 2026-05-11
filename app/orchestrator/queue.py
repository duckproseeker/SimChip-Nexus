from __future__ import annotations

import json
import os
import uuid
from datetime import datetime
from enum import Enum
from pathlib import Path

from pydantic import BaseModel

from app.utils.file_utils import ensure_dir


class RunCommandType(str, Enum):
    START = "START"


class RunCommand(BaseModel):
    command_id: str
    run_id: str
    command_type: RunCommandType
    created_at: datetime


class FileCommandQueue:
    def __init__(self, commands_root: Path) -> None:
        self._commands_root = ensure_dir(commands_root)

    def enqueue_start(self, run_id: str) -> RunCommand:
        command = RunCommand(
            command_id=str(uuid.uuid4()),
            run_id=run_id,
            command_type=RunCommandType.START,
            created_at=datetime.utcnow(),
        )
        filename = (
            f"{command.created_at.strftime('%Y%m%d%H%M%S%f')}_{command.command_id}.json"
        )
        path = self._commands_root / filename
        with path.open("w", encoding="utf-8") as handle:
            json.dump(command.model_dump(mode="json"), handle, indent=2)
        return command

    def count_pending(self) -> int:
        return len(list(self._commands_root.glob("*.json")))

    def pop_next(self) -> RunCommand | None:
        candidates = sorted(self._commands_root.glob("*.json"))
        for path in candidates:
            processing_path = path.with_suffix(".processing")
            try:
                os.rename(path, processing_path)
            except OSError:
                continue

            try:
                with processing_path.open("r", encoding="utf-8") as handle:
                    payload = json.load(handle)
                return RunCommand.model_validate(payload)
            finally:
                if processing_path.exists():
                    processing_path.unlink()

        return None
