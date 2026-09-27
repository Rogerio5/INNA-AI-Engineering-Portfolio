from __future__ import annotations

import threading
from dataclasses import dataclass, field
from enum import StrEnum

from inna_ai.resilience.contracts import ResiliencePolicy


class CircuitState(StrEnum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass(frozen=True, slots=True)
class CircuitBreakerSnapshot:
    state: CircuitState
    consecutive_failures: int
    opened_at: float | None
    half_open_probe_in_flight: bool


@dataclass(slots=True)
class CircuitBreaker:
    failure_threshold: int
    recovery_seconds: float

    _state: CircuitState = field(
        default=CircuitState.CLOSED,
        init=False,
    )

    _consecutive_failures: int = field(
        default=0,
        init=False,
    )

    _opened_at: float | None = field(
        default=None,
        init=False,
    )

    _half_open_probe_in_flight: bool = field(
        default=False,
        init=False,
    )

    _lock: threading.RLock = field(
        default_factory=threading.RLock,
        init=False,
        repr=False,
    )

    def __post_init__(self) -> None:
        if self.failure_threshold < 1:
            raise ValueError(
                "failure_threshold must be >= 1."
            )

        if self.recovery_seconds < 0:
            raise ValueError(
                "recovery_seconds must be >= 0."
            )

    def snapshot(
        self,
    ) -> CircuitBreakerSnapshot:
        with self._lock:
            return CircuitBreakerSnapshot(
                state=self._state,
                consecutive_failures=(
                    self._consecutive_failures
                ),
                opened_at=self._opened_at,
                half_open_probe_in_flight=(
                    self._half_open_probe_in_flight
                ),
            )

    def acquire_permission(
        self,
        *,
        now: float,
    ) -> bool:
        now = float(now)

        with self._lock:
            if (
                self._state
                is CircuitState.CLOSED
            ):
                return True

            if (
                self._state
                is CircuitState.OPEN
            ):
                if self._opened_at is None:
                    return False

                elapsed = (
                    now
                    - self._opened_at
                )

                if (
                    elapsed
                    < self.recovery_seconds
                ):
                    return False

                self._state = (
                    CircuitState.HALF_OPEN
                )

                self._half_open_probe_in_flight = (
                    False
                )

            if (
                self._state
                is CircuitState.HALF_OPEN
            ):
                if (
                    self._half_open_probe_in_flight
                ):
                    return False

                self._half_open_probe_in_flight = (
                    True
                )

                return True

            return False

    def record_success(
        self,
    ) -> None:
        with self._lock:
            self._close()

    def record_non_circuit_outcome(
        self,
    ) -> None:
        with self._lock:
            self._close()

    def record_failure(
        self,
        *,
        now: float,
    ) -> None:
        now = float(now)

        with self._lock:
            if (
                self._state
                is CircuitState.HALF_OPEN
            ):
                self._open(
                    now=now
                )
                return

            if (
                self._state
                is CircuitState.OPEN
            ):
                return

            self._consecutive_failures += 1

            if (
                self._consecutive_failures
                >= self.failure_threshold
            ):
                self._open(
                    now=now
                )

    def _open(
        self,
        *,
        now: float,
    ) -> None:
        self._state = CircuitState.OPEN
        self._opened_at = float(now)
        self._half_open_probe_in_flight = (
            False
        )

    def _close(
        self,
    ) -> None:
        self._state = CircuitState.CLOSED
        self._consecutive_failures = 0
        self._opened_at = None
        self._half_open_probe_in_flight = (
            False
        )


class CircuitBreakerRegistry:
    def __init__(
        self,
    ) -> None:
        self._lock = threading.RLock()

        self._breakers: dict[
            str,
            CircuitBreaker,
        ] = {}

        self._signatures: dict[
            str,
            tuple[int, float],
        ] = {}

    def get_or_create(
        self,
        policy: ResiliencePolicy,
    ) -> CircuitBreaker:
        signature = (
            policy.circuit_failure_threshold,
            float(
                policy.circuit_recovery_seconds
            ),
        )

        with self._lock:
            existing = self._breakers.get(
                policy.name
            )

            if existing is not None:
                if (
                    self._signatures[
                        policy.name
                    ]
                    != signature
                ):
                    raise ValueError(
                        "Circuit policy changed for "
                        f"registered operation: "
                        f"{policy.name}"
                    )

                return existing

            breaker = CircuitBreaker(
                failure_threshold=(
                    policy.circuit_failure_threshold
                ),
                recovery_seconds=(
                    policy.circuit_recovery_seconds
                ),
            )

            self._breakers[
                policy.name
            ] = breaker

            self._signatures[
                policy.name
            ] = signature

            return breaker

    def clear(
        self,
    ) -> None:
        with self._lock:
            self._breakers.clear()
            self._signatures.clear()
