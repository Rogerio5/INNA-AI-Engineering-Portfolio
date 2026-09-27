from __future__ import annotations

import asyncio
import math
import random
import time
from collections.abc import (
    Awaitable,
    Callable,
)
from typing import TypeVar

from inna_ai.resilience.backoff import RandomSource, calculate_backoff_seconds
from inna_ai.resilience.circuit_breaker import CircuitBreaker, CircuitBreakerRegistry
from inna_ai.resilience.classification import classify_failure
from inna_ai.resilience.contracts import ResiliencePolicy
from inna_ai.resilience.deadline import DeadlineBudget, DeadlineBudgetExhaustedError
from inna_ai.resilience.events import ResilienceEvent, ResilienceEventType, ResilienceObserver

T = TypeVar("T")


class CircuitOpenError(RuntimeError):
    def __init__(
        self,
        operation: str,
    ) -> None:
        self.operation = operation

        super().__init__(
            "Circuit breaker rejected operation: "
            f"{operation}"
        )


class ResilienceRuntime:
    def __init__(
        self,
        *,
        registry: CircuitBreakerRegistry | None = None,
        observer: ResilienceObserver | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
        random_source: RandomSource = random.random,
    ) -> None:
        self._registry = (
            registry
            or CircuitBreakerRegistry()
        )

        self._observer = observer
        self._clock = clock
        self._sleeper = sleeper
        self._random_source = random_source

    @property
    def registry(
        self,
    ) -> CircuitBreakerRegistry:
        return self._registry

    @staticmethod
    def _validate_minimum_retry_attempt_seconds(
        value: float,
    ) -> float:
        parsed = float(value)

        if (
            not math.isfinite(parsed)
            or parsed < 0
        ):
            raise ValueError(
                "minimum_retry_attempt_seconds "
                "must be finite and >= 0."
            )

        return parsed

    @staticmethod
    def _ensure_initial_deadline_budget(
        *,
        deadline_budget: DeadlineBudget | None,
        minimum_attempt_seconds: float,
    ) -> None:
        if deadline_budget is None:
            return

        if deadline_budget.expired():
            raise DeadlineBudgetExhaustedError(
                "Insufficient deadline budget "
                "for initial attempt."
            )

        if deadline_budget.can_start_attempt(
            minimum_attempt_seconds=(
                minimum_attempt_seconds
            ),
        ):
            return

        raise DeadlineBudgetExhaustedError(
            "Insufficient deadline budget "
            "for initial attempt."
        )

    @staticmethod
    def _ensure_retry_deadline_budget(
        *,
        deadline_budget: DeadlineBudget | None,
        delay_seconds: float,
        minimum_attempt_seconds: float,
    ) -> None:
        if deadline_budget is None:
            return

        if deadline_budget.can_retry(
            delay_seconds=delay_seconds,
            minimum_attempt_seconds=(
                minimum_attempt_seconds
            ),
        ):
            return

        raise DeadlineBudgetExhaustedError(
            "Insufficient deadline budget "
            "for retry."
        )

    def execute(
        self,
        *,
        policy: ResiliencePolicy,
        operation: Callable[[], T],
        deadline_budget: DeadlineBudget | None = None,
        minimum_retry_attempt_seconds: float = 0.0,
    ) -> T:
        minimum_retry_attempt_seconds = (
            self._validate_minimum_retry_attempt_seconds(
                minimum_retry_attempt_seconds
            )
        )

        self._ensure_initial_deadline_budget(
            deadline_budget=deadline_budget,
            minimum_attempt_seconds=(
                minimum_retry_attempt_seconds
            ),
        )

        breaker = (
            self._registry.get_or_create(
                policy
            )
        )

        started_at = self._clock()
        attempt_number = 1

        while True:
            self._ensure_circuit_permission(
                policy=policy,
                breaker=breaker,
                attempt_number=attempt_number,
                started_at=started_at,
            )

            self._emit(
                ResilienceEvent(
                    operation=policy.name,
                    event_type=(
                        ResilienceEventType
                        .ATTEMPT_STARTED
                    ),
                    attempt_number=(
                        attempt_number
                    ),
                    max_attempts=(
                        policy.max_attempts
                    ),
                    circuit_state=(
                        breaker
                        .snapshot()
                        .state
                        .value
                    ),
                    elapsed_ms=self._elapsed_ms(
                        started_at
                    ),
                )
            )

            try:
                result = operation()

            except Exception as exc:
                failure_kind = (
                    classify_failure(
                        exc
                    )
                )

                self._record_failure_outcome(
                    breaker=breaker,
                    policy=policy,
                    failure_kind=(
                        failure_kind
                    ),
                )

                snapshot = (
                    breaker.snapshot()
                )

                self._emit(
                    ResilienceEvent(
                        operation=policy.name,
                        event_type=(
                            ResilienceEventType
                            .ATTEMPT_FAILED
                        ),
                        attempt_number=(
                            attempt_number
                        ),
                        max_attempts=(
                            policy.max_attempts
                        ),
                        failure_kind=(
                            failure_kind
                        ),
                        error_type=(
                            type(exc).__name__
                        ),
                        circuit_state=(
                            snapshot.state.value
                        ),
                        elapsed_ms=(
                            self._elapsed_ms(
                                started_at
                            )
                        ),
                    )
                )

                if not policy.allows_retry(
                    failure_kind=(
                        failure_kind
                    ),
                    attempt_number=(
                        attempt_number
                    ),
                ):
                    self._emit(
                        ResilienceEvent(
                            operation=(
                                policy.name
                            ),
                            event_type=(
                                ResilienceEventType
                                .OPERATION_FAILED
                            ),
                            attempt_number=(
                                attempt_number
                            ),
                            max_attempts=(
                                policy.max_attempts
                            ),
                            failure_kind=(
                                failure_kind
                            ),
                            error_type=(
                                type(exc).__name__
                            ),
                            circuit_state=(
                                snapshot
                                .state
                                .value
                            ),
                            elapsed_ms=(
                                self._elapsed_ms(
                                    started_at
                                )
                            ),
                        )
                    )

                    raise

                delay = (
                    calculate_backoff_seconds(
                        retry_number=(
                            attempt_number
                        ),
                        base_delay_seconds=(
                            policy
                            .base_delay_seconds
                        ),
                        max_delay_seconds=(
                            policy
                            .max_delay_seconds
                        ),
                        jitter_ratio=(
                            policy.jitter_ratio
                        ),
                        random_source=(
                            self._random_source
                        ),
                    )
                )

                self._ensure_retry_deadline_budget(
                    deadline_budget=deadline_budget,
                    delay_seconds=delay,
                    minimum_attempt_seconds=(
                        minimum_retry_attempt_seconds
                    ),
                )

                self._emit(
                    ResilienceEvent(
                        operation=policy.name,
                        event_type=(
                            ResilienceEventType
                            .RETRY_SCHEDULED
                        ),
                        attempt_number=(
                            attempt_number
                        ),
                        max_attempts=(
                            policy.max_attempts
                        ),
                        failure_kind=(
                            failure_kind
                        ),
                        error_type=(
                            type(exc).__name__
                        ),
                        delay_seconds=delay,
                        circuit_state=(
                            snapshot.state.value
                        ),
                        elapsed_ms=(
                            self._elapsed_ms(
                                started_at
                            )
                        ),
                    )
                )

                self._sleeper(
                    delay
                )

                attempt_number += 1
                continue

            breaker.record_success()

            self._emit(
                ResilienceEvent(
                    operation=policy.name,
                    event_type=(
                        ResilienceEventType
                        .OPERATION_SUCCEEDED
                    ),
                    attempt_number=(
                        attempt_number
                    ),
                    max_attempts=(
                        policy.max_attempts
                    ),
                    circuit_state=(
                        breaker
                        .snapshot()
                        .state
                        .value
                    ),
                    elapsed_ms=(
                        self._elapsed_ms(
                            started_at
                        )
                    ),
                )
            )

            return result

    async def execute_async(
        self,
        *,
        policy: ResiliencePolicy,
        operation: Callable[
            [],
            Awaitable[T],
        ],
        sleeper: Callable[
            [float],
            Awaitable[None],
        ] = asyncio.sleep,
        deadline_budget: DeadlineBudget | None = None,
        minimum_retry_attempt_seconds: float = 0.0,
    ) -> T:
        minimum_retry_attempt_seconds = (
            self._validate_minimum_retry_attempt_seconds(
                minimum_retry_attempt_seconds
            )
        )

        self._ensure_initial_deadline_budget(
            deadline_budget=deadline_budget,
            minimum_attempt_seconds=(
                minimum_retry_attempt_seconds
            ),
        )

        breaker = (
            self._registry.get_or_create(
                policy
            )
        )

        started_at = self._clock()
        attempt_number = 1

        while True:
            self._ensure_circuit_permission(
                policy=policy,
                breaker=breaker,
                attempt_number=attempt_number,
                started_at=started_at,
            )

            self._emit(
                ResilienceEvent(
                    operation=policy.name,
                    event_type=(
                        ResilienceEventType
                        .ATTEMPT_STARTED
                    ),
                    attempt_number=(
                        attempt_number
                    ),
                    max_attempts=(
                        policy.max_attempts
                    ),
                    circuit_state=(
                        breaker
                        .snapshot()
                        .state
                        .value
                    ),
                    elapsed_ms=self._elapsed_ms(
                        started_at
                    ),
                )
            )

            try:
                result = await operation()

            except asyncio.CancelledError:
                breaker.record_non_circuit_outcome()
                raise

            except Exception as exc:
                failure_kind = (
                    classify_failure(
                        exc
                    )
                )

                self._record_failure_outcome(
                    breaker=breaker,
                    policy=policy,
                    failure_kind=(
                        failure_kind
                    ),
                )

                snapshot = (
                    breaker.snapshot()
                )

                self._emit(
                    ResilienceEvent(
                        operation=policy.name,
                        event_type=(
                            ResilienceEventType
                            .ATTEMPT_FAILED
                        ),
                        attempt_number=(
                            attempt_number
                        ),
                        max_attempts=(
                            policy.max_attempts
                        ),
                        failure_kind=(
                            failure_kind
                        ),
                        error_type=(
                            type(exc).__name__
                        ),
                        circuit_state=(
                            snapshot.state.value
                        ),
                        elapsed_ms=(
                            self._elapsed_ms(
                                started_at
                            )
                        ),
                    )
                )

                if not policy.allows_retry(
                    failure_kind=(
                        failure_kind
                    ),
                    attempt_number=(
                        attempt_number
                    ),
                ):
                    self._emit(
                        ResilienceEvent(
                            operation=(
                                policy.name
                            ),
                            event_type=(
                                ResilienceEventType
                                .OPERATION_FAILED
                            ),
                            attempt_number=(
                                attempt_number
                            ),
                            max_attempts=(
                                policy.max_attempts
                            ),
                            failure_kind=(
                                failure_kind
                            ),
                            error_type=(
                                type(exc).__name__
                            ),
                            circuit_state=(
                                snapshot
                                .state
                                .value
                            ),
                            elapsed_ms=(
                                self._elapsed_ms(
                                    started_at
                                )
                            ),
                        )
                    )

                    raise

                delay = (
                    calculate_backoff_seconds(
                        retry_number=(
                            attempt_number
                        ),
                        base_delay_seconds=(
                            policy
                            .base_delay_seconds
                        ),
                        max_delay_seconds=(
                            policy
                            .max_delay_seconds
                        ),
                        jitter_ratio=(
                            policy.jitter_ratio
                        ),
                        random_source=(
                            self._random_source
                        ),
                    )
                )

                self._ensure_retry_deadline_budget(
                    deadline_budget=deadline_budget,
                    delay_seconds=delay,
                    minimum_attempt_seconds=(
                        minimum_retry_attempt_seconds
                    ),
                )

                self._emit(
                    ResilienceEvent(
                        operation=policy.name,
                        event_type=(
                            ResilienceEventType
                            .RETRY_SCHEDULED
                        ),
                        attempt_number=(
                            attempt_number
                        ),
                        max_attempts=(
                            policy.max_attempts
                        ),
                        failure_kind=(
                            failure_kind
                        ),
                        error_type=(
                            type(exc).__name__
                        ),
                        delay_seconds=delay,
                        circuit_state=(
                            snapshot.state.value
                        ),
                        elapsed_ms=(
                            self._elapsed_ms(
                                started_at
                            )
                        ),
                    )
                )

                await sleeper(
                    delay
                )

                attempt_number += 1
                continue

            breaker.record_success()

            self._emit(
                ResilienceEvent(
                    operation=policy.name,
                    event_type=(
                        ResilienceEventType
                        .OPERATION_SUCCEEDED
                    ),
                    attempt_number=(
                        attempt_number
                    ),
                    max_attempts=(
                        policy.max_attempts
                    ),
                    circuit_state=(
                        breaker
                        .snapshot()
                        .state
                        .value
                    ),
                    elapsed_ms=(
                        self._elapsed_ms(
                            started_at
                        )
                    ),
                )
            )

            return result

    def _record_failure_outcome(
        self,
        *,
        breaker: CircuitBreaker,
        policy: ResiliencePolicy,
        failure_kind,
    ) -> None:
        if policy.counts_toward_circuit(
            failure_kind
        ):
            breaker.record_failure(
                now=self._clock()
            )
            return

        breaker.record_non_circuit_outcome()

    def _ensure_circuit_permission(
        self,
        *,
        policy: ResiliencePolicy,
        breaker: CircuitBreaker,
        attempt_number: int,
        started_at: float,
    ) -> None:
        if breaker.acquire_permission(
            now=self._clock()
        ):
            return

        snapshot = (
            breaker.snapshot()
        )

        self._emit(
            ResilienceEvent(
                operation=policy.name,
                event_type=(
                    ResilienceEventType
                    .CIRCUIT_REJECTED
                ),
                attempt_number=(
                    attempt_number
                ),
                max_attempts=(
                    policy.max_attempts
                ),
                circuit_state=(
                    snapshot.state.value
                ),
                elapsed_ms=(
                    self._elapsed_ms(
                        started_at
                    )
                ),
            )
        )

        raise CircuitOpenError(
            policy.name
        )

    def _elapsed_ms(
        self,
        started_at: float,
    ) -> float:
        return max(
            0.0,
            (
                self._clock()
                - started_at
            )
            * 1000.0,
        )

    def _emit(
        self,
        event: ResilienceEvent,
    ) -> None:
        if self._observer is None:
            return

        try:
            self._observer(
                event
            )
        except Exception:
            # Observabilidade nunca pode derrubar
            # o caminho funcional da aplicação.
            return
