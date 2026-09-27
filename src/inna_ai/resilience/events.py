from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from uuid import uuid4

from inna_ai.resilience.contracts import FailureKind


def _new_resilience_event_id() -> str:
    """Identidade técnica sem conteúdo sensível."""
    return uuid4().hex


def _utc_now() -> datetime:
    """Timestamp UTC timezone-aware do evento."""
    return datetime.now(UTC)


class ResilienceEventType(StrEnum):
    ATTEMPT_STARTED = "attempt_started"
    ATTEMPT_FAILED = "attempt_failed"
    RETRY_SCHEDULED = "retry_scheduled"
    OPERATION_SUCCEEDED = "operation_succeeded"
    OPERATION_FAILED = "operation_failed"
    CIRCUIT_REJECTED = "circuit_rejected"


@dataclass(frozen=True, slots=True)
class ResilienceEvent:
    operation: str
    event_type: ResilienceEventType
    attempt_number: int
    max_attempts: int

    event_id: str = field(
        default_factory=_new_resilience_event_id
    )
    occurred_at: datetime = field(
        default_factory=_utc_now
    )

    failure_kind: FailureKind | None = None
    error_type: str | None = None

    delay_seconds: float | None = None
    circuit_state: str | None = None
    elapsed_ms: float | None = None


    def __post_init__(self) -> None:
        event_id = str(
            self.event_id
        ).strip()

        if (
            not event_id
            or len(event_id) > 128
        ):
            raise ValueError(
                "event_id must be non-empty "
                "and <= 128 characters."
            )

        occurred_at = self.occurred_at

        if (
            not isinstance(
                occurred_at,
                datetime,
            )
            or occurred_at.tzinfo is None
            or occurred_at.utcoffset()
            is None
        ):
            raise ValueError(
                "occurred_at must be "
                "timezone-aware."
            )

        object.__setattr__(
            self,
            "event_id",
            event_id,
        )

        object.__setattr__(
            self,
            "occurred_at",
            occurred_at.astimezone(
                UTC
            ),
        )


ResilienceObserver = Callable[
    [ResilienceEvent],
    None,
]
