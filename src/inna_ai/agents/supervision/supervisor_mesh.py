"""Planejamento determinístico do Supervisor Mesh da INNA."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import asdict, dataclass
from typing import Literal

from inna_ai.agents.routing.team_hierarchy import DEFAULT_TEAM_REGISTRY, TeamHierarchyError, TeamName, TeamSupervisorNode

SUPERVISOR_MESH_SCHEMA_VERSION = "1.0.0"

SupervisorMeshStatus = Literal[
    "inactive",
    "planned",
    "blocked",
]


@dataclass(
    frozen=True,
    slots=True,
)
class SupervisorMeshPlan:
    """Plano governado de colaboração entre supervisores."""

    schema_version: str
    active: bool
    status: SupervisorMeshStatus
    source_team: TeamName
    participant_teams: tuple[TeamName, ...]
    participant_supervisors: tuple[
        TeamSupervisorNode,
        ...,
    ]
    max_supervisors: int
    reason: str

    def model_dump(
        self,
    ) -> dict[str, object]:
        return asdict(self)


def _normalize_max_supervisors(
    value: int,
) -> int:
    if isinstance(value, bool):
        raise ValueError(
            "max_supervisors must be an integer."
        )

    normalized = int(value)

    if normalized < 0:
        raise ValueError(
            "max_supervisors cannot be negative."
        )

    return normalized


def _registered_team(
    team_name: TeamName,
):
    """Resolve a equipe usando o registro hierárquico oficial."""

    return DEFAULT_TEAM_REGISTRY.get_team(
        team_name
    )


def plan_supervisor_mesh(
    *,
    source_team: TeamName,
    requested_teams: Iterable[TeamName],
    max_supervisors: int,
    multi_domain: bool,
) -> SupervisorMeshPlan:
    """Planeja colaboração entre supervisores sem executar agentes."""

    budget = _normalize_max_supervisors(
        max_supervisors
    )

    source = _registered_team(
        source_team
    )

    teams: list[TeamName] = [
        source.name,
    ]

    for requested_team in requested_teams:
        registered = _registered_team(
            requested_team
        )

        if registered.name not in teams:
            teams.append(
                registered.name
            )

    supervisors = tuple(
        _registered_team(
            team_name
        ).supervisor_node
        for team_name in teams
    )

    participant_teams = tuple(
        teams
    )

    if not multi_domain:
        return SupervisorMeshPlan(
            schema_version=(
                SUPERVISOR_MESH_SCHEMA_VERSION
            ),
            active=False,
            status="inactive",
            source_team=source.name,
            participant_teams=participant_teams,
            participant_supervisors=supervisors,
            max_supervisors=budget,
            reason="supervisor_mesh_not_required",
        )

    if len(participant_teams) == 1:
        return SupervisorMeshPlan(
            schema_version=(
                SUPERVISOR_MESH_SCHEMA_VERSION
            ),
            active=False,
            status="blocked",
            source_team=source.name,
            participant_teams=participant_teams,
            participant_supervisors=supervisors,
            max_supervisors=budget,
            reason=(
                "supervisor_mesh_participants_unresolved"
            ),
        )

    if budget < 2:
        return SupervisorMeshPlan(
            schema_version=(
                SUPERVISOR_MESH_SCHEMA_VERSION
            ),
            active=False,
            status="blocked",
            source_team=source.name,
            participant_teams=participant_teams,
            participant_supervisors=supervisors,
            max_supervisors=budget,
            reason=(
                "supervisor_mesh_budget_insufficient"
            ),
        )

    if len(participant_teams) > budget:
        return SupervisorMeshPlan(
            schema_version=(
                SUPERVISOR_MESH_SCHEMA_VERSION
            ),
            active=False,
            status="blocked",
            source_team=source.name,
            participant_teams=participant_teams,
            participant_supervisors=supervisors,
            max_supervisors=budget,
            reason=(
                "supervisor_mesh_budget_exceeded"
            ),
        )

    return SupervisorMeshPlan(
        schema_version=(
            SUPERVISOR_MESH_SCHEMA_VERSION
        ),
        active=True,
        status="planned",
        source_team=source.name,
        participant_teams=participant_teams,
        participant_supervisors=supervisors,
        max_supervisors=budget,
        reason="supervisor_mesh_planned",
    )


__all__ = [
    "SUPERVISOR_MESH_SCHEMA_VERSION",
    "SupervisorMeshPlan",
    "SupervisorMeshStatus",
    "plan_supervisor_mesh",
    "TeamHierarchyError",
]
