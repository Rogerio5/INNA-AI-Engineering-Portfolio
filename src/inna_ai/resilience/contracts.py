from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import StrEnum


class OperationKind(StrEnum):
    READ_ONLY = "read_only"
    IDEMPOTENT = "idempotent"
    SIDE_EFFECT = "side_effect"


class FailureKind(StrEnum):
    TIMEOUT = "timeout"
    RATE_LIMIT = "rate_limit"
    TRANSIENT_NETWORK = "transient_network"
    UPSTREAM_5XX = "upstream_5xx"

    AUTHENTICATION = "authentication"
    AUTHORIZATION = "authorization"
    INVALID_REQUEST = "invalid_request"
    VALIDATION = "validation"
    CONFIGURATION = "configuration"
    CANCELLED = "cancelled"

    UNKNOWN = "unknown"


DEFAULT_RETRYABLE_FAILURES = frozenset(
    {
        FailureKind.TIMEOUT,
        FailureKind.RATE_LIMIT,
        FailureKind.TRANSIENT_NETWORK,
        FailureKind.UPSTREAM_5XX,
    }
)

DEFAULT_CIRCUIT_FAILURES = frozenset(
    {
        FailureKind.TIMEOUT,
        FailureKind.RATE_LIMIT,
        FailureKind.TRANSIENT_NETWORK,
        FailureKind.UPSTREAM_5XX,
    }
)


@dataclass(frozen=True, slots=True)
class ResiliencePolicy:
    name: str
    operation_kind: OperationKind

    max_attempts: int = 3

    base_delay_seconds: float = 0.25
    max_delay_seconds: float = 2.0
    jitter_ratio: float = 0.20

    circuit_failure_threshold: int = 5
    circuit_recovery_seconds: float = 30.0

    retryable_failures: frozenset[FailureKind] = field(
        default_factory=lambda: DEFAULT_RETRYABLE_FAILURES
    )

    circuit_failure_kinds: frozenset[FailureKind] = field(
        default_factory=lambda: DEFAULT_CIRCUIT_FAILURES
    )

    def __post_init__(self) -> None:
        normalized_name = str(self.name or "").strip()

        if not normalized_name:
            raise ValueError(
                "ResiliencePolicy.name must not be empty."
            )

        if self.max_attempts < 1:
            raise ValueError(
                "max_attempts must be >= 1."
            )

        numeric_values = {
            "base_delay_seconds": self.base_delay_seconds,
            "max_delay_seconds": self.max_delay_seconds,
            "jitter_ratio": self.jitter_ratio,
            "circuit_recovery_seconds": (
                self.circuit_recovery_seconds
            ),
        }

        for field_name, value in numeric_values.items():
            if not math.isfinite(float(value)):
                raise ValueError(
                    f"{field_name} must be finite."
                )

            if float(value) < 0:
                raise ValueError(
                    f"{field_name} must be >= 0."
                )

        if (
            self.max_delay_seconds
            < self.base_delay_seconds
        ):
            raise ValueError(
                "max_delay_seconds must be >= "
                "base_delay_seconds."
            )

        if not 0 <= self.jitter_ratio <= 1:
            raise ValueError(
                "jitter_ratio must be between 0 and 1."
            )

        if self.circuit_failure_threshold < 1:
            raise ValueError(
                "circuit_failure_threshold must be >= 1."
            )

    def allows_retry(
        self,
        *,
        failure_kind: FailureKind,
        attempt_number: int,
    ) -> bool:
        if attempt_number < 1:
            return False

        if (
            self.operation_kind
            is OperationKind.SIDE_EFFECT
        ):
            return False

        if (
            failure_kind
            not in self.retryable_failures
        ):
            return False

        return attempt_number < self.max_attempts

    def counts_toward_circuit(
        self,
        failure_kind: FailureKind,
    ) -> bool:
        return (
            failure_kind
            in self.circuit_failure_kinds
        )
