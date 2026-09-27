"""
Catálogo das ferramentas autorizadas da INNA.

O catálogo cria um novo ToolRegistry para cada runtime
ou teste, evitando compartilhamento acidental de estado.
"""

from __future__ import annotations

import os

from inna_ai.tools.communication_tools import criar_definicao_preparar_email_financeiro, criar_definicao_preparar_mensagem_telegram
from inna_ai.tools.core import ToolRegistry
from inna_ai.tools.financial_history_tools import criar_definicao_consultar_historico_financeiro
from inna_ai.tools.financial_tools import criar_definicao_calcular_diagnostico_financeiro
from inna_ai.tools.rag_tools import criar_definicao_buscar_conhecimento_rag
from inna_ai.tools.report_tools import criar_definicao_preparar_relatorio_financeiro

DEFAULT_RAG_TOOL_TIMEOUT_SECONDS = 20.0
DEFAULT_FINANCIAL_TOOL_TIMEOUT_SECONDS = 2.0


DEFAULT_FINANCIAL_HISTORY_TOOL_TIMEOUT_SECONDS = 15.0
DEFAULT_REPORT_PREPARATION_TOOL_TIMEOUT_SECONDS = 2.0

def _positive_float_environment(
    name: str,
    default: float,
) -> float:
    raw_value = str(
        os.getenv(name, "")
    ).strip()

    if not raw_value:
        return default

    try:
        value = float(raw_value)
    except (TypeError, ValueError):
        return default

    if value <= 0:
        return default

    return value


def criar_registro_ferramentas_inna(
) -> ToolRegistry:
    """
    Monta o catálogo completo de ferramentas.
    """
    registry = ToolRegistry()

    history_timeout = _positive_float_environment(
        "INNA_FINANCIAL_HISTORY_TOOL_TIMEOUT_SECONDS",
        DEFAULT_FINANCIAL_HISTORY_TOOL_TIMEOUT_SECONDS,
    )

    report_preparation_timeout = (
        _positive_float_environment(
            "INNA_REPORT_PREPARATION_TOOL_TIMEOUT_SECONDS",
            DEFAULT_REPORT_PREPARATION_TOOL_TIMEOUT_SECONDS,
        )
    )


    rag_timeout = _positive_float_environment(
        "INNA_RAG_TOOL_TIMEOUT_SECONDS",
        DEFAULT_RAG_TOOL_TIMEOUT_SECONDS,
    )

    financial_timeout = (
        _positive_float_environment(
            "INNA_FINANCIAL_TOOL_TIMEOUT_SECONDS",
            DEFAULT_FINANCIAL_TOOL_TIMEOUT_SECONDS,
        )
    )

    registry.register(
        criar_definicao_buscar_conhecimento_rag(
            timeout_seconds=rag_timeout,
        )
    )

    registry.register(
        criar_definicao_calcular_diagnostico_financeiro(
            timeout_seconds=financial_timeout,
        )
    )

    registry.register(
        criar_definicao_consultar_historico_financeiro(
            timeout_seconds=history_timeout,
        )
    )

    registry.register(
        criar_definicao_preparar_relatorio_financeiro(
            timeout_seconds=(
                report_preparation_timeout
            ),
        )
    )


    registry.register(
        criar_definicao_preparar_email_financeiro(
            timeout_seconds=2.0,
        )
    )

    registry.register(
        criar_definicao_preparar_mensagem_telegram(
            timeout_seconds=2.0,
        )
    )

    return registry


def obter_catalogo_schemas_ferramentas(
) -> list[dict]:
    """
    Retorna schemas para integração futura com
    Gemini Function Calling.
    """
    return (
        criar_registro_ferramentas_inna()
        .schema_catalog()
    )


__all__ = [
    "DEFAULT_FINANCIAL_TOOL_TIMEOUT_SECONDS",
    "DEFAULT_RAG_TOOL_TIMEOUT_SECONDS",
    "DEFAULT_FINANCIAL_HISTORY_TOOL_TIMEOUT_SECONDS",
    "DEFAULT_REPORT_PREPARATION_TOOL_TIMEOUT_SECONDS",
    "criar_registro_ferramentas_inna",
    "obter_catalogo_schemas_ferramentas",
]
