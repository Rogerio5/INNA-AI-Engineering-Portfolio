"""
Supervisores determinísticos das equipes da INNA.

Cada supervisor possui autoridade apenas sobre os agentes
registrados em sua própria equipe. Solicitações entre equipes
são escaladas para o supervisor principal.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal

from inna_ai.agents.routing.team_hierarchy import DEFAULT_TEAM_REGISTRY, AgentName, TeamHierarchyError, TeamName, TeamSupervisorNode

TeamRouteSource = Literal[
    "requested_agent",
    "intent_rule",
    "team_default",
    "root_escalation",
]

TeamRouteStatus = Literal[
    "selected",
    "escalated",
]


@dataclass(
    frozen=True,
    slots=True,
)
class TeamSupervisorDecision:
    """
    Decisão formal produzida por um supervisor de equipe.
    """

    team_name: TeamName
    supervisor_node: TeamSupervisorNode
    next_node: AgentName | Literal["supervisor"]
    selected_agent: AgentName | None
    status: TeamRouteStatus
    route_source: TeamRouteSource
    requires_root_supervisor: bool
    reason: str

    def model_dump(
        self,
    ) -> dict[str, Any]:
        """
        Mantém uma interface semelhante aos modelos Pydantic
        usados no restante do núcleo agentic.
        """
        return asdict(self)


def _normalize_text(
    value: Any,
) -> str:
    return str(
        value or ""
    ).strip()


def _requested_agent(
    state: dict[str, Any],
) -> str:
    """
    Obtém o agente solicitado pelo supervisor principal.

    A prioridade é:
    1. team_requested_agent;
    2. next_node.
    """
    explicit = _normalize_text(
        state.get(
            "team_requested_agent"
        )
    )

    if explicit:
        return explicit

    return _normalize_text(
        state.get(
            "next_node"
        )
    )


def _infer_financial_agent(
    state: dict[str, Any],
) -> AgentName:
    intent = _normalize_text(
        state.get(
            "intent"
        )
    )

    if intent == "relatorio":
        return "report_agent"

    return "financial_agent"


def _infer_knowledge_agent(
    state: dict[str, Any],
) -> AgentName:
    intent = _normalize_text(
        state.get(
            "intent"
        )
    )

    if intent == "consulta_rag":
        return "rag_agent"

    return "education_agent"


def _infer_support_agent(
    state: dict[str, Any],
) -> AgentName:
    del state
    return "fallback_agent"


_TEAM_DEFAULT_RESOLVERS = {
    "financial_team": _infer_financial_agent,
    "knowledge_team": _infer_knowledge_agent,
    "support_team": _infer_support_agent,
}


def resolve_team_supervisor_decision(
    *,
    team_name: TeamName,
    state: dict[str, Any],
) -> TeamSupervisorDecision:
    """
    Resolve a rota interna de uma equipe.

    Regras:
    - agente solicitado e pertencente à equipe: selecionado;
    - agente de outra equipe: escalado ao supervisor principal;
    - agente desconhecido: escalado ao supervisor principal;
    - solicitação vazia: agente inferido pela intenção;
    - o supervisor não altera o estado recebido.
    """
    team = DEFAULT_TEAM_REGISTRY.get_team(
        team_name
    )

    requested_agent = _requested_agent(
        state
    )

    if requested_agent:
        try:
            requested_team = (
                DEFAULT_TEAM_REGISTRY
                .team_for_agent(
                    requested_agent  # type: ignore[arg-type]
                )
            )
        except TeamHierarchyError:
            return TeamSupervisorDecision(
                team_name=team.name,
                supervisor_node=(
                    team.supervisor_node
                ),
                next_node="supervisor",
                selected_agent=None,
                status="escalated",
                route_source="root_escalation",
                requires_root_supervisor=True,
                reason=(
                    "O agente solicitado não está "
                    "registrado na hierarquia da INNA."
                ),
            )

        if requested_team.name != team.name:
            return TeamSupervisorDecision(
                team_name=team.name,
                supervisor_node=(
                    team.supervisor_node
                ),
                next_node="supervisor",
                selected_agent=None,
                status="escalated",
                route_source="root_escalation",
                requires_root_supervisor=True,
                reason=(
                    "O agente solicitado pertence a "
                    "outra equipe e precisa ser avaliado "
                    "pelo supervisor principal."
                ),
            )

        selected_agent = (
            requested_agent
        )

        return TeamSupervisorDecision(
            team_name=team.name,
            supervisor_node=(
                team.supervisor_node
            ),
            next_node=selected_agent,  # type: ignore[arg-type]
            selected_agent=selected_agent,  # type: ignore[arg-type]
            status="selected",
            route_source="requested_agent",
            requires_root_supervisor=False,
            reason=(
                "O agente solicitado pertence à equipe "
                "e foi autorizado pelo supervisor local."
            ),
        )

    resolver = _TEAM_DEFAULT_RESOLVERS[
        team.name
    ]

    selected_agent = resolver(
        state
    )

    if selected_agent not in team.members:
        raise TeamHierarchyError(
            "A regra interna da equipe selecionou "
            "um agente fora de seus membros."
        )

    intent = _normalize_text(
        state.get(
            "intent"
        )
    )

    route_source: TeamRouteSource = (
        "intent_rule"
        if intent
        else "team_default"
    )

    return TeamSupervisorDecision(
        team_name=team.name,
        supervisor_node=team.supervisor_node,
        next_node=selected_agent,
        selected_agent=selected_agent,
        status="selected",
        route_source=route_source,
        requires_root_supervisor=False,
        reason=(
            "O supervisor de equipe selecionou "
            "o agente por regra interna."
        ),
    )


def _append_team_route_history(
    state: dict[str, Any],
    decision: TeamSupervisorDecision,
) -> list[dict[str, Any]]:
    history = [
        dict(item)
        for item in state.get(
            "team_route_history",
            [],
        )
        if isinstance(
            item,
            dict,
        )
    ]

    history.append(
        decision.model_dump()
    )

    return history


def _append_trace(
    state: dict[str, Any],
    decision: TeamSupervisorDecision,
) -> list[str]:
    trace = [
        str(item)
        for item in state.get(
            "trace",
            [],
        )
    ]

    trace.append(

            "team_supervisor:"
            f"{decision.team_name}:"
            f"{decision.status}:"
            f"{decision.next_node}"

    )

    return trace


def team_supervisor_node(
    state: dict[str, Any],
    *,
    team_name: TeamName,
) -> dict[str, Any]:
    """
    Nó genérico dos supervisores de equipe.
    """
    decision = (
        resolve_team_supervisor_decision(
            team_name=team_name,
            state=dict(state),
        )
    )

    structured_response = dict(
        state.get(
            "structured_response",
            {},
        )
    )

    team_decisions = dict(
        structured_response.get(
            "team_supervisor_decisions",
            {},
        )
    )

    team_decisions[
        decision.team_name
    ] = decision.model_dump()

    structured_response[
        "team_supervisor_decisions"
    ] = team_decisions

    current_root_visits = int(
        state.get(
            "root_supervisor_visits",
            0,
        )
        or 0
    )

    root_supervisor_visits = (
        current_root_visits + 1
        if decision.requires_root_supervisor
        else current_root_visits
    )

    max_root_supervisor_visits = int(
        state.get(
            "max_root_supervisor_visits",
            3,
        )
        or 3
    )

    root_limit_reached = (
        decision.requires_root_supervisor
        and root_supervisor_visits
        >= max_root_supervisor_visits
    )

    effective_next_node = (
        "fallback_agent"
        if root_limit_reached
        else decision.next_node
    )

    effective_requires_root = (
        decision.requires_root_supervisor
        and not root_limit_reached
    )

    effective_reason = (
        "O limite de retornos ao supervisor "
        "principal foi atingido; a execução "
        "seguirá para o fallback pela "
        "governança."
        if root_limit_reached
        else decision.reason
    )

    trace = _append_trace(
        state,
        decision,
    )

    if root_limit_reached:
        trace.append(
            "team_supervisor:"
            "root_limit:"
            "fallback_agent"
        )

    return {
        "current_team": decision.team_name,
        "team_supervisor": (
            decision.supervisor_node
        ),
        "team_route": effective_next_node,
        "next_node": effective_next_node,
        "team_route_source": (
            decision.route_source
        ),
        "team_routing_reason": (
            effective_reason
        ),
        "team_requires_root_supervisor": (
            effective_requires_root
        ),
        "root_supervisor_visits": (
            root_supervisor_visits
        ),
        "team_route_history": (
            _append_team_route_history(
                state,
                decision,
            )
        ),
        "structured_response": (
            structured_response
        ),
        "trace": trace,
    }


def financial_team_supervisor_node(
    state: dict[str, Any],
) -> dict[str, Any]:
    return team_supervisor_node(
        state,
        team_name="financial_team",
    )


def knowledge_team_supervisor_node(
    state: dict[str, Any],
) -> dict[str, Any]:
    return team_supervisor_node(
        state,
        team_name="knowledge_team",
    )


def support_team_supervisor_node(
    state: dict[str, Any],
) -> dict[str, Any]:
    return team_supervisor_node(
        state,
        team_name="support_team",
    )


TEAM_SUPERVISOR_NODES = {
    "financial_team_supervisor": (
        financial_team_supervisor_node
    ),
    "knowledge_team_supervisor": (
        knowledge_team_supervisor_node
    ),
    "support_team_supervisor": (
        support_team_supervisor_node
    ),
}


__all__ = [
    "TeamRouteSource",
    "TeamRouteStatus",
    "TeamSupervisorDecision",
    "resolve_team_supervisor_decision",
    "team_supervisor_node",
    "financial_team_supervisor_node",
    "knowledge_team_supervisor_node",
    "support_team_supervisor_node",
    "TEAM_SUPERVISOR_NODES",
]
