"""
Contrato formal de handoffs entre agentes da INNA.

Um handoff representa a transferência explícita e
rastreável de responsabilidade entre dois agentes.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal, TypedDict
from uuid import uuid4


HandoffStatus = Literal[
    "requested",
    "accepted",
    "completed",
    "rejected",
    "cancelled",
    "failed",
]


class HandoffRecord(TypedDict):
    handoff_id: str
    from_agent: str
    to_agent: str
    reason: str
    payload: dict[str, Any]
    status: HandoffStatus

    created_at: str
    updated_at: str
    accepted_at: str | None
    completed_at: str | None

    result: dict[str, Any]
    error: str
    metadata: dict[str, Any]


_ALLOWED_TRANSITIONS: dict[
    HandoffStatus,
    set[HandoffStatus],
] = {
    "requested": {
        "accepted",
        "rejected",
        "cancelled",
        "failed",
    },
    "accepted": {
        "completed",
        "cancelled",
        "failed",
    },
    "completed": set(),
    "rejected": set(),
    "cancelled": set(),
    "failed": set(),
}


def _utc_now() -> str:
    return datetime.now(
        timezone.utc
    ).isoformat()


def _normalize_required_text(
    value: Any,
    *,
    field_name: str,
) -> str:
    normalized = str(
        value or ""
    ).strip()

    if not normalized:
        raise ValueError(
            f"{field_name} não pode ser vazio."
        )

    return normalized


def _normalize_optional_text(
    value: Any,
) -> str:
    return str(
        value or ""
    ).strip()


def create_handoff(
    *,
    from_agent: str,
    to_agent: str,
    reason: str,
    payload: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
    handoff_id: str | None = None,
    timestamp: str | None = None,
) -> HandoffRecord:
    """
    Cria uma solicitação explícita de handoff.
    """
    normalized_from = (
        _normalize_required_text(
            from_agent,
            field_name="from_agent",
        )
    )

    normalized_to = (
        _normalize_required_text(
            to_agent,
            field_name="to_agent",
        )
    )

    normalized_reason = (
        _normalize_required_text(
            reason,
            field_name="reason",
        )
    )

    if normalized_from == normalized_to:
        raise ValueError(
            "Um agente não pode transferir "
            "a tarefa para ele mesmo."
        )

    normalized_id = (
        _normalize_required_text(
            handoff_id,
            field_name="handoff_id",
        )
        if handoff_id is not None
        else uuid4().hex
    )

    created_at = (
        _normalize_required_text(
            timestamp,
            field_name="timestamp",
        )
        if timestamp is not None
        else _utc_now()
    )

    return {
        "handoff_id": normalized_id,
        "from_agent": normalized_from,
        "to_agent": normalized_to,
        "reason": normalized_reason,
        "payload": dict(
            payload or {}
        ),
        "status": "requested",
        "created_at": created_at,
        "updated_at": created_at,
        "accepted_at": None,
        "completed_at": None,
        "result": {},
        "error": "",
        "metadata": dict(
            metadata or {}
        ),
    }


def transition_handoff(
    handoff: HandoffRecord,
    *,
    status: HandoffStatus,
    result: dict[str, Any] | None = None,
    error: str = "",
    timestamp: str | None = None,
) -> HandoffRecord:
    """
    Executa uma transição válida da máquina de estados.
    """
    current_status = handoff.get(
        "status"
    )

    if current_status not in (
        _ALLOWED_TRANSITIONS
    ):
        raise ValueError(
            "Status atual do handoff é inválido: "
            f"{current_status!r}."
        )

    allowed = _ALLOWED_TRANSITIONS[
        current_status
    ]

    if status not in allowed:
        raise ValueError(
            "Transição de handoff inválida: "
            f"{current_status} -> {status}."
        )

    updated_at = (
        _normalize_required_text(
            timestamp,
            field_name="timestamp",
        )
        if timestamp is not None
        else _utc_now()
    )

    updated: HandoffRecord = {
        **handoff,
        "status": status,
        "updated_at": updated_at,
        "result": dict(
            result
            if result is not None
            else handoff.get(
                "result",
                {},
            )
        ),
        "error": _normalize_optional_text(
            error
        ),
    }

    if status == "accepted":
        updated["accepted_at"] = (
            updated_at
        )

    if status == "completed":
        updated["completed_at"] = (
            updated_at
        )

    return updated


def accept_handoff(
    handoff: HandoffRecord,
    *,
    timestamp: str | None = None,
) -> HandoffRecord:
    return transition_handoff(
        handoff,
        status="accepted",
        timestamp=timestamp,
    )


def complete_handoff(
    handoff: HandoffRecord,
    *,
    result: dict[str, Any] | None = None,
    timestamp: str | None = None,
) -> HandoffRecord:
    return transition_handoff(
        handoff,
        status="completed",
        result=result,
        timestamp=timestamp,
    )


def reject_handoff(
    handoff: HandoffRecord,
    *,
    reason: str,
    timestamp: str | None = None,
) -> HandoffRecord:
    return transition_handoff(
        handoff,
        status="rejected",
        error=_normalize_required_text(
            reason,
            field_name="reason",
        ),
        timestamp=timestamp,
    )


def fail_handoff(
    handoff: HandoffRecord,
    *,
    error: str,
    timestamp: str | None = None,
) -> HandoffRecord:
    return transition_handoff(
        handoff,
        status="failed",
        error=_normalize_required_text(
            error,
            field_name="error",
        ),
        timestamp=timestamp,
    )


def cancel_handoff(
    handoff: HandoffRecord,
    *,
    reason: str = "",
    timestamp: str | None = None,
) -> HandoffRecord:
    return transition_handoff(
        handoff,
        status="cancelled",
        error=_normalize_optional_text(
            reason
        ),
        timestamp=timestamp,
    )


__all__ = [
    "HandoffRecord",
    "HandoffStatus",
    "accept_handoff",
    "cancel_handoff",
    "complete_handoff",
    "create_handoff",
    "fail_handoff",
    "reject_handoff",
    "transition_handoff",
]
