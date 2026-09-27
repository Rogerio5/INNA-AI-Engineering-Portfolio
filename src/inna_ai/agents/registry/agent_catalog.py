"""Catálogo corporativo de agentes da INNA."""

from __future__ import annotations

from dataclasses import dataclass

from inna_ai.tools.catalog import criar_registro_ferramentas_inna
from inna_ai.agents.registry.agent_registry import AgentDefinition, AgentRegistrationError, AgentRegistry
from inna_ai.agents.routing.team_hierarchy import DEFAULT_TEAM_REGISTRY


@dataclass(
    frozen=True,
    slots=True,
)
class AgentMetadata:
    """Metadados não derivados dos registries existentes."""

    description: str
    runtime: str
    capabilities: frozenset[str]
    version: str | None = None


_HIERARCHICAL_METADATA: dict[
    str,
    AgentMetadata,
] = {
    "financial_agent": AgentMetadata(
        description=(
            "Executa diagnóstico e operações "
            "financeiras estruturadas."
        ),
        runtime="langgraph",
        capabilities=frozenset(
            {
                "financial_diagnosis",
                "financial_history",
            }
        ),
    ),
    "report_agent": AgentMetadata(
        description=(
            "Prepara relatórios e entregáveis "
            "financeiros."
        ),
        runtime="langgraph",
        capabilities=frozenset(
            {
                "financial_history",
                "report_preparation",
                "email_preparation",
            }
        ),
    ),
    "education_agent": AgentMetadata(
        description=(
            "Fornece educação financeira "
            "baseada em conhecimento recuperado."
        ),
        runtime="langgraph",
        capabilities=frozenset(
            {
                "financial_education",
                "knowledge_retrieval",
            }
        ),
    ),
    "rag_agent": AgentMetadata(
        description=(
            "Executa recuperação formal de "
            "conhecimento da INNA."
        ),
        runtime="langgraph",
        capabilities=frozenset(
            {
                "knowledge_retrieval",
            }
        ),
    ),
    "fallback_agent": AgentMetadata(
        description=(
            "Executa o caminho seguro para "
            "solicitações não classificadas."
        ),
        runtime="langgraph",
        capabilities=frozenset(
            {
                "safe_fallback",
            }
        ),
    ),
}


_SPECIAL_METADATA: dict[
    str,
    AgentMetadata,
] = {
    "research_agent": AgentMetadata(
        description=(
            "Executa pesquisa agentic RAG "
            "especializada."
        ),
        runtime="agentic_rag",
        capabilities=frozenset(
            {
                "knowledge_retrieval",
                "financial_history",
                "agentic_research",
            }
        ),
        version="5.1.0",
    ),
    "communication_agent": AgentMetadata(
        description=(
            "Identidade operacional autorizada "
            "para ferramentas de comunicação."
        ),
        runtime="mcp",
        capabilities=frozenset(
            {
                "email_preparation",
                "telegram_preparation",
            }
        ),
    ),
}


def _allowed_tools_by_agent(
) -> dict[str, frozenset[str]]:
    """Deriva permissões diretamente do Tool Registry."""

    tool_registry = (
        criar_registro_ferramentas_inna()
    )

    mapping: dict[
        str,
        set[str],
    ] = {}

    for definition in (
        tool_registry.list_definitions()
    ):
        for agent_id in definition.allowed_agents:
            if agent_id == "*":
                continue

            mapping.setdefault(
                agent_id,
                set(),
            ).add(
                definition.name
            )

    return {
        agent_id: frozenset(
            tool_names
        )
        for agent_id, tool_names
        in mapping.items()
    }


def criar_registro_agentes_inna(
) -> AgentRegistry:
    """Monta o Agent Registry corporativo da INNA."""

    registry = AgentRegistry()

    allowed_tools = (
        _allowed_tools_by_agent()
    )

    hierarchical_agents = set(
        DEFAULT_TEAM_REGISTRY.agents
    )

    metadata_agents = set(
        _HIERARCHICAL_METADATA
    )

    if hierarchical_agents != metadata_agents:
        missing = sorted(
            hierarchical_agents
            - metadata_agents
        )

        unexpected = sorted(
            metadata_agents
            - hierarchical_agents
        )

        raise AgentRegistrationError(
            "Metadados hierárquicos inconsistentes. "
            f"missing={missing}; "
            f"unexpected={unexpected}"
        )

    known_identities = (
        hierarchical_agents
        | set(_SPECIAL_METADATA)
    )

    permission_identities = set(
        allowed_tools
    )

    unknown_permission_identities = sorted(
        permission_identities
        - known_identities
    )

    if unknown_permission_identities:
        raise AgentRegistrationError(
            "Tool Registry contém identidades "
            "não registradas: "
            f"{unknown_permission_identities}"
        )

    for agent_id in sorted(
        hierarchical_agents
    ):
        metadata = (
            _HIERARCHICAL_METADATA[
                agent_id
            ]
        )

        team = (
            DEFAULT_TEAM_REGISTRY
            .team_for_agent(
                agent_id
            )
        )

        supervisor = (
            DEFAULT_TEAM_REGISTRY
            .supervisor_for_agent(
                agent_id
            )
        )

        registry.register(
            AgentDefinition(
                agent_id=agent_id,
                description=(
                    metadata.description
                ),
                runtime=metadata.runtime,
                team=team.name,
                supervisor=supervisor,
                capabilities=(
                    metadata.capabilities
                ),
                allowed_tools=(
                    allowed_tools.get(
                        agent_id,
                        frozenset(),
                    )
                ),
                version=metadata.version,
            )
        )

    research_metadata = (
        _SPECIAL_METADATA[
            "research_agent"
        ]
    )

    registry.register(
        AgentDefinition(
            agent_id="research_agent",
            description=(
                research_metadata.description
            ),
            runtime=(
                research_metadata.runtime
            ),
            capabilities=(
                research_metadata.capabilities
            ),
            allowed_tools=(
                allowed_tools.get(
                    "research_agent",
                    frozenset(),
                )
            ),
            version=(
                research_metadata.version
            ),
        )
    )

    communication_metadata = (
        _SPECIAL_METADATA[
            "communication_agent"
        ]
    )

    registry.register(
        AgentDefinition(
            agent_id="communication_agent",
            description=(
                communication_metadata.description
            ),
            kind="service_identity",
            runtime=(
                communication_metadata.runtime
            ),
            capabilities=(
                communication_metadata.capabilities
            ),
            allowed_tools=(
                allowed_tools.get(
                    "communication_agent",
                    frozenset(),
                )
            ),
        )
    )

    return registry


DEFAULT_AGENT_REGISTRY = (
    criar_registro_agentes_inna()
)


def obter_catalogo_agentes_inna(
) -> list[dict[str, object]]:
    """Retorna catálogo serializável de discovery."""

    return (
        DEFAULT_AGENT_REGISTRY
        .schema_catalog()
    )


__all__ = [
    "DEFAULT_AGENT_REGISTRY",
    "AgentMetadata",
    "criar_registro_agentes_inna",
    "obter_catalogo_agentes_inna",
]
