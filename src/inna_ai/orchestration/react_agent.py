"""ReAct governado da INNA.

O módulo não armazena chain-of-thought.
Registra somente ação, ferramenta, resultado e metadados seguros.

Fluxo:
decisão -> ferramenta autorizada -> Tool Runtime INNA -> observação
"""

from __future__ import annotations

from time import perf_counter
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

from inna_ai.tools.catalog import criar_registro_ferramentas_inna
from inna_ai.tools.core.contracts import ToolCall, ToolExecutionContext
from inna_ai.tools.runtime import executar_ferramenta_inna
from inna_ai.governance.react_privacy import safe_tool_observation


REACT_MAX_ITERATIONS = 5


REACT_FORBIDDEN_IDENTITY_ARGUMENTS = frozenset(
    {
        "user_id",
        "usuario_id",
        "tenant_id",
        "account_id",
        "organization_id",
        "company_id",
    }
)


# Fase inicial: somente ferramentas de baixo risco.
REACT_TOOL_BINDINGS: dict[str, str] = {
    "buscar_conhecimento_rag": "rag_agent",
    "calcular_diagnostico_financeiro": "financial_agent",
}


class ReactGovernanceError(RuntimeError):
    """Erro seguro da camada ReAct governada."""


class ReactAction(BaseModel):
    """Ação explícita solicitada pelo ReAct."""

    tool_name: str = Field(min_length=1)
    arguments: dict[str, Any] = Field(default_factory=dict)
    iteration: int = Field(ge=1, le=REACT_MAX_ITERATIONS)


class ReactObservation(BaseModel):
    """Observação segura produzida após uso de ferramenta."""

    trace_id: str
    tool_name: str
    requested_by: str
    iteration: int
    status: str
    duration_ms: float
    output: dict[str, Any] = Field(default_factory=dict)


_TOOL_REGISTRY = criar_registro_ferramentas_inna()


def _novo_trace_id() -> str:
    return f"react-{uuid4().hex}"


def ferramentas_react_disponiveis() -> list[dict[str, Any]]:
    """Retorna somente ferramentas autorizadas para o ReAct."""

    catalogo: list[dict[str, Any]] = []

    for tool_name, principal in sorted(
        REACT_TOOL_BINDINGS.items()
    ):
        if not _TOOL_REGISTRY.contains(tool_name):
            continue

        definition = _TOOL_REGISTRY.get(tool_name)

        if (
            principal not in definition.allowed_agents
            and "*" not in definition.allowed_agents
        ):
            continue

        catalogo.append(
            {
                "name": definition.name,
                "description": definition.description,
                "input_schema": (
                    definition.input_model.model_json_schema()
                ),
                "requested_by": principal,
                "timeout_seconds": definition.timeout_seconds,
                "idempotent": definition.idempotent,
                "sensitive_output": definition.sensitive_output,
            }
        )

    return catalogo


def executar_acao_react(
    action: ReactAction,
    *,
    parent_trace_id: str | None = None,
    user_id: str | None = None,
) -> ReactObservation:
    """Executa uma ação ReAct através do runtime oficial da INNA."""

    if action.iteration > REACT_MAX_ITERATIONS:
        raise ReactGovernanceError(
            "Limite máximo de iterações ReAct excedido."
        )

    normalized_argument_keys = {
        str(key).strip().lower()
        for key in action.arguments
    }

    if (
        normalized_argument_keys
        & REACT_FORBIDDEN_IDENTITY_ARGUMENTS
    ):
        raise ReactGovernanceError(
            "react_identity_override_blocked"
        )

    principal = REACT_TOOL_BINDINGS.get(
        action.tool_name
    )

    if principal is None:
        raise ReactGovernanceError(
            f"Ferramenta não autorizada para ReAct: "
            f"{action.tool_name}"
        )

    if not _TOOL_REGISTRY.contains(action.tool_name):
        raise ReactGovernanceError(
            f"Ferramenta não registrada: "
            f"{action.tool_name}"
        )

    definition = _TOOL_REGISTRY.get(
        action.tool_name
    )

    if (
        principal not in definition.allowed_agents
        and "*" not in definition.allowed_agents
    ):
        raise ReactGovernanceError(
            "Tool Registry recusou o principal "
            f"{principal} para {action.tool_name}."
        )

    trace_id = parent_trace_id or _novo_trace_id()

    context = ToolExecutionContext(
        requested_by=principal,
        user_id=(
            str(user_id).strip()
            if user_id
            else None
        ),
        trace_id=trace_id,
        metadata={
            "source": "react",
            "execution_mode": "governed_react",
            "iteration": action.iteration,
            "tool_name": action.tool_name,
        },
    )

    call = ToolCall(
        tool_name=action.tool_name,
        arguments=dict(action.arguments),
        context=context,
    )

    started_at = perf_counter()

    result = executar_ferramenta_inna(
        call,
    )

    duration_ms = (
        perf_counter() - started_at
    ) * 1000

    if result.output is None:
        error_code = "react_tool_execution_failed"

        if result.error is not None:
            error_code = str(
                getattr(
                    result.error,
                    "code",
                    error_code,
                )
            )

        raise ReactGovernanceError(
            f"{error_code}: ferramenta não executada."
        )

    return ReactObservation(
        trace_id=trace_id,
        tool_name=result.tool_name,
        requested_by=principal,
        iteration=action.iteration,
        status=str(
            getattr(
                result.status,
                "value",
                result.status,
            )
        ),
        duration_ms=float(
            getattr(
                result,
                "duration_ms",
                duration_ms,
            )
        ),
        output=safe_tool_observation(
            output=dict(result.output),
            sensitive_output=bool(
                definition.sensitive_output
            ),
        ),
    )


__all__ = [
    "REACT_MAX_ITERATIONS",
    "REACT_TOOL_BINDINGS",
    "ReactAction",
    "ReactGovernanceError",
    "ReactObservation",
    "executar_acao_react",
    "ferramentas_react_disponiveis",
]


