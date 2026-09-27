"""Gateway adaptativo de intenção, complexidade e execução da INNA.

Este módulo não executa agentes.
Ele transforma a decisão do supervisor existente em uma política
estruturada de execução para caminhos simples, complexos ou escalados.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from inna_ai.agents.registry.agent_catalog import DEFAULT_AGENT_REGISTRY

RouteType = Literal["simple", "complex", "escalate"]
ComplexityType = Literal["simple", "complex"]
RiskLevel = Literal["low", "medium", "high", "critical"]


@dataclass(frozen=True)
class AdaptiveExecutionBudget:
    """Limites de execução associados à rota adaptativa."""

    max_supervisors: int
    max_agents: int
    max_a2a_messages: int
    max_handoffs: int
    max_rounds: int


@dataclass(frozen=True)
class AdaptiveGatewayDecision:
    """Decisão produzida pelo Adaptive Intent & Complexity Gateway."""

    intent: str
    domain: str
    complexity: ComplexityType
    route_type: RouteType
    confidence: float
    risk: RiskLevel
    target_agent: str
    target_supervisor: str
    budget: AdaptiveExecutionBudget
    reason: str


_SIMPLE_BUDGET = AdaptiveExecutionBudget(
    max_supervisors=1,
    max_agents=1,
    max_a2a_messages=0,
    max_handoffs=1,
    max_rounds=1,
)

_COMPLEX_BUDGET = AdaptiveExecutionBudget(
    max_supervisors=3,
    max_agents=5,
    max_a2a_messages=6,
    max_handoffs=3,
    max_rounds=2,
)

_ESCALATE_BUDGET = AdaptiveExecutionBudget(
    max_supervisors=1,
    max_agents=1,
    max_a2a_messages=0,
    max_handoffs=1,
    max_rounds=1,
)



def _normalize_confidence(value: float) -> float:
    return max(
        0.0,
        min(float(value), 1.0),
    )


def _registered_execution_target(
    agent: str,
) -> tuple[str, str, str] | None:
    """Resolve somente agentes executáveis no LangGraph principal."""

    agent_id = str(
        agent or ""
    ).strip()

    if not DEFAULT_AGENT_REGISTRY.contains(
        agent_id
    ):
        return None

    definition = (
        DEFAULT_AGENT_REGISTRY.get(
            agent_id
        )
    )

    if definition.status != "active":
        return None

    if definition.kind != "agent":
        return None

    if definition.runtime != "langgraph":
        return None

    if (
        definition.team is None
        or definition.supervisor is None
    ):
        return None

    domain = (
        definition.team
        .removesuffix("_team")
        .strip()
    )

    if not domain:
        return None

    return (
        definition.agent_id,
        domain,
        definition.supervisor,
    )


def _fallback_execution_target(
) -> tuple[str, str, str]:
    """Resolve o fallback pelo Agent Registry."""

    result = _registered_execution_target(
        "fallback_agent"
    )

    if result is None:
        raise RuntimeError(
            "fallback_agent sem registro "
            "executável válido."
        )

    return result


def _resolve_domain(
    agent: str,
) -> tuple[str, str]:
    """Mantém compatibilidade para domínio e supervisor."""

    result = _registered_execution_target(
        agent
    )

    if result is None:
        _, domain, supervisor = (
            _fallback_execution_target()
        )

        return domain, supervisor

    _, domain, supervisor = result

    return domain, supervisor

def decide_adaptive_route(
    *,
    intent: str,
    next_node: str,
    confidence: float,
    risk: RiskLevel = "low",
    multi_domain: bool = False,
    requires_handoff: bool = False,
    complexity_hint: ComplexityType | None = None,
) -> AdaptiveGatewayDecision:
    """Classifica a execução como simples, complexa ou escalada."""

    normalized_intent = str(
        intent or ""
    ).strip()

    normalized_agent = str(
        next_node or "fallback_agent"
    ).strip()

    normalized_confidence = (
        _normalize_confidence(
            confidence
        )
    )

    registered_target = (
        _registered_execution_target(
            normalized_agent
        )
    )

    target_is_executable = (
        registered_target is not None
    )

    if registered_target is None:
        (
            resolved_agent,
            domain,
            supervisor,
        ) = _fallback_execution_target()
    else:
        (
            resolved_agent,
            domain,
            supervisor,
        ) = registered_target

    if (
        normalized_confidence < 0.60
        or normalized_intent
        in {"", "desconhecido"}
        or resolved_agent
        == "fallback_agent"
        or not target_is_executable
        or risk == "critical"
    ):
        (
            fallback_agent,
            fallback_domain,
            fallback_supervisor,
        ) = _fallback_execution_target()

        return AdaptiveGatewayDecision(
            intent=(
                normalized_intent
                or "desconhecido"
            ),
            domain=fallback_domain,
            complexity="complex",
            route_type="escalate",
            confidence=normalized_confidence,
            risk=risk,
            target_agent=fallback_agent,
            target_supervisor=fallback_supervisor,
            budget=_ESCALATE_BUDGET,
            reason=(
                "adaptive_escalation_required"
            ),
        )

    if (
        complexity_hint == "complex"
        or multi_domain
        or requires_handoff
        or risk == "high"
    ):
        return AdaptiveGatewayDecision(
            intent=normalized_intent,
            domain=domain,
            complexity="complex",
            route_type="complex",
            confidence=normalized_confidence,
            risk=risk,
            target_agent=resolved_agent,
            target_supervisor=supervisor,
            budget=_COMPLEX_BUDGET,
            reason="adaptive_complex_route",
        )

    return AdaptiveGatewayDecision(
        intent=normalized_intent,
        domain=domain,
        complexity="simple",
        route_type="simple",
        confidence=normalized_confidence,
        risk=risk,
        target_agent=resolved_agent,
        target_supervisor=supervisor,
        budget=_SIMPLE_BUDGET,
        reason="adaptive_direct_route",
    )


__all__ = [
    "AdaptiveExecutionBudget",
    "AdaptiveGatewayDecision",
    "ComplexityType",
    "RiskLevel",
    "RouteType",
    "decide_adaptive_route",
]
