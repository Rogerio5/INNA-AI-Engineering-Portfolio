from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Literal

GEMINI_35_FLASH_LITE_MODEL = (
    "gemini-3.5-flash-lite"
)

PRICING_SNAPSHOT_DATE = "2026-08-09"

STANDARD_INPUT_USD_PER_1M = 0.30
STANDARD_OUTPUT_USD_PER_1M = 2.50

BillingMode = Literal[
    "free_tier",
    "paid_standard",
]

GEMINI_BILLING_MODE_ENV = (
    "INNA_GEMINI_BILLING_MODE"
)

DEFAULT_GEMINI_BILLING_MODE: BillingMode = (
    "free_tier"
)


def resolve_gemini_billing_mode(
    value: str | None = None,
) -> BillingMode:
    """
    Resolve o modo de billing usado pela INNA.

    Prioridade:
    1. valor explícito;
    2. INNA_GEMINI_BILLING_MODE;
    3. free_tier como default seguro.

    Valores desconhecidos são rejeitados para
    impedir contabilização financeira incorreta.
    """

    raw_value = value

    if raw_value is None:
        raw_value = os.getenv(
            GEMINI_BILLING_MODE_ENV,
            DEFAULT_GEMINI_BILLING_MODE,
        )

    normalized = str(
        raw_value
        or DEFAULT_GEMINI_BILLING_MODE
    ).strip().lower()

    if normalized == "free_tier":
        return "free_tier"

    if normalized == "paid_standard":
        return "paid_standard"

    raise ValueError(
        "INNA_GEMINI_BILLING_MODE inválido: "
        f"{raw_value!r}. "
        "Use 'free_tier' ou 'paid_standard'."
    )


@dataclass(frozen=True, slots=True)
class GeminiCostAccounting:
    model_name: str
    billing_mode: BillingMode

    input_tokens: int
    output_tokens: int
    total_tokens: int

    actual_billed_cost_usd: float
    paid_equivalent_cost_usd: float
    free_tier_savings_usd: float

    paid_input_rate_per_1m_usd: float
    paid_output_rate_per_1m_usd: float

    pricing_snapshot_date: str


def _validate_tokens(
    value: int,
    *,
    field_name: str,
) -> int:
    if isinstance(value, bool):
        raise TypeError(
            f"{field_name} deve ser inteiro."
        )

    resolved = int(value)

    if resolved != value:
        raise ValueError(
            f"{field_name} deve ser inteiro."
        )

    if resolved < 0:
        raise ValueError(
            f"{field_name} não pode ser negativo."
        )

    return resolved


def calculate_gemini_35_flash_lite_cost(
    *,
    input_tokens: int,
    output_tokens: int,
    billing_mode: BillingMode = "free_tier",
) -> GeminiCostAccounting:
    """
    Calcula custo faturado e custo equivalente.

    Free Tier:
    - custo faturado = zero;
    - custo equivalente usa a tabela Standard paga.

    Paid Standard:
    - custo faturado = custo calculado pela tabela Standard.

    O snapshot de preço fica registrado para permitir
    reprodutibilidade histórica dos benchmarks.
    """

    resolved_input = _validate_tokens(
        input_tokens,
        field_name="input_tokens",
    )

    resolved_output = _validate_tokens(
        output_tokens,
        field_name="output_tokens",
    )

    if billing_mode not in {
        "free_tier",
        "paid_standard",
    }:
        raise ValueError(
            f"billing_mode inválido: {billing_mode!r}."
        )

    input_equivalent = (
        resolved_input
        / 1_000_000
        * STANDARD_INPUT_USD_PER_1M
    )

    output_equivalent = (
        resolved_output
        / 1_000_000
        * STANDARD_OUTPUT_USD_PER_1M
    )

    paid_equivalent = (
        input_equivalent
        + output_equivalent
    )

    if billing_mode == "free_tier":
        actual_billed = 0.0
        savings = paid_equivalent
    else:
        actual_billed = paid_equivalent
        savings = 0.0

    return GeminiCostAccounting(
        model_name=GEMINI_35_FLASH_LITE_MODEL,
        billing_mode=billing_mode,
        input_tokens=resolved_input,
        output_tokens=resolved_output,
        total_tokens=(
            resolved_input
            + resolved_output
        ),
        actual_billed_cost_usd=(
            actual_billed
        ),
        paid_equivalent_cost_usd=(
            paid_equivalent
        ),
        free_tier_savings_usd=savings,
        paid_input_rate_per_1m_usd=(
            STANDARD_INPUT_USD_PER_1M
        ),
        paid_output_rate_per_1m_usd=(
            STANDARD_OUTPUT_USD_PER_1M
        ),
        pricing_snapshot_date=(
            PRICING_SNAPSHOT_DATE
        ),
    )


__all__ = [
    "BillingMode",
    "GEMINI_35_FLASH_LITE_MODEL",
    "GeminiCostAccounting",
    "PRICING_SNAPSHOT_DATE",
    "STANDARD_INPUT_USD_PER_1M",
    "STANDARD_OUTPUT_USD_PER_1M",
    "calculate_gemini_35_flash_lite_cost",
]
