"""Runtime determinístico do Supervisor Mesh da INNA."""

from __future__ import annotations

from typing import Any, cast

from inna_ai.agents.supervision.supervisor_mesh import SupervisorMeshPlan, plan_supervisor_mesh
from inna_ai.agents.routing.team_hierarchy import DEFAULT_TEAM_REGISTRY, AgentName, TeamHierarchyError, TeamName


def _normalize_text(
    value: Any,
) -> str:
    return str(
        value or ""
    ).strip()


def _registered_team_name(
    value: Any,
) -> TeamName | None:
    normalized = _normalize_text(
        value
    )

    if not normalized:
        return None

    try:
        return (
            DEFAULT_TEAM_REGISTRY
            .get_team(
                cast(
                    TeamName,
                    normalized,
                )
            )
            .name
        )
    except TeamHierarchyError:
        return None


def _team_for_agent(
    value: Any,
) -> TeamName | None:
    normalized = _normalize_text(
        value
    )

    if not normalized:
        return None

    try:
        return (
            DEFAULT_TEAM_REGISTRY
            .team_for_agent(
                cast(
                    AgentName,
                    normalized,
                )
            )
            .name
        )
    except TeamHierarchyError:
        return None


def _append_team(
    teams: list[TeamName],
    team: TeamName | None,
) -> None:
    if (
        team is not None
        and team not in teams
    ):
        teams.append(
            team
        )


def infer_supervisor_mesh_teams(
    state: dict[str, Any],
) -> tuple[TeamName, ...]:
    """Infere equipes participantes usando apenas estado governado."""

    teams: list[TeamName] = []

    # Em reentrada/handoff, preserva a equipe atual como origem.
    _append_team(
        teams,
        _registered_team_name(
            state.get(
                "current_team"
            )
        ),
    )

    # Equipe da rota principal produzida pelo Adaptive Gateway.
    target_agent = (
        state.get(
            "adaptive_target_agent"
        )
        or state.get(
            "next_node"
        )
    )

    _append_team(
        teams,
        _team_for_agent(
            target_agent
        ),
    )

    # Banco/diagnóstico/relatório pertencem ao domínio financeiro.
    if (
        bool(
            state.get(
                "use_database",
                False,
            )
        )
        or bool(
            state.get(
                "generate_report",
                False,
            )
        )
    ):
        _append_team(
            teams,
            "financial_team",
        )

    # RAG pertence ao domínio de conhecimento.
    if bool(
        state.get(
            "use_rag",
            False,
        )
    ):
        _append_team(
            teams,
            "knowledge_team",
        )

    # Um handoff já solicitado também participa do plano.
    handoff = state.get(
        "handoff_current"
    )

    if isinstance(
        handoff,
        dict,
    ):
        if (
            _normalize_text(
                handoff.get(
                    "status"
                )
            )
            == "requested"
        ):
            _append_team(
                teams,
                _team_for_agent(
                    handoff.get(
                        "to_agent"
                    )
                ),
            )

    # Fail-safe: sempre existe uma origem conhecida.
    if not teams:
        teams.append(
            DEFAULT_TEAM_REGISTRY
            .team_for_agent(
                "fallback_agent"
            )
            .name
        )

    return tuple(
        teams
    )


def _adaptive_max_supervisors(
    state: dict[str, Any],
) -> int:
    budget = state.get(
        "adaptive_budget",
        {},
    )

    if not isinstance(
        budget,
        dict,
    ):
        return 1

    value = budget.get(
        "max_supervisors",
        1,
    )

    try:
        normalized = int(
            value
        )
    except (
        TypeError,
        ValueError,
    ):
        return 1

    return max(
        0,
        normalized,
    )


def _append_mesh_history(
    state: dict[str, Any],
    plan: SupervisorMeshPlan,
) -> list[dict[str, Any]]:
    history = [
        dict(item)
        for item in state.get(
            "supervisor_mesh_history",
            [],
        )
        if isinstance(
            item,
            dict,
        )
    ]

    history.append(
        {
            "schema_version": (
                plan.schema_version
            ),
            "status": plan.status,
            "active": plan.active,
            "source_team": (
                plan.source_team
            ),
            "participant_teams": list(
                plan.participant_teams
            ),
            "participant_supervisors": list(
                plan.participant_supervisors
            ),
            "max_supervisors": (
                plan.max_supervisors
            ),
            "reason": plan.reason,
        }
    )

    return history


def _append_mesh_trace(
    state: dict[str, Any],
    plan: SupervisorMeshPlan,
) -> list[str]:
    trace = [
        str(item)
        for item in state.get(
            "trace",
            [],
        )
    ]

    trace.append(
        
            "supervisor_mesh:"
            f"{plan.status}:"
            f"{plan.source_team}:"
            f"{len(plan.participant_supervisors)}"
        
    )

    return trace


def supervisor_mesh_node(
    state: dict[str, Any],
) -> dict[str, Any]:
    """Produz o plano governado; não executa agentes."""

    teams = infer_supervisor_mesh_teams(
        state
    )

    source_team = teams[0]

    effective_multi_domain = (
        bool(
            state.get(
                "adaptive_multi_domain",
                False,
            )
        )
        or len(teams) > 1
    )

    plan = plan_supervisor_mesh(
        source_team=source_team,
        requested_teams=teams[1:],
        max_supervisors=(
            _adaptive_max_supervisors(
                state
            )
        ),
        multi_domain=effective_multi_domain,
    )

    result = {
        "supervisor_mesh_active": (
            plan.active
        ),
        "supervisor_mesh_status": (
            plan.status
        ),
        "supervisor_mesh_plan": (
            plan.model_dump()
        ),
        "supervisor_mesh_requested_teams": list(
            plan.participant_teams
        ),
        "supervisor_mesh_supervisors": list(
            plan.participant_supervisors
        ),
        "supervisor_mesh_supervisor_count": len(
            plan.participant_supervisors
        ),
        "supervisor_mesh_history": (
            _append_mesh_history(
                state,
                plan,
            )
        ),
        "trace": _append_mesh_trace(
            state,
            plan,
        ),
    }

    if plan.status == "blocked":
        result.update(
            {
                "next_node": "fallback_agent",
                "team_requested_agent": (
                    "fallback_agent"
                ),
                "team_routing_reason": (
                    plan.reason
                ),
            }
        )

    return result


def _normalize_string_list(
    value: Any,
) -> list[str]:
    if not isinstance(
        value,
        (list, tuple),
    ):
        return []

    result: list[str] = []

    for item in value:
        normalized = _normalize_text(
            item
        )

        if (
            normalized
            and normalized not in result
        ):
            result.append(
                normalized
            )

    return result


def evaluate_supervisor_mesh_visit(
    state: dict[str, Any],
    supervisor_node: str,
) -> dict[str, Any]:
    """
    Autoriza uma visita a supervisor dentro do Mesh.

    O controle é fail-closed quando o Mesh está ativo.
    Supervisores repetidos não consomem novo slot do
    orçamento, pois max_supervisors limita supervisores
    distintos.
    """

    supervisor = _normalize_text(
        supervisor_node
    )

    visited = _normalize_string_list(
        state.get(
            "supervisor_mesh_visited_supervisors",
            [],
        )
    )

    history = [
        dict(item)
        for item in state.get(
            "supervisor_mesh_visit_history",
            [],
        )
        if isinstance(
            item,
            dict,
        )
    ]

    active = bool(
        state.get(
            "supervisor_mesh_active",
            False,
        )
    )

    if not active:
        return {
            "allowed": True,
            "supervisor": supervisor,
            "visited_supervisors": visited,
            "visited_count": len(
                visited
            ),
            "visit_history": history,
            "reason": (
                "supervisor_mesh_inactive"
            ),
        }

    plan = state.get(
        "supervisor_mesh_plan"
    )

    if not isinstance(
        plan,
        dict,
    ):
        return {
            "allowed": False,
            "supervisor": supervisor,
            "visited_supervisors": visited,
            "visited_count": len(
                visited
            ),
            "visit_history": history,
            "reason": (
                "supervisor_mesh_plan_missing"
            ),
        }

    participants = _normalize_string_list(
        plan.get(
            "participant_supervisors",
            [],
        )
    )

    if (
        not supervisor
        or supervisor not in participants
    ):
        decision = {
            "allowed": False,
            "supervisor": supervisor,
            "visited_count": len(
                visited
            ),
            "reason": (
                "supervisor_mesh_unplanned_supervisor"
            ),
        }

        history.append(
            dict(decision)
        )

        return {
            **decision,
            "visited_supervisors": visited,
            "visit_history": history,
        }

    raw_budget = plan.get(
        "max_supervisors",
        0,
    )

    try:
        max_supervisors = int(
            raw_budget
        )
    except (
        TypeError,
        ValueError,
    ):
        max_supervisors = 0

    if max_supervisors < 1:
        decision = {
            "allowed": False,
            "supervisor": supervisor,
            "visited_count": len(
                visited
            ),
            "reason": (
                "supervisor_mesh_invalid_budget"
            ),
        }

        history.append(
            dict(decision)
        )

        return {
            **decision,
            "visited_supervisors": visited,
            "visit_history": history,
        }

    next_visited = list(
        visited
    )

    if supervisor not in next_visited:
        next_visited.append(
            supervisor
        )

    if len(next_visited) > max_supervisors:
        decision = {
            "allowed": False,
            "supervisor": supervisor,
            "visited_count": len(
                visited
            ),
            "reason": (
                "supervisor_mesh_execution_budget_exceeded"
            ),
        }

        history.append(
            dict(decision)
        )

        return {
            **decision,
            "visited_supervisors": visited,
            "visit_history": history,
        }

    reason = (
        "supervisor_mesh_supervisor_revisit"
        if supervisor in visited
        else "supervisor_mesh_supervisor_authorized"
    )

    decision = {
        "allowed": True,
        "supervisor": supervisor,
        "visited_count": len(
            next_visited
        ),
        "reason": reason,
    }

    history.append(
        dict(decision)
    )

    return {
        **decision,
        "visited_supervisors": next_visited,
        "visit_history": history,
    }


def select_supervisor_mesh_route(
    state: dict[str, Any],
) -> str:
    """Seleciona a saída segura do Supervisor Mesh."""

    status = _normalize_text(
        state.get(
            "supervisor_mesh_status"
        )
    )

    if status == "blocked":
        return "execution_governance"

    return "team_router"


__all__ = [
    "evaluate_supervisor_mesh_visit",
    "infer_supervisor_mesh_teams",
    "select_supervisor_mesh_route",
    "supervisor_mesh_node",
]
