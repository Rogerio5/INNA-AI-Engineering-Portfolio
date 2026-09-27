"""Sink de reliability enxuto do portfólio."""

from __future__ import annotations

from collections import deque
from typing import Any


_EVENTS: deque[Any] = deque(
    maxlen=2000
)

_PERSISTENCE_EVENTS: deque[Any] = (
    deque(maxlen=2000)
)


def observe_production_reliability_event(
    event: Any,
) -> bool:
    """
    Registra o evento em memória para observação
    local e testes do portfólio.
    """
    _EVENTS.append(
        event
    )

    return True


def observe_production_reliability_persistence_event(
    event: Any,
) -> bool:
    """
    Adapter em memória para a superfície de
    persistência de eventos de reliability.
    """
    _PERSISTENCE_EVENTS.append(
        event
    )

    return True


def reliability_snapshot(
) -> dict[str, int]:
    return {
        "events": len(
            _EVENTS
        ),
        "persistence_events": len(
            _PERSISTENCE_EVENTS
        ),
    }


__all__ = [
    "observe_production_reliability_event",
    "observe_production_reliability_persistence_event",
    "reliability_snapshot",
]
