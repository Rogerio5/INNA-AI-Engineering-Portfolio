"""Ferramenta financeira educacional do portfólio.

As regras comerciais da plataforma Sabino.AI não fazem
parte deste módulo.
"""

from __future__ import annotations

from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)

from inna_ai.tools.core import (
    ToolDefinition,
    ToolExecutionContext,
)


FINANCIAL_DIAGNOSIS_TOOL_NAME = (
    "calcular_diagnostico_financeiro"
)

MAX_MONETARY_VALUE = (
    1_000_000_000_000.0
)


class FinancialToolInvariantError(
    RuntimeError
):
    pass


class CalcularDiagnosticoFinanceiroInput(
    BaseModel
):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        allow_inf_nan=False,
    )

    renda_mensal: float = Field(
        ge=0,
        le=MAX_MONETARY_VALUE,
    )

    gastos_fixos: float = Field(
        ge=0,
        le=MAX_MONETARY_VALUE,
    )

    gastos_variaveis: float = Field(
        ge=0,
        le=MAX_MONETARY_VALUE,
    )

    dividas_mensais: float = Field(
        default=0,
        ge=0,
        le=MAX_MONETARY_VALUE,
    )

    reserva_atual: float = Field(
        default=0,
        ge=0,
        le=MAX_MONETARY_VALUE,
    )

    gastos_incluem_dividas: bool = False

    moeda: str = Field(
        default="BRL",
        min_length=3,
        max_length=3,
    )

    idioma: str = Field(
        default="pt",
        min_length=2,
        max_length=10,
    )


class CalcularDiagnosticoFinanceiroOutput(
    BaseModel
):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        allow_inf_nan=False,
    )

    renda_mensal: float
    gastos_fixos: float
    gastos_variaveis: float
    dividas_mensais: float
    reserva_atual: float

    moeda: str
    idioma: str

    gastos_incluem_dividas: bool

    despesas_totais: float
    saldo_estimado: float

    comprometimento_renda_percentual: float
    meses_reserva_estimados: float

    score_financeiro: int = Field(
        ge=0,
        le=100,
    )

    nivel_risco: Literal[
        "Baixo",
        "Medio",
        "Alto",
    ]

    situacao: Literal[
        "sem_renda_informada",
        "deficit",
        "equilibrio_sem_margem",
        "saldo_positivo",
    ]

    tem_saldo_positivo: bool

    parcelas_adicionais_consideradas: float

    base_calculo: str = (
        "portfolio_education_demo"
    )

    versao_regra: str = (
        "portfolio_education_v1"
    )


def executar_calculo_diagnostico_financeiro(
    payload: CalcularDiagnosticoFinanceiroInput,
    context: ToolExecutionContext,
) -> CalcularDiagnosticoFinanceiroOutput:
    """
    Exemplo determinístico e transparente.

    Não representa regra de crédito, recomendação de
    investimento ou motor financeiro comercial.
    """
    del context

    additional_debt = (
        0.0
        if payload.gastos_incluem_dividas
        else payload.dividas_mensais
    )

    expenses = (
        payload.gastos_fixos
        + payload.gastos_variaveis
        + additional_debt
    )

    balance = (
        payload.renda_mensal
        - expenses
    )

    if payload.renda_mensal > 0:
        commitment = (
            expenses
            / payload.renda_mensal
            * 100.0
        )
    else:
        commitment = 0.0

    reserve_months = (
        payload.reserva_atual
        / expenses
        if expenses > 0
        else 0.0
    )

    if payload.renda_mensal <= 0:
        situation = (
            "sem_renda_informada"
        )
    elif balance < -0.01:
        situation = "deficit"
    elif abs(balance) <= 0.01:
        situation = (
            "equilibrio_sem_margem"
        )
    else:
        situation = (
            "saldo_positivo"
        )

    score = int(
        round(
            max(
                0.0,
                min(
                    100.0,
                    100.0
                    - min(
                        commitment,
                        100.0,
                    ),
                ),
            )
        )
    )

    if (
        situation
        == "sem_renda_informada"
        or situation
        == "deficit"
    ):
        risk = "Alto"
    elif score >= 60:
        risk = "Baixo"
    elif score >= 35:
        risk = "Medio"
    else:
        risk = "Alto"

    return (
        CalcularDiagnosticoFinanceiroOutput(
            renda_mensal=round(
                payload.renda_mensal,
                2,
            ),
            gastos_fixos=round(
                payload.gastos_fixos,
                2,
            ),
            gastos_variaveis=round(
                payload.gastos_variaveis,
                2,
            ),
            dividas_mensais=round(
                payload.dividas_mensais,
                2,
            ),
            reserva_atual=round(
                payload.reserva_atual,
                2,
            ),
            moeda=(
                payload.moeda.upper()
            ),
            idioma=payload.idioma,
            gastos_incluem_dividas=(
                payload.gastos_incluem_dividas
            ),
            despesas_totais=round(
                expenses,
                2,
            ),
            saldo_estimado=round(
                balance,
                2,
            ),
            comprometimento_renda_percentual=round(
                commitment,
                2,
            ),
            meses_reserva_estimados=round(
                reserve_months,
                2,
            ),
            score_financeiro=score,
            nivel_risco=risk,
            situacao=situation,
            tem_saldo_positivo=(
                balance > 0
            ),
            parcelas_adicionais_consideradas=round(
                additional_debt,
                2,
            ),
        )
    )


def criar_definicao_calcular_diagnostico_financeiro(
    *,
    timeout_seconds: float = 2.0,
) -> ToolDefinition:

    return ToolDefinition(
        name=(
            FINANCIAL_DIAGNOSIS_TOOL_NAME
        ),
        description=(
            "Demonstra cálculo financeiro "
            "educacional determinístico. "
            "Não utiliza regras comerciais."
        ),
        input_model=(
            CalcularDiagnosticoFinanceiroInput
        ),
        output_model=(
            CalcularDiagnosticoFinanceiroOutput
        ),
        handler=(
            executar_calculo_diagnostico_financeiro
        ),
        allowed_agents=frozenset({
            "financial_agent",
        }),
        timeout_seconds=timeout_seconds,
        idempotent=True,
        sensitive_output=True,
        tags=frozenset({
            "portfolio",
            "financial_education",
            "deterministic",
        }),
    )


__all__ = [
    "CalcularDiagnosticoFinanceiroInput",
    "CalcularDiagnosticoFinanceiroOutput",
    "FINANCIAL_DIAGNOSIS_TOOL_NAME",
    "FinancialToolInvariantError",
    "criar_definicao_calcular_diagnostico_financeiro",
    "executar_calculo_diagnostico_financeiro",
]
