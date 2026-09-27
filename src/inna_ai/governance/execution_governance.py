"""
Governança operacional da arquitetura multiagente da INNA.

Controla:
- orçamento de passos;
- repetição de rotas;
- detecção preventiva de loops;
- fallback seguro.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping, Sequence


DEFAULT_MAX_EXECUTION_STEPS = 8
DEFAULT_MAX_SAME_AGENT_VISITS = 2

SAFE_FALLBACK_AGENT = "fallback_agent"


@dataclass(frozen=True)
class ExecutionGovernanceDecision:
    """
    Resultado da avaliação de governança.
    """

    allowed: bool
    requested_agent: str
    selected_agent: str
    current_step: int
    max_steps: int
    repeated_visits: int
    max_same_agent_visits: int
    loop_detected: bool
    budget_exceeded: bool
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _normalize_positive_integer(
    value: Any,
    *,
    default: int,
) -> int:
    try:
        normalized = int(value)
    except (TypeError, ValueError):
        normalized = default

    return max(1, normalized)


def _extract_route_name(
    route_record: Any,
) -> str:
    if isinstance(route_record, Mapping):
        return str(
            route_record.get("next_node")
            or route_record.get("route")
            or route_record.get("agent")
            or ""
        ).strip()

    return str(route_record or "").strip()


def count_agent_visits(
    route_history: Sequence[Any] | None,
    agent: str,
) -> int:
    """
    Conta quantas vezes o agente aparece no histórico.
    """
    normalized_agent = str(agent or "").strip()

    if not normalized_agent:
        return 0

    return sum(
        1
        for record in list(route_history or [])
        if _extract_route_name(record)
        == normalized_agent
    )


def evaluate_execution_governance(
    *,
    requested_agent: str,
    route_history: Sequence[Any] | None = None,
    execution_steps: Any = 0,
    max_execution_steps: Any = (
        DEFAULT_MAX_EXECUTION_STEPS
    ),
    max_same_agent_visits: Any = (
        DEFAULT_MAX_SAME_AGENT_VISITS
    ),
    fallback_agent: str = SAFE_FALLBACK_AGENT,
) -> ExecutionGovernanceDecision:
    """
    Avalia se uma rota pode ser executada com segurança.

    O passo atual é incrementado antes da avaliação,
    representando a próxima execução solicitada.
    """
    requested_agent = str(
        requested_agent or fallback_agent
    ).strip()

    fallback_agent = str(
        fallback_agent or SAFE_FALLBACK_AGENT
    ).strip()

    current_step = (
        _normalize_positive_integer(
            execution_steps,
            default=0,
        )
        if execution_steps
        else 0
    ) + 1

    max_steps = _normalize_positive_integer(
        max_execution_steps,
        default=DEFAULT_MAX_EXECUTION_STEPS,
    )

    max_visits = _normalize_positive_integer(
        max_same_agent_visits,
        default=DEFAULT_MAX_SAME_AGENT_VISITS,
    )

    previous_visits = count_agent_visits(
        route_history,
        requested_agent,
    )

    repeated_visits = previous_visits + 1

    budget_exceeded = (
        current_step > max_steps
    )

    loop_detected = (
        requested_agent != fallback_agent
        and repeated_visits > max_visits
    )

    if budget_exceeded:
        return ExecutionGovernanceDecision(
            allowed=False,
            requested_agent=requested_agent,
            selected_agent=fallback_agent,
            current_step=current_step,
            max_steps=max_steps,
            repeated_visits=repeated_visits,
            max_same_agent_visits=max_visits,
            loop_detected=False,
            budget_exceeded=True,
            reason=(
                "execution_step_budget_exceeded"
            ),
        )

    if loop_detected:
        return ExecutionGovernanceDecision(
            allowed=False,
            requested_agent=requested_agent,
            selected_agent=fallback_agent,
            current_step=current_step,
            max_steps=max_steps,
            repeated_visits=repeated_visits,
            max_same_agent_visits=max_visits,
            loop_detected=True,
            budget_exceeded=False,
            reason=(
                "repeated_agent_route_detected"
            ),
        )

    return ExecutionGovernanceDecision(
        allowed=True,
        requested_agent=requested_agent,
        selected_agent=requested_agent,
        current_step=current_step,
        max_steps=max_steps,
        repeated_visits=repeated_visits,
        max_same_agent_visits=max_visits,
        loop_detected=False,
        budget_exceeded=False,
        reason="route_allowed",
    )


def _resolve_requested_agent(
    state: Mapping[str, Any],
) -> str:
    """
    Resolve a rota solicitada antes da avaliacao de governanca.

    O ReAct somente pode assumir a execucao quando:
    - react_enabled estiver explicitamente habilitado;
    - existir uma solicitacao explicita via react_requested.

    Com a flag desligada, preserva integralmente o fluxo legado.
    """
    react_enabled = bool(
        state.get("react_enabled", False)
    )

    react_requested = bool(
        state.get(
            "react_requested",
            False,
        )
    )

    react_action = state.get(
        "react_action",
        {},
    )

    legacy_react_action = (
        isinstance(react_action, Mapping)
        and bool(react_action)
    )

    if (
        react_enabled
        and (
            react_requested
            or legacy_react_action
        )
    ):
        return "react_agent"

    return str(
        state.get(
            "next_node",
            SAFE_FALLBACK_AGENT,
        )
        or SAFE_FALLBACK_AGENT
    ).strip()


def apply_execution_governance(
    state: Mapping[str, Any],
) -> dict[str, Any]:
    """
    Aplica governança sobre o estado do LangGraph.

    Retorna somente os campos atualizados.
    """
    decision = evaluate_execution_governance(
        requested_agent=_resolve_requested_agent(
            state
        ),
        route_history=state.get(
            "route_history",
            [],
        ),
        execution_steps=state.get(
            "execution_steps",
            0,
        ),
        max_execution_steps=state.get(
            "max_execution_steps",
            DEFAULT_MAX_EXECUTION_STEPS,
        ),
        max_same_agent_visits=state.get(
            "max_same_agent_visits",
            DEFAULT_MAX_SAME_AGENT_VISITS,
        ),
    )

    trace = list(
        state.get("trace", [])
        or []
    )

    trace.append(
        "governance:"
        f"{decision.reason}:"
        f"{decision.requested_agent}->"
        f"{decision.selected_agent}"
    )

    errors = list(
        state.get("errors", [])
        or []
    )

    if not decision.allowed:
        errors.append(
            "A rota solicitada foi interrompida "
            "pela governança de execução."
        )

    return {
        "next_node": decision.selected_agent,
        "execution_steps": (
            decision.current_step
        ),
        "loop_detected": (
            decision.loop_detected
        ),
        "execution_budget_exceeded": (
            decision.budget_exceeded
        ),
        "governance_reason": (
            decision.reason
        ),
        "governance_decision": (
            decision.to_dict()
        ),
        "trace": trace,
        "errors": errors,
    }


__all__ = [
    "DEFAULT_MAX_EXECUTION_STEPS",
    "DEFAULT_MAX_SAME_AGENT_VISITS",
    "SAFE_FALLBACK_AGENT",
    "ExecutionGovernanceDecision",
    "count_agent_visits",
    "evaluate_execution_governance",
    "apply_execution_governance",
]





