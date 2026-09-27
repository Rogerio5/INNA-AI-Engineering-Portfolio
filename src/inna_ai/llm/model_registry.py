"""
Registro central dos modelos de linguagem da INNA.

Cada agente possui sua própria variável de ambiente,
mesmo quando todos utilizam inicialmente o mesmo modelo.
"""

from __future__ import annotations

from enum import Enum
from functools import lru_cache
import os


DEFAULT_TEXT_MODEL = (
    "gemini-2.5-flash-lite"
)


class LLMRole(str, Enum):
    DEFAULT = "default"
    SUPERVISOR = "supervisor"
    EDUCATION = "education"
    RAG = "rag"
    REPORT = "report"
    FINANCIAL_EXPLANATION = (
        "financial_explanation"
    )


MODEL_ENV_BY_ROLE: dict[LLMRole, str] = {
    LLMRole.DEFAULT: "GEMINI_MODEL",
    LLMRole.SUPERVISOR: (
        "INNA_SUPERVISOR_MODEL"
    ),
    LLMRole.EDUCATION: (
        "INNA_EDUCATION_MODEL"
    ),
    LLMRole.RAG: "INNA_RAG_MODEL",
    LLMRole.REPORT: "INNA_REPORT_MODEL",
    LLMRole.FINANCIAL_EXPLANATION: (
        "INNA_FINANCIAL_EXPLANATION_MODEL"
    ),
}


def _normalize_model_name(
    value: str | None,
) -> str:
    return str(value or "").strip()


@lru_cache(maxsize=None)
def get_model_for_role(
    role: LLMRole | str,
) -> str:
    """
    Resolve o modelo aplicando esta prioridade:

    1. variável específica do agente;
    2. variável global GEMINI_MODEL;
    3. modelo padrão da aplicação.
    """
    normalized_role = (
        role
        if isinstance(role, LLMRole)
        else LLMRole(str(role))
    )

    specific_environment = (
        MODEL_ENV_BY_ROLE[
            normalized_role
        ]
    )

    specific_model = _normalize_model_name(
        os.getenv(
            specific_environment
        )
    )

    if specific_model:
        return specific_model

    global_model = _normalize_model_name(
        os.getenv("GEMINI_MODEL")
    )

    if global_model:
        return global_model

    return DEFAULT_TEXT_MODEL


def get_model_registry(
) -> dict[str, str]:
    """
    Retorna a configuração resolvida de todos os agentes.
    """
    return {
        role.value: get_model_for_role(role)
        for role in LLMRole
    }


def reset_model_registry_cache() -> None:
    """
    Limpa o cache após alterações de ambiente ou testes.
    """
    get_model_for_role.cache_clear()


__all__ = [
    "DEFAULT_TEXT_MODEL",
    "LLMRole",
    "MODEL_ENV_BY_ROLE",
    "get_model_for_role",
    "get_model_registry",
    "reset_model_registry_cache",
]
