"""Preparação demonstrativa de relatório educacional."""

from __future__ import annotations

from typing import Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)

from inna_ai.tools.core import (
    ToolDefinition,
    ToolExecutionContext,
)


PREPARE_FINANCIAL_REPORT_TOOL_NAME = (
    "preparar_relatorio_financeiro"
)

MAX_REPORT_DIAGNOSES = 20
MAX_REPORT_RECOMMENDATIONS = 10


class RelatorioDiagnosticoItem(
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


class PrepararRelatorioFinanceiroInput(
    BaseModel
):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    diagnosticos: list[
        RelatorioDiagnosticoItem
    ] = Field(
        default_factory=list,
        max_length=MAX_REPORT_DIAGNOSES,
    )

    titulo: str = Field(
        default=(
            "Relatório Educacional INNA"
        ),
        min_length=1,
        max_length=120,
    )

    resumo_executivo: str | None = None

    recomendacoes: list[str] = Field(
        default_factory=list,
        max_length=MAX_REPORT_RECOMMENDATIONS,
    )

    proximos_passos: list[str] = Field(
        default_factory=list,
        max_length=MAX_REPORT_RECOMMENDATIONS,
    )

    idioma: str = "pt"


class PrepararRelatorioFinanceiroOutput(
    BaseModel
):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    titulo: str
    idioma: str
    possui_diagnostico: bool
    total_diagnosticos: int

    resumo_executivo: str
    recomendacoes: list[str]
    proximos_passos: list[str]

    financial_values_recalculated: bool = False
    ready_for_risk_review: bool = True
    ready_for_pdf_rendering: bool = False


class ReportPreparationError(
    RuntimeError
):
    pass


def _text(
    value: Any,
    default: str,
) -> str:

    normalized = str(
        value or ""
    ).strip()

    return (
        normalized
        or default
    )


def executar_preparacao_relatorio_financeiro(
    payload: PrepararRelatorioFinanceiroInput,
    context: ToolExecutionContext,
) -> PrepararRelatorioFinanceiroOutput:
    """
    Organiza dados fornecidos sem buscar dados externos
    e sem recalcular indicadores.
    """
    del context

    diagnostics = list(
        payload.diagnosticos
    )

    summary = _text(
        payload.resumo_executivo,
        (
            "Relatório educacional preparado "
            "com dados demonstrativos."
            if diagnostics
            else (
                "Nenhum diagnóstico demonstrativo "
                "foi fornecido."
            )
        ),
    )

    return (
        PrepararRelatorioFinanceiroOutput(
            titulo=_text(
                payload.titulo,
                "Relatório Educacional INNA",
            ),
            idioma=_text(
                payload.idioma,
                "pt",
            ),
            possui_diagnostico=bool(
                diagnostics
            ),
            total_diagnosticos=len(
                diagnostics
            ),
            resumo_executivo=summary,
            recomendacoes=list(
                payload.recomendacoes
            ),
            proximos_passos=list(
                payload.proximos_passos
            ),
            financial_values_recalculated=False,
            ready_for_risk_review=True,
            ready_for_pdf_rendering=False,
        )
    )


def criar_definicao_preparar_relatorio_financeiro(
    *,
    timeout_seconds: float = 2.0,
) -> ToolDefinition:

    return ToolDefinition(
        name=(
            PREPARE_FINANCIAL_REPORT_TOOL_NAME
        ),
        description=(
            "Organiza um relatório educacional "
            "demonstrativo. Não gera PDF e "
            "não acessa dados privados."
        ),
        input_model=(
            PrepararRelatorioFinanceiroInput
        ),
        output_model=(
            PrepararRelatorioFinanceiroOutput
        ),
        handler=(
            executar_preparacao_relatorio_financeiro
        ),
        allowed_agents=frozenset({
            "report_agent",
        }),
        timeout_seconds=timeout_seconds,
        idempotent=True,
        sensitive_output=True,
        tags=frozenset({
            "portfolio",
            "report",
            "no_customer_data",
        }),
    )


__all__ = [
    "PREPARE_FINANCIAL_REPORT_TOOL_NAME",
    "MAX_REPORT_DIAGNOSES",
    "MAX_REPORT_RECOMMENDATIONS",
    "RelatorioDiagnosticoItem",
    "PrepararRelatorioFinanceiroInput",
    "PrepararRelatorioFinanceiroOutput",
    "ReportPreparationError",
    "executar_preparacao_relatorio_financeiro",
    "criar_definicao_preparar_relatorio_financeiro",
]
