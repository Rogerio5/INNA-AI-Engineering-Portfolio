"""Contrato público de histórico financeiro.

O portfólio não acessa histórico financeiro real de clientes.
"""

from __future__ import annotations

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)

from inna_ai.tools.core import (
    ToolDefinition,
    ToolExecutionContext,
)


FINANCIAL_HISTORY_TOOL_NAME = (
    "consultar_historico_financeiro"
)

DEFAULT_HISTORY_LIMIT = 5
MAX_HISTORY_LIMIT = 20


class ConsultarHistoricoFinanceiroInput(
    BaseModel
):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    limite: int = Field(
        default=DEFAULT_HISTORY_LIMIT,
        ge=1,
        le=MAX_HISTORY_LIMIT,
    )


class HistoricoFinanceiroItem(
    BaseModel
):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    data_hora: str | None = None
    saldo_estimado: float | None = None

    comprometimento_renda_percentual: (
        float | None
    ) = None

    meses_reserva_estimados: (
        float | None
    ) = None

    score_financeiro: int | None = None
    nivel_risco: str | None = None
    moeda: str | None = None
    idioma: str | None = None


class ConsultarHistoricoFinanceiroOutput(
    BaseModel
):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    possui_historico: bool = False

    total_retornado: int = Field(
        default=0,
        ge=0,
        le=MAX_HISTORY_LIMIT,
    )

    diagnosticos: list[
        HistoricoFinanceiroItem
    ] = Field(
        default_factory=list,
        max_length=MAX_HISTORY_LIMIT,
    )


class FinancialHistoryToolExecutionError(
    RuntimeError
):
    pass


def executar_consulta_historico_financeiro(
    payload: ConsultarHistoricoFinanceiroInput,
    context: ToolExecutionContext,
) -> ConsultarHistoricoFinanceiroOutput:
    """
    Não consulta usuários ou banco real.

    Mantém somente o contrato necessário para demonstrar
    Tool Calling e autorização no portfólio público.
    """
    del payload
    del context

    return (
        ConsultarHistoricoFinanceiroOutput(
            possui_historico=False,
            total_retornado=0,
            diagnosticos=[],
        )
    )


def criar_definicao_consultar_historico_financeiro(
    *,
    timeout_seconds: float = 5.0,
) -> ToolDefinition:

    return ToolDefinition(
        name=(
            FINANCIAL_HISTORY_TOOL_NAME
        ),
        description=(
            "Contrato demonstrativo de histórico. "
            "O portfólio público não consulta "
            "dados financeiros reais."
        ),
        input_model=(
            ConsultarHistoricoFinanceiroInput
        ),
        output_model=(
            ConsultarHistoricoFinanceiroOutput
        ),
        handler=(
            executar_consulta_historico_financeiro
        ),
        allowed_agents=frozenset({
            "financial_agent",
            "report_agent",
            "research_agent",
        }),
        timeout_seconds=timeout_seconds,
        idempotent=True,
        sensitive_output=True,
        tags=frozenset({
            "portfolio",
            "demo_only",
            "no_customer_data",
        }),
    )


__all__ = [
    "FINANCIAL_HISTORY_TOOL_NAME",
    "DEFAULT_HISTORY_LIMIT",
    "MAX_HISTORY_LIMIT",
    "ConsultarHistoricoFinanceiroInput",
    "ConsultarHistoricoFinanceiroOutput",
    "HistoricoFinanceiroItem",
    "FinancialHistoryToolExecutionError",
    "criar_definicao_consultar_historico_financeiro",
    "executar_consulta_historico_financeiro",
]
