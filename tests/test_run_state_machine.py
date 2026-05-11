from __future__ import annotations

import pytest

from app.core.models import RunStatus
from app.orchestrator.state_machine import (
    InvalidTransitionError,
    can_transition,
    validate_transition,
)


def test_valid_transitions() -> None:
    assert can_transition(RunStatus.CREATED, RunStatus.QUEUED)
    assert can_transition(RunStatus.QUEUED, RunStatus.STARTING)
    assert can_transition(RunStatus.RUNNING, RunStatus.STOPPING)
    assert can_transition(RunStatus.STOPPING, RunStatus.COMPLETED)


def test_invalid_transition_raises() -> None:
    with pytest.raises(InvalidTransitionError):
        validate_transition(RunStatus.CREATED, RunStatus.RUNNING)

    with pytest.raises(InvalidTransitionError):
        validate_transition(RunStatus.COMPLETED, RunStatus.RUNNING)
