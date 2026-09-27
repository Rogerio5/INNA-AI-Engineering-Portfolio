"""Registro corporativo de agentes e identidades da INNA."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

AgentKind = Literal[
    "agent",
    "service_identity",
]

AgentStatus = Literal[
    "active",
    "inactive",
]


class AgentRegistrationError(
    ValueError
):
    """Erro de configuração do Agent Registry."""


class AgentNotFoundError(
    KeyError
):
    """Agente não encontrado no Agent Registry."""


@dataclass(
    frozen=True,
    slots=True,
)
class AgentDefinition:
    """Contrato formal de um agente ou identidade operacional."""

    agent_id: str
    description: str

    kind: AgentKind = "agent"
    status: AgentStatus = "active"

    runtime: str = "langgraph"

    team: str | None = None
    supervisor: str | None = None

    capabilities: frozenset[str] = field(
        default_factory=frozenset,
    )

    allowed_tools: frozenset[str] = field(
        default_factory=frozenset,
    )

    version: str | None = None

    def __post_init__(
        self,
    ) -> None:
        if not re.fullmatch(
            r"[a-z][a-z0-9_]*",
            self.agent_id,
        ):
            raise AgentRegistrationError(
                "agent_id deve usar snake_case."
            )

        if not self.description.strip():
            raise AgentRegistrationError(
                "description é obrigatória."
            )

        if not self.runtime.strip():
            raise AgentRegistrationError(
                "runtime é obrigatório."
            )

        if (
            self.kind == "service_identity"
            and (
                self.team is not None
                or self.supervisor is not None
            )
        ):
            raise AgentRegistrationError(
                "service_identity não pode declarar "
                "team ou supervisor sem hierarquia formal."
            )

        if (
            self.team is None
            and self.supervisor is not None
        ):
            raise AgentRegistrationError(
                "supervisor exige team."
            )

        if (
            self.team is not None
            and self.supervisor is None
        ):
            raise AgentRegistrationError(
                "team exige supervisor."
            )


class AgentRegistry:
    """Catálogo explícito e validado de agentes da INNA."""

    def __init__(
        self,
    ) -> None:
        self._agents: dict[
            str,
            AgentDefinition,
        ] = {}

    def register(
        self,
        definition: AgentDefinition,
        *,
        replace: bool = False,
    ) -> AgentDefinition:
        if (
            definition.agent_id
            in self._agents
            and not replace
        ):
            raise AgentRegistrationError(
                "Agente já registrado: "
                f"{definition.agent_id}"
            )

        self._agents[
            definition.agent_id
        ] = definition

        return definition

    def get(
        self,
        agent_id: str,
    ) -> AgentDefinition:
        try:
            return self._agents[
                agent_id
            ]
        except KeyError as exc:
            raise AgentNotFoundError(
                agent_id
            ) from exc

    def contains(
        self,
        agent_id: str,
    ) -> bool:
        return agent_id in self._agents

    def list_definitions(
        self,
        *,
        active_only: bool = False,
    ) -> tuple[
        AgentDefinition,
        ...,
    ]:
        definitions = (
            self._agents[agent_id]
            for agent_id
            in sorted(self._agents)
        )

        if active_only:
            return tuple(
                definition
                for definition
                in definitions
                if definition.status
                == "active"
            )

        return tuple(
            definitions
        )

    def find_by_capability(
        self,
        capability: str,
        *,
        active_only: bool = True,
        kind: AgentKind | None = "agent",
    ) -> tuple[
        AgentDefinition,
        ...,
    ]:
        normalized = str(
            capability or ""
        ).strip()

        if not normalized:
            return ()

        return tuple(
            definition
            for definition
            in self.list_definitions(
                active_only=active_only
            )
            if (
                normalized
                in definition.capabilities
                and (
                    kind is None
                    or definition.kind == kind
                )
            )
        )

    def schema_catalog(
        self,
    ) -> list[dict[str, object]]:
        """Retorna catálogo serializável para discovery."""

        return [
            {
                "agent_id": definition.agent_id,
                "description": definition.description,
                "kind": definition.kind,
                "status": definition.status,
                "runtime": definition.runtime,
                "team": definition.team,
                "supervisor": definition.supervisor,
                "capabilities": sorted(
                    definition.capabilities
                ),
                "allowed_tools": sorted(
                    definition.allowed_tools
                ),
                "version": definition.version,
            }
            for definition
            in self.list_definitions()
        ]


__all__ = [
    "AgentDefinition",
    "AgentKind",
    "AgentNotFoundError",
    "AgentRegistrationError",
    "AgentRegistry",
    "AgentStatus",
]
