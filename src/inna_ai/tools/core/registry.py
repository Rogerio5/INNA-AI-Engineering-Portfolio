"""
Registro central das ferramentas autorizadas da INNA.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
import re
from typing import Any

from pydantic import BaseModel

from inna_ai.tools.core.contracts import ToolExecutionContext


ToolHandler = Callable[
    [BaseModel, ToolExecutionContext],
    BaseModel | dict[str, Any],
]


class ToolRegistrationError(RuntimeError):
    """Erro de registro de ferramenta."""


class ToolNotFoundError(KeyError):
    """Ferramenta não encontrada."""


@dataclass(
    frozen=True,
    slots=True,
)
class ToolDefinition:
    """
    Definição completa de uma ferramenta autorizada.
    """

    name: str
    description: str

    input_model: type[BaseModel]
    output_model: type[BaseModel]

    handler: ToolHandler

    allowed_agents: frozenset[str]

    timeout_seconds: float = 10.0
    idempotent: bool = True
    sensitive_output: bool = False

    tags: frozenset[str] = field(
        default_factory=frozenset,
    )

    def __post_init__(self) -> None:
        if not re.fullmatch(
            r"[a-z][a-z0-9_]*",
            self.name,
        ):
            raise ToolRegistrationError(
                "O nome da ferramenta deve usar "
                "snake_case."
            )

        if not self.description.strip():
            raise ToolRegistrationError(
                "A descrição da ferramenta é "
                "obrigatória."
            )

        if not issubclass(
            self.input_model,
            BaseModel,
        ):
            raise ToolRegistrationError(
                "input_model deve herdar de BaseModel."
            )

        if not issubclass(
            self.output_model,
            BaseModel,
        ):
            raise ToolRegistrationError(
                "output_model deve herdar de BaseModel."
            )

        if not callable(self.handler):
            raise ToolRegistrationError(
                "handler deve ser executável."
            )

        if not self.allowed_agents:
            raise ToolRegistrationError(
                "A ferramenta deve possuir pelo "
                "menos um agente autorizado."
            )

        if self.timeout_seconds <= 0:
            raise ToolRegistrationError(
                "timeout_seconds deve ser positivo."
            )


class ToolRegistry:
    """
    Catálogo explícito de ferramentas.

    Nenhuma função pode ser executada sem estar registrada.
    """

    def __init__(self) -> None:
        self._tools: dict[
            str,
            ToolDefinition,
        ] = {}

    def register(
        self,
        definition: ToolDefinition,
        *,
        replace: bool = False,
    ) -> ToolDefinition:
        if (
            definition.name in self._tools
            and not replace
        ):
            raise ToolRegistrationError(
                f"Ferramenta já registrada: "
                f"{definition.name}"
            )

        self._tools[
            definition.name
        ] = definition

        return definition

    def get(
        self,
        name: str,
    ) -> ToolDefinition:
        try:
            return self._tools[name]
        except KeyError as exc:
            raise ToolNotFoundError(
                name
            ) from exc

    def contains(
        self,
        name: str,
    ) -> bool:
        return name in self._tools

    def list_definitions(
        self,
    ) -> tuple[ToolDefinition, ...]:
        return tuple(
            self._tools[name]
            for name in sorted(self._tools)
        )

    def schema_catalog(
        self,
    ) -> list[dict[str, Any]]:
        """
        Catálogo serializável para integração posterior
        com Gemini Function Calling.
        """
        return [
            {
                "name": definition.name,
                "description": (
                    definition.description
                ),
                "input_schema": (
                    definition
                    .input_model
                    .model_json_schema()
                ),
                "allowed_agents": sorted(
                    definition.allowed_agents
                ),
                "timeout_seconds": (
                    definition.timeout_seconds
                ),
                "idempotent": (
                    definition.idempotent
                ),
                "sensitive_output": (
                    definition.sensitive_output
                ),
                "tags": sorted(
                    definition.tags
                ),
            }
            for definition in (
                self.list_definitions()
            )
        ]


__all__ = [
    "ToolDefinition",
    "ToolHandler",
    "ToolNotFoundError",
    "ToolRegistrationError",
    "ToolRegistry",
]
