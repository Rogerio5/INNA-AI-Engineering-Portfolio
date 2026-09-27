"""Nó LangGraph do Adaptive Intent & Complexity Gateway."""

from __future__ import annotations

from dataclasses import asdict
from typing import cast

from inna_ai.orchestration.gateway.adaptive_gateway import RiskLevel, decide_adaptive_route
from inna_ai.orchestration.gateway.complexity_detector import assess_request_complexity
from inna_ai.orchestration.state import InnaAgentState

_VALID_RISK_LEVELS = {
    "low",
    "medium",
    "high",
    "critical",
}


def _normalize_risk(
    value: object,
) -> RiskLevel:
    """Normaliza risco com comportamento fail-safe."""

    normalized = str(
        value or "low"
    ).strip().lower()

    if normalized not in _VALID_RISK_LEVELS:
        return "critical"

    return cast(
        RiskLevel,
        normalized,
    )


def _should_request_react(
    *,
    state: InnaAgentState,
    route_type: str,
    risk: str,
    next_node: str,
) -> bool:
    """
    Habilita ReAct somente para casos complexos
    compatíveis com as ferramentas governadas atuais.
    """

    if not bool(
        state.get(
            "react_enabled",
            False,
        )
    ):
        return False

    if str(route_type).strip() != "complex":
        return False

    if str(risk).strip().lower() not in {
        "low",
        "medium",
    }:
        return False

    if str(next_node).strip() not in {
        "financial_agent",
        "rag_agent",
    }:
        return False

    if bool(
        state.get(
            "generate_report",
            False,
        )
    ):
        return False

    if bool(
        state.get(
            "handoff_required",
            False,
        )
    ):
        return False

    return True

def adaptive_gateway_node(
    state: InnaAgentState,
) -> InnaAgentState:
    """Produz a política adaptativa sem executar agentes."""

    risk = _normalize_risk(
        state.get(
            "adaptive_risk",
            "low",
        )
    )

    complexity = assess_request_complexity(
        user_message=str(
            state.get(
                "user_message",
                "",
            )
        ),
        intent=str(
            state.get(
                "intent",
                "desconhecido",
            )
        ),
        use_database=bool(
            state.get(
                "use_database",
                False,
            )
        ),
        use_rag=bool(
            state.get(
                "use_rag",
                False,
            )
        ),
        generate_report=bool(
            state.get(
                "generate_report",
                False,
            )
        ),
        handoff_required=bool(
            state.get(
                "handoff_required",
                False,
            )
        ),
        multi_domain=bool(
            state.get(
                "adaptive_multi_domain",
                False,
            )
        ),
    )

    decision = decide_adaptive_route(
        intent=str(
            state.get(
                "intent",
                "desconhecido",
            )
        ),
        next_node=str(
            state.get(
                "next_node",
                "fallback_agent",
            )
        ),
        confidence=float(
            state.get(
                "confidence",
                0.0,
            )
        ),
        risk=risk,
        multi_domain=bool(
            state.get(
                "adaptive_multi_domain",
                False,
            )
        ),
        requires_handoff=bool(
            state.get(
                "handoff_required",
                False,
            )
        ),
        complexity_hint=(
            complexity.complexity
        ),
    )

    next_node = str(
        state.get(
            "next_node",
            "fallback_agent",
        )
        or "fallback_agent"
    ).strip()

    if decision.route_type == "escalate":
        next_node = "fallback_agent"

    react_requested = _should_request_react(
        state=state,
        route_type=decision.route_type,
        risk=decision.risk,
        next_node=next_node,
    )

    return {
        "react_requested": react_requested,
        "next_node": next_node,
        "adaptive_complexity": (
            decision.complexity
        ),
        "adaptive_complexity_reason": (
            complexity.reason
        ),
        "adaptive_complexity_signals": list(
            complexity.signals
        ),
        "adaptive_route_type": (
            decision.route_type
        ),
        "adaptive_domain": decision.domain,
        "adaptive_target_supervisor": (
            decision.target_supervisor
        ),
        "adaptive_target_agent": (
            decision.target_agent
        ),
        "adaptive_risk": decision.risk,
        "adaptive_reason": decision.reason,
        "adaptive_budget": asdict(
            decision.budget
        ),

        # Integra o orçamento adaptativo aos mecanismos
        # de governança já existentes da INNA.
        "max_execution_steps": (
            decision.budget.max_agents
        ),
        "max_a2a_messages": (
            decision.budget.max_a2a_messages
        ),
        "max_handoffs": (
            decision.budget.max_handoffs
        ),
    }


def select_adaptive_gateway_route(
    state: InnaAgentState,
) -> str:
    """Seleciona a próxima camada após a decisão adaptativa."""

    route = str(
        state.get(
            "adaptive_route_type",
            "escalate",
        )
        or "escalate"
    ).strip()

    if bool(
        state.get(
            "react_requested",
            False,
        )
    ):
        return "execution_governance"

    if route == "complex":
        return "team_router"

    return "execution_governance"


__all__ = [
    "adaptive_gateway_node",
    "select_adaptive_gateway_route",
]

