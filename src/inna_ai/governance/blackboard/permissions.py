"""Política deny-by-default do Shared Blackboard da INNA."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from inna_ai.agents.registry.agent_catalog import DEFAULT_AGENT_REGISTRY
from inna_ai.agents.registry.agent_registry import AgentDefinition, AgentRegistry
from inna_ai.governance.blackboard.models import BlackboardEntry, BlackboardEntryKind, BlackboardVisibility, can_read_blackboard_entry
from inna_ai.agents.routing.team_hierarchy import DEFAULT_TEAM_REGISTRY

BlackboardPrincipalType = Literal[
    "agent",
    "service_identity",
    "team_supervisor",
    "unknown",
]


@dataclass(
    frozen=True,
    slots=True,
)
class BlackboardPermissionDecision:
    """Decisão formal de autorização do Blackboard."""

    allowed: bool
    reason: str
    principal: str
    principal_type: BlackboardPrincipalType
    team: str | None


_AGENT_PUBLISH_KINDS: dict[
    str,
    frozenset[BlackboardEntryKind],
] = {
    "financial_agent": frozenset(
        {
            "fact",
            "result",
            "evidence",
        }
    ),
    "report_agent": frozenset(
        {
            "result",
            "evidence",
        }
    ),
    "education_agent": frozenset(
        {
            "fact",
            "result",
            "evidence",
        }
    ),
    "rag_agent": frozenset(
        {
            "fact",
            "result",
            "evidence",
        }
    ),
    "fallback_agent": frozenset(
        {
            "result",
        }
    ),
    "research_agent": frozenset(
        {
            "result",
            "evidence",
        }
    ),
}


_AGENT_PUBLISH_VISIBILITY: dict[
    str,
    frozenset[BlackboardVisibility],
] = {
    "financial_agent": frozenset(
        {
            "workflow",
            "team",
        }
    ),
    "report_agent": frozenset(
        {
            "workflow",
            "team",
        }
    ),
    "education_agent": frozenset(
        {
            "workflow",
            "team",
        }
    ),
    "rag_agent": frozenset(
        {
            "workflow",
            "team",
        }
    ),
    "fallback_agent": frozenset(
        {
            "team",
        }
    ),
    "research_agent": frozenset(
        {
            "workflow",
        }
    ),
}


def _normalize_text(
    value: object,
) -> str:
    return str(
        value or ""
    ).strip()


def _agent_definitions(
    registry: AgentRegistry,
) -> dict[str, AgentDefinition]:
    return {
        definition.agent_id: definition
        for definition in registry.list_definitions()
    }


def _supervisor_teams() -> dict[str, str]:
    return {
        team.supervisor_node: team.name
        for team in DEFAULT_TEAM_REGISTRY.teams
    }


def _resolve_principal(
    principal: str,
    *,
    registry: AgentRegistry,
) -> tuple[
    BlackboardPrincipalType,
    str | None,
    AgentDefinition | None,
]:
    normalized = _normalize_text(
        principal
    )

    definitions = _agent_definitions(
        registry
    )

    definition = definitions.get(
        normalized
    )

    if definition is not None:
        return (
            definition.kind,
            definition.team,
            definition,
        )

    supervisor_team = (
        _supervisor_teams().get(
            normalized
        )
    )

    if supervisor_team is not None:
        return (
            "team_supervisor",
            supervisor_team,
            None,
        )

    return (
        "unknown",
        None,
        None,
    )


def evaluate_blackboard_publish(
    *,
    principal: str,
    kind: BlackboardEntryKind,
    visibility: BlackboardVisibility,
    team: str | None,
    registry: AgentRegistry = DEFAULT_AGENT_REGISTRY,
) -> BlackboardPermissionDecision:
    """Autoriza publicação sem inspecionar conteúdo bruto."""

    normalized_principal = (
        _normalize_text(
            principal
        )
    )

    (
        principal_type,
        principal_team,
        definition,
    ) = _resolve_principal(
        normalized_principal,
        registry=registry,
    )

    if principal_type == "unknown":
        return BlackboardPermissionDecision(
            allowed=False,
            reason="blackboard_unknown_principal",
            principal=normalized_principal,
            principal_type=principal_type,
            team=None,
        )

    if (
        definition is not None
        and definition.status != "active"
    ):
        return BlackboardPermissionDecision(
            allowed=False,
            reason="blackboard_inactive_principal",
            principal=normalized_principal,
            principal_type=principal_type,
            team=principal_team,
        )

    if principal_type == "service_identity":
        return BlackboardPermissionDecision(
            allowed=False,
            reason=(
                "blackboard_service_identity_denied"
            ),
            principal=normalized_principal,
            principal_type=principal_type,
            team=None,
        )

    if principal_type == "team_supervisor":
        if kind != "decision":
            return BlackboardPermissionDecision(
                allowed=False,
                reason=(
                    "blackboard_supervisor_kind_denied"
                ),
                principal=normalized_principal,
                principal_type=principal_type,
                team=principal_team,
            )

        if (
            visibility == "team"
            and team != principal_team
        ):
            return BlackboardPermissionDecision(
                allowed=False,
                reason=(
                    "blackboard_cross_team_publish_denied"
                ),
                principal=normalized_principal,
                principal_type=principal_type,
                team=principal_team,
            )

        return BlackboardPermissionDecision(
            allowed=True,
            reason=(
                "blackboard_supervisor_authorized"
            ),
            principal=normalized_principal,
            principal_type=principal_type,
            team=principal_team,
        )

    allowed_kinds = (
        _AGENT_PUBLISH_KINDS.get(
            normalized_principal,
            frozenset(),
        )
    )

    if kind not in allowed_kinds:
        return BlackboardPermissionDecision(
            allowed=False,
            reason="blackboard_kind_not_authorized",
            principal=normalized_principal,
            principal_type=principal_type,
            team=principal_team,
        )

    allowed_visibility = (
        _AGENT_PUBLISH_VISIBILITY.get(
            normalized_principal,
            frozenset(),
        )
    )

    if visibility not in allowed_visibility:
        return BlackboardPermissionDecision(
            allowed=False,
            reason=(
                "blackboard_visibility_not_authorized"
            ),
            principal=normalized_principal,
            principal_type=principal_type,
            team=principal_team,
        )

    if visibility == "team":
        if (
            principal_team is None
            or team != principal_team
        ):
            return BlackboardPermissionDecision(
                allowed=False,
                reason=(
                    "blackboard_cross_team_publish_denied"
                ),
                principal=normalized_principal,
                principal_type=principal_type,
                team=principal_team,
            )

    return BlackboardPermissionDecision(
        allowed=True,
        reason="blackboard_publish_authorized",
        principal=normalized_principal,
        principal_type=principal_type,
        team=principal_team,
    )


def evaluate_blackboard_read(
    *,
    principal: str,
    entry: BlackboardEntry,
    registry: AgentRegistry = DEFAULT_AGENT_REGISTRY,
) -> BlackboardPermissionDecision:
    """Autoriza leitura usando Registry + visibilidade."""

    normalized_principal = (
        _normalize_text(
            principal
        )
    )

    (
        principal_type,
        principal_team,
        definition,
    ) = _resolve_principal(
        normalized_principal,
        registry=registry,
    )

    if principal_type == "unknown":
        return BlackboardPermissionDecision(
            allowed=False,
            reason="blackboard_unknown_principal",
            principal=normalized_principal,
            principal_type=principal_type,
            team=None,
        )

    if (
        definition is not None
        and definition.status != "active"
    ):
        return BlackboardPermissionDecision(
            allowed=False,
            reason="blackboard_inactive_principal",
            principal=normalized_principal,
            principal_type=principal_type,
            team=principal_team,
        )

    if principal_type == "service_identity":
        return BlackboardPermissionDecision(
            allowed=False,
            reason=(
                "blackboard_service_identity_denied"
            ),
            principal=normalized_principal,
            principal_type=principal_type,
            team=None,
        )

    # Fallback recebe acesso mínimo e apenas à própria equipe.
    if normalized_principal == "fallback_agent":
        if (
            entry.visibility != "team"
            or entry.team != "support_team"
        ):
            return BlackboardPermissionDecision(
                allowed=False,
                reason=(
                    "blackboard_fallback_read_denied"
                ),
                principal=normalized_principal,
                principal_type=principal_type,
                team=principal_team,
            )

    # Research Agent não pertence à hierarquia formal.
    # Ele pode consumir somente registros workflow.
    if normalized_principal == "research_agent":
        if entry.visibility != "workflow":
            return BlackboardPermissionDecision(
                allowed=False,
                reason=(
                    "blackboard_research_team_read_denied"
                ),
                principal=normalized_principal,
                principal_type=principal_type,
                team=None,
            )

    visible = can_read_blackboard_entry(
        entry,
        consumer_team=principal_team,
    )

    if not visible:
        return BlackboardPermissionDecision(
            allowed=False,
            reason="blackboard_entry_not_visible",
            principal=normalized_principal,
            principal_type=principal_type,
            team=principal_team,
        )

    return BlackboardPermissionDecision(
        allowed=True,
        reason="blackboard_read_authorized",
        principal=normalized_principal,
        principal_type=principal_type,
        team=principal_team,
    )


__all__ = [
    "BlackboardPermissionDecision",
    "BlackboardPrincipalType",
    "evaluate_blackboard_publish",
    "evaluate_blackboard_read",
]
