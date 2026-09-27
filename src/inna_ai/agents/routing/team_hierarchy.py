"""
Contratos formais para equipes hierárquicas da INNA.

Este módulo define:
- equipes especializadas;
- membros permitidos;
- supervisores de equipe;
- limites internos;
- políticas de transferência;
- resolução agente -> equipe.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


AgentName = Literal[
    "financial_agent",
    "education_agent",
    "rag_agent",
    "report_agent",
    "fallback_agent",
]

TeamName = Literal[
    "financial_team",
    "knowledge_team",
    "support_team",
]

TeamSupervisorNode = Literal[
    "financial_team_supervisor",
    "knowledge_team_supervisor",
    "support_team_supervisor",
]


class TeamHierarchyError(
    ValueError
):
    """
    Erro de configuração ou uso da hierarquia.
    """


@dataclass(
    frozen=True,
    slots=True,
)
class TeamDefinition:
    """
    Definição imutável de uma equipe especializada.
    """

    name: TeamName
    supervisor_node: TeamSupervisorNode
    members: tuple[AgentName, ...]
    description: str
    max_internal_handoffs: int = 2

    def __post_init__(
        self,
    ) -> None:
        normalized_description = str(
            self.description or ""
        ).strip()

        if not normalized_description:
            raise TeamHierarchyError(
                "A equipe precisa possuir uma descrição."
            )

        if not self.members:
            raise TeamHierarchyError(
                "A equipe precisa possuir ao menos um membro."
            )

        if len(
            set(self.members)
        ) != len(self.members):
            raise TeamHierarchyError(
                "A equipe não pode possuir membros duplicados."
            )

        if self.max_internal_handoffs < 1:
            raise TeamHierarchyError(
                "O limite interno de handoffs deve ser "
                "maior ou igual a 1."
            )


@dataclass(
    frozen=True,
    slots=True,
)
class TeamTransferDecision:
    """
    Resultado da avaliação de uma transferência entre agentes.
    """

    allowed: bool
    same_team: bool
    requires_root_supervisor: bool
    source_team: TeamName
    target_team: TeamName
    reason: str


class TeamRegistry:
    """
    Registro validado das equipes da INNA.
    """

    def __init__(
        self,
        teams: tuple[TeamDefinition, ...],
    ) -> None:
        if not teams:
            raise TeamHierarchyError(
                "O registro precisa possuir equipes."
            )

        team_names = [
            team.name
            for team in teams
        ]

        if len(
            set(team_names)
        ) != len(team_names):
            raise TeamHierarchyError(
                "Existem nomes de equipes duplicados."
            )

        supervisor_nodes = [
            team.supervisor_node
            for team in teams
        ]

        if len(
            set(supervisor_nodes)
        ) != len(supervisor_nodes):
            raise TeamHierarchyError(
                "Existem supervisores de equipe duplicados."
            )

        agent_to_team: dict[
            AgentName,
            TeamName,
        ] = {}

        for team in teams:
            for member in team.members:
                if member in agent_to_team:
                    existing_team = (
                        agent_to_team[
                            member
                        ]
                    )

                    raise TeamHierarchyError(
                        "O agente "
                        f"{member!r} pertence a mais de uma "
                        "equipe: "
                        f"{existing_team!r} e {team.name!r}."
                    )

                agent_to_team[
                    member
                ] = team.name

        self._teams = teams
        self._teams_by_name = {
            team.name: team
            for team in teams
        }
        self._agent_to_team = (
            agent_to_team
        )

    @property
    def teams(
        self,
    ) -> tuple[TeamDefinition, ...]:
        return self._teams

    @property
    def team_names(
        self,
    ) -> tuple[TeamName, ...]:
        return tuple(
            team.name
            for team in self._teams
        )

    @property
    def agents(
        self,
    ) -> tuple[AgentName, ...]:
        return tuple(
            self._agent_to_team
        )

    def get_team(
        self,
        team_name: TeamName,
    ) -> TeamDefinition:
        try:
            return self._teams_by_name[
                team_name
            ]
        except KeyError as error:
            raise TeamHierarchyError(
                "Equipe não registrada: "
                f"{team_name!r}."
            ) from error

    def team_for_agent(
        self,
        agent: AgentName,
    ) -> TeamDefinition:
        try:
            team_name = self._agent_to_team[
                agent
            ]
        except KeyError as error:
            raise TeamHierarchyError(
                "Agente não associado a uma equipe: "
                f"{agent!r}."
            ) from error

        return self.get_team(
            team_name
        )

    def supervisor_for_agent(
        self,
        agent: AgentName,
    ) -> TeamSupervisorNode:
        return self.team_for_agent(
            agent
        ).supervisor_node

    def members_of(
        self,
        team_name: TeamName,
    ) -> tuple[AgentName, ...]:
        return self.get_team(
            team_name
        ).members

    def is_member(
        self,
        *,
        agent: AgentName,
        team_name: TeamName,
    ) -> bool:
        return (
            agent
            in self.members_of(
                team_name
            )
        )

    def evaluate_transfer(
        self,
        *,
        from_agent: AgentName,
        to_agent: AgentName,
    ) -> TeamTransferDecision:
        source_team = self.team_for_agent(
            from_agent
        )

        target_team = self.team_for_agent(
            to_agent
        )

        same_team = (
            source_team.name
            == target_team.name
        )

        if same_team:
            return TeamTransferDecision(
                allowed=True,
                same_team=True,
                requires_root_supervisor=False,
                source_team=source_team.name,
                target_team=target_team.name,
                reason=(
                    "Transferência interna permitida "
                    "pela equipe especializada."
                ),
            )

        return TeamTransferDecision(
            allowed=False,
            same_team=False,
            requires_root_supervisor=True,
            source_team=source_team.name,
            target_team=target_team.name,
            reason=(
                "Transferências entre equipes devem "
                "ser avaliadas pelo supervisor principal."
            ),
        )


FINANCIAL_TEAM = TeamDefinition(
    name="financial_team",
    supervisor_node=(
        "financial_team_supervisor"
    ),
    members=(
        "financial_agent",
        "report_agent",
    ),
    description=(
        "Equipe responsável por diagnóstico, "
        "cálculos, histórico e relatórios financeiros."
    ),
    max_internal_handoffs=2,
)


KNOWLEDGE_TEAM = TeamDefinition(
    name="knowledge_team",
    supervisor_node=(
        "knowledge_team_supervisor"
    ),
    members=(
        "education_agent",
        "rag_agent",
    ),
    description=(
        "Equipe responsável por educação financeira "
        "e recuperação de conhecimento."
    ),
    max_internal_handoffs=2,
)


SUPPORT_TEAM = TeamDefinition(
    name="support_team",
    supervisor_node=(
        "support_team_supervisor"
    ),
    members=(
        "fallback_agent",
    ),
    description=(
        "Equipe responsável por solicitações "
        "desconhecidas ou fora das rotas principais."
    ),
    max_internal_handoffs=1,
)


DEFAULT_TEAM_REGISTRY = TeamRegistry(
    (
        FINANCIAL_TEAM,
        KNOWLEDGE_TEAM,
        SUPPORT_TEAM,
    )
)


__all__ = [
    "AgentName",
    "TeamName",
    "TeamSupervisorNode",
    "TeamHierarchyError",
    "TeamDefinition",
    "TeamTransferDecision",
    "TeamRegistry",
    "FINANCIAL_TEAM",
    "KNOWLEDGE_TEAM",
    "SUPPORT_TEAM",
    "DEFAULT_TEAM_REGISTRY",
]
