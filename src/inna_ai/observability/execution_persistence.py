"""Sink seguro de execuções LangGraph do portfólio."""

from __future__ import annotations

from collections import deque
from typing import Any


_EVENTS: deque[dict[str, Any]] = (
    deque(maxlen=1000)
)

_ALLOWED_FIELDS = {
    "execution_mode",
    "thread_id_hash",
    "trace_id",
    "status",
    "duration_ms",
    "execution_steps",
    "handoff_count",
    "human_review_count",
}


def persist_langgraph_execution(
    *args: Any,
    **kwargs: Any,
) -> bool:
    """
    Registra metadados operacionais em memória.

    Não persiste prompt, resposta, conteúdo financeiro,
    credenciais ou dados pessoais.
    """
    safe = {
        key: value
        for key, value
        in kwargs.items()
        if key in _ALLOWED_FIELDS
    }

    safe["positional_arguments"] = len(
        args
    )

    _EVENTS.append(
        safe
    )

    return True


def get_execution_persistence_snapshot(
) -> tuple[dict[str, Any], ...]:
    return tuple(
        dict(item)
        for item in _EVENTS
    )


__all__ = [
    "persist_langgraph_execution",
    "get_execution_persistence_snapshot",
]
