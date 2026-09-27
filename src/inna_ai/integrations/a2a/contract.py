"""Contrato interno governado Agent-to-Agent da INNA.

Esta camada formaliza mensagens entre agentes sem substituir
o handoff, o Team Router ou a governança de execução existentes.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal, TypedDict
from uuid import uuid4

from inna_ai.agents.registry.agent_registry import AgentNotFoundError, AgentRegistry
from inna_ai.agents.supervision.handoff import HandoffRecord, create_handoff

A2A_MESSAGE_SCHEMA_VERSION = "1.0.0"

A2AMessageKind = Literal[
    "task_request",
]


class A2AMessage(TypedDict):
    """Envelope interno de comunicação entre agentes."""

    schema_version: str
    kind: A2AMessageKind

    message_id: str
    trace_id: str

    source_agent: str
    target_agent: str
    capability: str

    payload: dict[str, Any]

    created_at: str
    metadata: dict[str, Any]


@dataclass(
    frozen=True,
    slots=True,
)
class A2AGovernanceDecision:
    """Resultado da política de autorização A2A."""

    allowed: bool
    reason: str

    next_message_count: int

    requires_handoff: bool

    target_team: str | None
    target_supervisor: str | None


def _utc_now() -> str:
    return datetime.now(
        UTC
    ).isoformat()


def _required_text(
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


def _non_negative_int(
    value: Any,
) -> int | None:
    try:
        normalized = int(value)
    except (
        TypeError,
        ValueError,
    ):
        return None

    if normalized < 0:
        return None

    return normalized


def create_a2a_message(
    *,
    source_agent: str,
    target_agent: str,
    capability: str,
    payload: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
    message_id: str | None = None,
    trace_id: str | None = None,
    timestamp: str | None = None,
) -> A2AMessage:
    """Cria envelope A2A sem executar ou autorizar a rota."""

    normalized_source = _required_text(
        source_agent,
        field_name="source_agent",
    )

    normalized_target = _required_text(
        target_agent,
        field_name="target_agent",
    )

    if normalized_source == normalized_target:
        raise ValueError(
            "Uma mensagem A2A exige agentes distintos."
        )

    normalized_capability = _required_text(
        capability,
        field_name="capability",
    )

    normalized_message_id = (
        _required_text(
            message_id,
            field_name="message_id",
        )
        if message_id is not None
        else uuid4().hex
    )

    normalized_trace_id = (
        _required_text(
            trace_id,
            field_name="trace_id",
        )
        if trace_id is not None
        else f"a2a-{uuid4().hex}"
    )

    created_at = (
        _required_text(
            timestamp,
            field_name="timestamp",
        )
        if timestamp is not None
        else _utc_now()
    )

    return {
        "schema_version": (
            A2A_MESSAGE_SCHEMA_VERSION
        ),
        "kind": "task_request",
        "message_id": normalized_message_id,
        "trace_id": normalized_trace_id,
        "source_agent": normalized_source,
        "target_agent": normalized_target,
        "capability": normalized_capability,
        "payload": dict(
            payload or {}
        ),
        "created_at": created_at,
        "metadata": dict(
            metadata or {}
        ),
    }


def _deny(
    *,
    reason: str,
    message_count: int,
) -> A2AGovernanceDecision:
    return A2AGovernanceDecision(
        allowed=False,
        reason=reason,
        next_message_count=message_count,
        requires_handoff=False,
        target_team=None,
        target_supervisor=None,
    )


def evaluate_a2a_message(
    message: A2AMessage,
    *,
    agent_registry: AgentRegistry,
    a2a_message_count: Any,
    max_a2a_messages: Any,
    handoff_count: Any,
    max_handoffs: Any,
) -> A2AGovernanceDecision:
    """Aplica identidade, capability e budgets ao A2A."""

    current_messages = _non_negative_int(
        a2a_message_count
    )

    message_limit = _non_negative_int(
        max_a2a_messages
    )

    current_handoffs = _non_negative_int(
        handoff_count
    )

    handoff_limit = _non_negative_int(
        max_handoffs
    )

    if (
        current_messages is None
        or message_limit is None
        or current_handoffs is None
        or handoff_limit is None
    ):
        return _deny(
            reason="a2a_invalid_budget",
            message_count=(
                current_messages or 0
            ),
        )

    if (
        message_limit == 0
        or current_messages >= message_limit
    ):
        return _deny(
            reason="a2a_message_budget_exceeded",
            message_count=current_messages,
        )

    if (
        handoff_limit == 0
        or current_handoffs >= handoff_limit
    ):
        return _deny(
            reason="a2a_handoff_budget_exceeded",
            message_count=current_messages,
        )

    source_id = str(
        message.get(
            "source_agent",
            "",
        )
    ).strip()

    target_id = str(
        message.get(
            "target_agent",
            "",
        )
    ).strip()

    capability = str(
        message.get(
            "capability",
            "",
        )
    ).strip()

    if (
        not source_id
        or not target_id
        or not capability
    ):
        return _deny(
            reason="a2a_invalid_message",
            message_count=current_messages,
        )

    if source_id == target_id:
        return _deny(
            reason="a2a_self_target_denied",
            message_count=current_messages,
        )

    try:
        source = agent_registry.get(
            source_id
        )

        target = agent_registry.get(
            target_id
        )

    except AgentNotFoundError:
        return _deny(
            reason="a2a_agent_not_registered",
            message_count=current_messages,
        )

    if (
        source.status != "active"
        or target.status != "active"
    ):
        return _deny(
            reason="a2a_inactive_agent",
            message_count=current_messages,
        )

    if (
        source.kind != "agent"
        or target.kind != "agent"
    ):
        return _deny(
            reason="a2a_agent_kind_denied",
            message_count=current_messages,
        )

    # Nesta primeira fase o transporte A2A utiliza o
    # handoff hierárquico já existente no LangGraph.
    if (
        source.team is None
        or source.supervisor is None
    ):
        return _deny(
            reason="a2a_source_not_handoff_routable",
            message_count=current_messages,
        )

    if (
        target.team is None
        or target.supervisor is None
    ):
        return _deny(
            reason="a2a_target_not_handoff_routable",
            message_count=current_messages,
        )

    if capability not in target.capabilities:
        return _deny(
            reason="a2a_target_capability_denied",
            message_count=current_messages,
        )

    return A2AGovernanceDecision(
        allowed=True,
        reason="a2a_route_allowed",
        next_message_count=(
            current_messages + 1
        ),
        requires_handoff=True,
        target_team=target.team,
        target_supervisor=target.supervisor,
    )


def create_handoff_from_a2a(
    message: A2AMessage,
) -> HandoffRecord:
    """Adapta uma mensagem A2A autorizada ao handoff existente."""

    metadata = dict(
        message.get(
            "metadata",
            {},
        )
    )

    metadata.update(
        {
            "source": "a2a",
            "a2a_schema_version": (
                message["schema_version"]
            ),
            "a2a_message_id": (
                message["message_id"]
            ),
            "a2a_trace_id": (
                message["trace_id"]
            ),
            "a2a_capability": (
                message["capability"]
            ),
        }
    )

    return create_handoff(
        from_agent=message[
            "source_agent"
        ],
        to_agent=message[
            "target_agent"
        ],
        reason=(
            "a2a:"
            f"{message['capability']}"
        ),
        payload=message[
            "payload"
        ],
        metadata=metadata,
    )


__all__ = [
    "A2AGovernanceDecision",
    "A2AMessage",
    "A2AMessageKind",
    "A2A_MESSAGE_SCHEMA_VERSION",
    "create_a2a_message",
    "create_handoff_from_a2a",
    "evaluate_a2a_message",
]
