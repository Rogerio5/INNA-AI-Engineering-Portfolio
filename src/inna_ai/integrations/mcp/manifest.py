"""Manifesto corporativo do servidor MCP da INNA."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from inna_ai.tools.core.registry import ToolRegistry
from inna_ai.agents.registry.agent_registry import AgentRegistry

MCP_MANIFEST_SCHEMA_VERSION = "1.0.0"
MCP_MANIFEST_URI = "inna://mcp/manifest"


class MCPManifestError(RuntimeError):
    """Erro seguro de construção do manifesto MCP."""


def build_mcp_manifest(
    *,
    server_name: str,
    server_version: str,
    principal_binding: Mapping[str, str],
    agent_registry: AgentRegistry,
    tool_registry: ToolRegistry,
) -> dict[str, Any]:
    """
    Constrói o manifesto a partir dos registries oficiais.

    O binding recebido já deve ter sido validado pelo
    contrato MCP do servidor.
    """
    registered_tools = {
        definition.name
        for definition in (
            tool_registry.list_definitions()
        )
    }

    exposed_tools = set(
        principal_binding
    )

    unknown_tools = sorted(
        exposed_tools - registered_tools
    )

    if unknown_tools:
        raise MCPManifestError(
            "Manifesto MCP contém ferramentas "
            "não registradas: "
            f"{unknown_tools}"
        )

    tools: list[dict[str, Any]] = []

    for tool_name, principal in sorted(
        principal_binding.items()
    ):
        if not agent_registry.contains(
            principal
        ):
            raise MCPManifestError(
                "Manifesto MCP contém principal "
                "não registrado: "
                f"{principal}"
            )

        tool_definition = (
            tool_registry.get(
                tool_name
            )
        )

        agent_definition = (
            agent_registry.get(
                principal
            )
        )

        tools.append(
            {
                "name": tool_definition.name,
                "description": (
                    tool_definition.description
                ),
                "exposure": "mcp",
                "principal": principal,
                "principal_kind": (
                    agent_definition.kind
                ),
                "runtime": (
                    agent_definition.runtime
                ),
                "status": (
                    agent_definition.status
                ),
                "timeout_seconds": (
                    tool_definition.timeout_seconds
                ),
                "idempotent": (
                    tool_definition.idempotent
                ),
                "sensitive_output": (
                    tool_definition.sensitive_output
                ),
                "tags": sorted(
                    tool_definition.tags
                ),
                "input_schema": (
                    tool_definition
                    .input_model
                    .model_json_schema()
                ),
            }
        )

    return {
        "schema_version": (
            MCP_MANIFEST_SCHEMA_VERSION
        ),
        "server": {
            "name": server_name,
            "version": server_version,
            "transport_scope": "internal",
        },
        "registry_summary": {
            "tool_registry_count": (
                len(registered_tools)
            ),
            "mcp_exposed_tool_count": (
                len(exposed_tools)
            ),
            "internal_only_tool_count": (
                len(
                    registered_tools
                    - exposed_tools
                )
            ),
        },
        "tools": tools,
    }


__all__ = [
    "MCP_MANIFEST_SCHEMA_VERSION",
    "MCP_MANIFEST_URI",
    "MCPManifestError",
    "build_mcp_manifest",
]
