from __future__ import annotations

from app.core.models import RunStatus

ALLOWED_TRANSITIONS: dict[RunStatus, set[RunStatus]] = {
    RunStatus.CREATED: {RunStatus.QUEUED, RunStatus.CANCELED, RunStatus.FAILED},
    RunStatus.QUEUED: {RunStatus.STARTING, RunStatus.CANCELED, RunStatus.FAILED},
    RunStatus.STARTING: {RunStatus.RUNNING, RunStatus.STOPPING, RunStatus.FAILED},
    RunStatus.RUNNING: {
        RunStatus.PAUSED,
        RunStatus.STOPPING,
        RunStatus.COMPLETED,
        RunStatus.FAILED,
    },
    RunStatus.PAUSED: {RunStatus.RUNNING, RunStatus.STOPPING, RunStatus.FAILED},
    RunStatus.STOPPING: {RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.CANCELED},
    RunStatus.COMPLETED: set(),
    RunStatus.FAILED: set(),
    RunStatus.CANCELED: set(),
}


class InvalidTransitionError(ValueError):
    """Raised when a run state transition violates the lifecycle rules."""


def can_transition(current: RunStatus, target: RunStatus) -> bool:
    return target in ALLOWED_TRANSITIONS[current]


def validate_transition(current: RunStatus, target: RunStatus) -> None:
    if current == target:
        return
    if not can_transition(current, target):
        raise InvalidTransitionError(
            f"Invalid run state transition: {current} -> {target}"
        )
