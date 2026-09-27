"""
Orçamento de contexto da INNA.
"""

from __future__ import annotations

import json
import math
from typing import Any

from inna_ai.context.schemas import ContextBudget


DEFAULT_MAX_CONTEXT_TOKENS = 4000
DEFAULT_RESERVED_OUTPUT_TOKENS = 800
AVERAGE_CHARACTERS_PER_TOKEN = 4


def estimate_tokens(
    value: Any,
) -> int:
    """
    Estima tokens por quantidade de caracteres.

    Utilizado apenas para controle preventivo de orçamento.
    """
    if value is None:
        return 0

    if isinstance(value, str):
        text = value
    else:
        try:
            text = json.dumps(
                value,
                ensure_ascii=False,
                default=str,
            )
        except (TypeError, ValueError):
            text = str(value)

    if not text:
        return 0

    return max(
        1,
        math.ceil(
            len(text)
            / AVERAGE_CHARACTERS_PER_TOKEN
        ),
    )


def create_context_budget(
    *,
    max_tokens: int = DEFAULT_MAX_CONTEXT_TOKENS,
    reserved_output_tokens: int = (
        DEFAULT_RESERVED_OUTPUT_TOKENS
    ),
    estimated_input_tokens: int = 0,
) -> ContextBudget:
    max_tokens = max(256, int(max_tokens))
    reserved_output_tokens = max(
        0,
        int(reserved_output_tokens),
    )

    available_input_tokens = max(
        128,
        max_tokens - reserved_output_tokens,
    )

    estimated_input_tokens = max(
        0,
        int(estimated_input_tokens),
    )

    utilization = (
        estimated_input_tokens
        / available_input_tokens
        * 100
    )

    return ContextBudget(
        max_tokens=max_tokens,
        reserved_output_tokens=(
            reserved_output_tokens
        ),
        available_input_tokens=(
            available_input_tokens
        ),
        estimated_input_tokens=(
            estimated_input_tokens
        ),
        within_budget=(
            estimated_input_tokens
            <= available_input_tokens
        ),
        utilization_percent=round(
            utilization,
            2,
        ),
    )


def truncate_text_to_token_budget(
    text: str,
    *,
    max_tokens: int,
) -> str:
    text = str(text or "").strip()

    if not text:
        return ""

    max_tokens = max(1, int(max_tokens))

    if estimate_tokens(text) <= max_tokens:
        return text

    max_characters = (
        max_tokens
        * AVERAGE_CHARACTERS_PER_TOKEN
    )

    if max_characters <= 20:
        return text[:max_characters]

    return (
        text[: max_characters - 15].rstrip()
        + " [TRUNCADO]"
    )


__all__ = [
    "DEFAULT_MAX_CONTEXT_TOKENS",
    "DEFAULT_RESERVED_OUTPUT_TOKENS",
    "estimate_tokens",
    "create_context_budget",
    "truncate_text_to_token_budget",
]
