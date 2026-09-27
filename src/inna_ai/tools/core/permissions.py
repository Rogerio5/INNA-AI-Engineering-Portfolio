"""
Política de autorização das ferramentas.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from inna_ai.tools.core.registry import ToolDefinition


@dataclass(
    frozen=True,
    slots=True,
)
class ToolPermissionDecision:
    allowed: bool
    reason: str


@dataclass(slots=True)
class ToolPermissionPolicy:
    """
    Política deny-by-default.

    O agente precisa estar explicitamente autorizado,
    exceto quando a ferramenta permitir "*".
    """

    explicit_denials: dict[
        str,
        frozenset[str],
    ] = field(
        default_factory=dict,
    )

    def evaluate(
        self,
        *,
        agent_name: str,
        definition: ToolDefinition,
    ) -> ToolPermissionDecision:
        denied_tools = (
            self.explicit_denials.get(
                agent_name,
                frozenset(),
            )
        )

        if definition.name in denied_tools:
            return ToolPermissionDecision(
                allowed=False,
                reason="explicitly_denied",
            )

        if "*" in definition.allowed_agents:
            return ToolPermissionDecision(
                allowed=True,
                reason="wildcard_permission",
            )

        if agent_name in definition.allowed_agents:
            return ToolPermissionDecision(
                allowed=True,
                reason="agent_authorized",
            )

        return ToolPermissionDecision(
            allowed=False,
            reason="agent_not_authorized",
        )


__all__ = [
    "ToolPermissionDecision",
    "ToolPermissionPolicy",
]
