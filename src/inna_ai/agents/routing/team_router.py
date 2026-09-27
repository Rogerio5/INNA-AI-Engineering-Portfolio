"""
Roteador hierárquico de equipes da INNA.

Converte uma rota de agente produzida pelo supervisor principal
em uma rota para o supervisor da equipe correspondente.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal

from inna_ai.agents.supervision.supervisor_mesh_node import evaluate_supervisor_mesh_visit
from inna_ai.agents.routing.team_hierarchy import DEFAULT_TEAM_REGISTRY, AgentName, TeamHierarchyError, TeamName, TeamSupervisorNode

TeamRouterSource = Literal[
    "supervisor_agent_route",
    "explicit_team_request",
    "fallback_recovery",
]


@dataclass(
    frozen=True,
    slots=True,
)
class TeamRouterDecision:
    """
    Decisão formal do roteador hierárquico.
    """

    requested_agent: AgentName
    selected_team: TeamName
    team_supervisor_node: TeamSupervisorNode
    route_source: TeamRouterSource
    recovered_to_fallback: bool
    reason: str

    def model_dump(
        self,
    ) -> dict[str, Any]:
        return asdict(self)


def _normalize_text(
    value: Any,
) -> str:
    return str(
        value or ""
    ).strip()


def _requested_agent_from_state(
    state: dict[str, Any],
) -> str:
    """
    Resolve o agente solicitado.

    Prioridade:
    1. destino de um handoff solicitado;
    2. agente explicitamente solicitado à equipe;
    3. next_node definido pelo supervisor principal.
    """
    handoff = state.get(
        "handoff_current"
    )

    if isinstance(
        handoff,
        dict,
    ):
        handoff_status = _normalize_text(
            handoff.get(
                "status"
            )
        )

        handoff_target = _normalize_text(
            handoff.get(
                "to_agent"
            )
        )

        if (
            handoff_status == "requested"
            and handoff_target
        ):
            return handoff_target

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


def resolve_team_router_decision(
    state: dict[str, Any],
) -> TeamRouterDecision:
    """
    Resolve o supervisor de equipe para a rota atual.

    Um agente desconhecido é recuperado com segurança para:
    support_team -> fallback_agent.
    """
    requested_agent = (
        _requested_agent_from_state(
            state
        )
    )

    route_source: TeamRouterSource = (
        "explicit_team_request"
        if _normalize_text(
            state.get(
                "team_requested_agent"
            )
        )
        else "supervisor_agent_route"
    )

    recovered_to_fallback = False

    try:
        team = (
            DEFAULT_TEAM_REGISTRY
            .team_for_agent(
                requested_agent  # type: ignore[arg-type]
            )
        )

        normalized_agent = (
            requested_agent
        )
    except TeamHierarchyError:
        team = (
            DEFAULT_TEAM_REGISTRY
            .team_for_agent(
                "fallback_agent"
            )
        )

        normalized_agent = (
            "fallback_agent"
        )

        route_source = (
            "fallback_recovery"
        )

        recovered_to_fallback = True

    return TeamRouterDecision(
        requested_agent=normalized_agent,  # type: ignore[arg-type]
        selected_team=team.name,
        team_supervisor_node=(
            team.supervisor_node
        ),
        route_source=route_source,
        recovered_to_fallback=(
            recovered_to_fallback
        ),
        reason=(
            "A rota do agente foi associada ao "
            "supervisor de sua equipe."
            if not recovered_to_fallback
            else (
                "A rota solicitada não pertence à "
                "hierarquia e foi recuperada para "
                "a equipe de suporte."
            )
        ),
    )


def _append_trace(
    state: dict[str, Any],
    decision: TeamRouterDecision,
) -> list[str]:
    trace = [
        str(item)
        for item in state.get(
            "trace",
            [],
        )
    ]

    trace.append(

            "team_router:"
            f"{decision.selected_team}:"
            f"{decision.team_supervisor_node}:"
            f"{decision.requested_agent}"

    )

    return trace


def team_router_node(
    state: dict[str, Any],
) -> dict[str, Any]:
    """
    Prepara o estado para execução do supervisor de equipe.

    Quando o Supervisor Mesh está ativo, a rota também
    precisa ser autorizada pelo plano governado.
    """

    decision = (
        resolve_team_router_decision(
            dict(state)
        )
    )

    mesh_visit = (
        evaluate_supervisor_mesh_visit(
            state,
            decision.team_supervisor_node,
        )
    )

    structured_response = dict(
        state.get(
            "structured_response",
            {},
        )
    )

    structured_response[
        "team_router_decision"
    ] = decision.model_dump()

    structured_response[
        "supervisor_mesh_visit_decision"
    ] = {
        "allowed": mesh_visit[
            "allowed"
        ],
        "supervisor": mesh_visit[
            "supervisor"
        ],
        "visited_count": mesh_visit[
            "visited_count"
        ],
        "reason": mesh_visit[
            "reason"
        ],
    }

    trace = _append_trace(
        state,
        decision,
    )

    if bool(
        state.get(
            "supervisor_mesh_active",
            False,
        )
    ):
        trace.append(

                "supervisor_mesh_visit:"
                f"{mesh_visit['reason']}:"
                f"{mesh_visit['supervisor']}:"
                f"{mesh_visit['visited_count']}"

        )

    if not mesh_visit[
        "allowed"
    ]:
        fallback_team = (
            DEFAULT_TEAM_REGISTRY
            .team_for_agent(
                "fallback_agent"
            )
        )

        return {
            "current_team": (
                fallback_team.name
            ),
            "team_supervisor": (
                fallback_team.supervisor_node
            ),
            "team_requested_agent": (
                "fallback_agent"
            ),
            "team_route": (
                fallback_team.supervisor_node
            ),
            "team_route_source": (
                "fallback_recovery"
            ),
            "team_routing_reason": (
                mesh_visit["reason"]
            ),
            "team_requires_root_supervisor": False,
            "supervisor_mesh_active": False,
            "supervisor_mesh_status": "blocked",
            "supervisor_mesh_visited_supervisors": (
                mesh_visit[
                    "visited_supervisors"
                ]
            ),
            "supervisor_mesh_visited_count": (
                mesh_visit[
                    "visited_count"
                ]
            ),
            "supervisor_mesh_visit_history": (
                mesh_visit[
                    "visit_history"
                ]
            ),
            "structured_response": (
                structured_response
            ),
            "trace": trace,
        }

    return {
        "current_team": (
            decision.selected_team
        ),
        "team_supervisor": (
            decision.team_supervisor_node
        ),
        "team_requested_agent": (
            decision.requested_agent
        ),
        "team_route": (
            decision.team_supervisor_node
        ),
        "team_route_source": (
            decision.route_source
        ),
        "team_routing_reason": (
            decision.reason
        ),
        "team_requires_root_supervisor": False,
        "supervisor_mesh_visited_supervisors": (
            mesh_visit[
                "visited_supervisors"
            ]
        ),
        "supervisor_mesh_visited_count": (
            mesh_visit[
                "visited_count"
            ]
        ),
        "supervisor_mesh_visit_history": (
            mesh_visit[
                "visit_history"
            ]
        ),
        "structured_response": (
            structured_response
        ),
        "trace": trace,
    }


def select_team_supervisor_route(
    state: dict[str, Any],
) -> str:
    """
    Função de branch condicional do LangGraph.
    """
    route = _normalize_text(
        state.get(
            "team_supervisor"
        )
        or state.get(
            "team_route"
        )
    )

    allowed_routes = {
        "financial_team_supervisor",
        "knowledge_team_supervisor",
        "support_team_supervisor",
    }

    if route not in allowed_routes:
        return "support_team_supervisor"

    return route


__all__ = [
    "TeamRouterSource",
    "TeamRouterDecision",
    "resolve_team_router_decision",
    "team_router_node",
    "select_team_supervisor_route",
]
