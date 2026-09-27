from __future__ import annotations

import math
import time
from collections.abc import Callable
from dataclasses import dataclass

Clock = Callable[[], float]


class DeadlineBudgetExhaustedError(RuntimeError):
    """
    Indica que não existe orçamento temporal suficiente
    para iniciar outra operação.

    Não herda de TimeoutError deliberadamente:
    esgotar o orçamento total não deve disparar
    automaticamente outro retry.
    """


@dataclass(
    frozen=True,
    slots=True,
)
class DeadlineSnapshot:
    total_seconds: float
    elapsed_seconds: float
    remaining_seconds: float
    reserve_seconds: float
    usable_seconds: float
    expired: bool


class DeadlineBudget:
    """
    Orçamento monotônico para uma operação com prazo total.

    O objeto não dorme, não executa retries e não altera
    timeouts de transporte. Ele apenas responde quanto
    tempo ainda pode ser utilizado com segurança.
    """

    def __init__(
        self,
        total_seconds: float,
        *,
        reserve_seconds: float = 0.0,
        clock: Clock = time.monotonic,
    ) -> None:
        self._total_seconds = (
            self._validate_positive(
                total_seconds,
                name="total_seconds",
            )
        )

        self._reserve_seconds = (
            self._validate_non_negative(
                reserve_seconds,
                name="reserve_seconds",
            )
        )

        if (
            self._reserve_seconds
            >= self._total_seconds
        ):
            raise ValueError(
                "reserve_seconds must be smaller "
                "than total_seconds."
            )

        if not callable(clock):
            raise TypeError(
                "clock must be callable."
            )

        self._clock = clock
        self._started_at = float(
            self._clock()
        )

        if not math.isfinite(
            self._started_at
        ):
            raise ValueError(
                "clock must return a finite value."
            )

    @classmethod
    def from_milliseconds(
        cls,
        total_ms: int | float,
        *,
        reserve_ms: int | float = 0,
        clock: Clock = time.monotonic,
    ) -> DeadlineBudget:
        total = cls._validate_positive(
            total_ms,
            name="total_ms",
        )

        reserve = cls._validate_non_negative(
            reserve_ms,
            name="reserve_ms",
        )

        return cls(
            total / 1000.0,
            reserve_seconds=(
                reserve / 1000.0
            ),
            clock=clock,
        )

    @staticmethod
    def _validate_positive(
        value: int | float,
        *,
        name: str,
    ) -> float:
        parsed = float(value)

        if (
            not math.isfinite(parsed)
            or parsed <= 0
        ):
            raise ValueError(
                f"{name} must be finite and > 0."
            )

        return parsed

    @staticmethod
    def _validate_non_negative(
        value: int | float,
        *,
        name: str,
    ) -> float:
        parsed = float(value)

        if (
            not math.isfinite(parsed)
            or parsed < 0
        ):
            raise ValueError(
                f"{name} must be finite and >= 0."
            )

        return parsed

    @property
    def total_seconds(
        self,
    ) -> float:
        return self._total_seconds

    @property
    def reserve_seconds(
        self,
    ) -> float:
        return self._reserve_seconds

    @property
    def started_at(
        self,
    ) -> float:
        return self._started_at

    def elapsed_seconds(
        self,
    ) -> float:
        elapsed = (
            float(self._clock())
            - self._started_at
        )

        return max(
            0.0,
            elapsed,
        )

    def remaining_seconds(
        self,
    ) -> float:
        return max(
            0.0,
            self._total_seconds
            - self.elapsed_seconds(),
        )

    def usable_seconds(
        self,
    ) -> float:
        return max(
            0.0,
            self.remaining_seconds()
            - self._reserve_seconds,
        )

    def expired(
        self,
    ) -> bool:
        return (
            self.usable_seconds()
            <= 0.0
        )

    def snapshot(
        self,
    ) -> DeadlineSnapshot:
        elapsed = (
            self.elapsed_seconds()
        )

        remaining = max(
            0.0,
            self._total_seconds
            - elapsed,
        )

        usable = max(
            0.0,
            remaining
            - self._reserve_seconds,
        )

        return DeadlineSnapshot(
            total_seconds=(
                self._total_seconds
            ),
            elapsed_seconds=elapsed,
            remaining_seconds=remaining,
            reserve_seconds=(
                self._reserve_seconds
            ),
            usable_seconds=usable,
            expired=usable <= 0.0,
        )

    def can_start_attempt(
        self,
        *,
        minimum_attempt_seconds: float,
    ) -> bool:
        minimum = (
            self._validate_non_negative(
                minimum_attempt_seconds,
                name=(
                    "minimum_attempt_seconds"
                ),
            )
        )

        return (
            self.usable_seconds()
            >= minimum
        )

    def can_retry(
        self,
        *,
        delay_seconds: float,
        minimum_attempt_seconds: float,
    ) -> bool:
        delay = (
            self._validate_non_negative(
                delay_seconds,
                name="delay_seconds",
            )
        )

        minimum = (
            self._validate_non_negative(
                minimum_attempt_seconds,
                name=(
                    "minimum_attempt_seconds"
                ),
            )
        )

        required = (
            delay
            + minimum
        )

        return (
            self.usable_seconds()
            >= required
        )

    def clamp_timeout(
        self,
        requested_seconds: float,
        *,
        minimum_seconds: float = 0.001,
    ) -> float:
        requested = (
            self._validate_positive(
                requested_seconds,
                name="requested_seconds",
            )
        )

        minimum = (
            self._validate_positive(
                minimum_seconds,
                name="minimum_seconds",
            )
        )

        usable = (
            self.usable_seconds()
        )

        if usable < minimum:
            raise DeadlineBudgetExhaustedError(
                "Deadline budget exhausted."
            )

        return max(
            minimum,
            min(
                requested,
                usable,
            ),
        )


__all__ = [
    "DeadlineBudget",
    "DeadlineBudgetExhaustedError",
    "DeadlineSnapshot",
]
