"""
Construtor principal de contexto da INNA.
"""

from __future__ import annotations

import json
from typing import Any

from inna_ai.context.history_selector import select_relevant_history
from inna_ai.context.privacy_filter import sanitize_sensitive_text
from inna_ai.context.schemas import BuiltAgentContext, ContextMetrics
from inna_ai.context.token_budget import create_context_budget, estimate_tokens, truncate_text_to_token_budget
from inna_ai.context.tool_selector import extract_unique_sources, select_tool_results


DEFAULT_CONTEXT_INSTRUCTIONS = [
    (
        "Responda apenas com informações necessárias "
        "para a solicitação atual."
    ),
    (
        "Não exponha dados pessoais ou informações "
        "internas da aplicação."
    ),
    (
        "Quando usar conhecimento recuperado, preserve "
        "a rastreabilidade das fontes."
    ),
    (
        "Não invente dados financeiros, valores, "
        "fontes ou ações executadas."
    ),
    (
        "Diferencie orientação educativa de decisão "
        "financeira pessoal."
    ),
]


def _sanitize_financial_profile(
    profile: dict[str, Any] | None,
) -> dict[str, Any]:
    if not isinstance(profile, dict):
        return {}

    allowed_fields = {
        "monthly_income",
        "fixed_expenses",
        "variable_expenses",
        "debts",
        "available_balance",
        "financial_goal",
        "risk_level",
        "knowledge_level",
        "preferred_language",
        "preferred_currency",
    }

    return {
        key: value
        for key, value in profile.items()
        if key in allowed_fields
        and value is not None
    }


def _context_to_serializable(
    context: BuiltAgentContext,
) -> dict[str, Any]:
    return context.model_dump()


def build_agent_context(
    *,
    current_message: str,
    conversation_history: (
        list[dict[str, Any]] | None
    ) = None,
    conversation_summary: str = "",
    financial_profile: (
        dict[str, Any] | None
    ) = None,
    tool_results: (
        list[dict[str, Any]] | None
    ) = None,
    language: str = "pt",
    currency: str = "BRL",
    max_context_tokens: int = 4000,
    reserved_output_tokens: int = 800,
    max_history_messages: int = 12,
) -> BuiltAgentContext:
    """
    Monta o contexto que será entregue ao agente.

    O histórico persistido permanece completo no banco,
    mas apenas uma seleção entra no prompt.
    """
    raw_current_message = str(
        current_message or ""
    ).strip()

    sanitized_current, current_privacy = (
        sanitize_sensitive_text(
            raw_current_message
        )
    )

    selected_history, history_privacy = (
        select_relevant_history(
            conversation_history,
            current_message=(
                raw_current_message
            ),
            max_messages=max_history_messages,
            max_tokens=1800,
            sanitize=True,
        )
    )

    selected_tools = select_tool_results(
        tool_results,
        max_results=8,
    )

    sources = extract_unique_sources(
        selected_tools,
        max_sources=12,
    )

    sanitized_summary, summary_privacy = (
        sanitize_sensitive_text(
            conversation_summary
        )
    )

    sanitized_summary = (
        truncate_text_to_token_budget(
            sanitized_summary,
            max_tokens=500,
        )
    )

    clean_profile = (
        _sanitize_financial_profile(
            financial_profile
        )
    )

    metrics = ContextMetrics(
        history_messages_received=len(
            conversation_history or []
        ),
        history_messages_selected=len(
            selected_history
        ),
        history_messages_removed=max(
            0,
            len(conversation_history or [])
            - len(selected_history),
        ),
        tool_results_received=len(
            tool_results or []
        ),
        tool_results_selected=len(
            selected_tools
        ),
        sources_received=sum(
            len(result.get("sources", []))
            if isinstance(
                result.get("sources", []),
                (list, tuple),
            )
            else 1
            for result in tool_results or []
            if isinstance(result, dict)
            and result.get("sources")
        ),
        sources_selected=len(sources),
        characters_before=sum(
            len(
                str(
                    message.get(
                        "content",
                        "",
                    )
                )
            )
            for message in conversation_history or []
            if isinstance(message, dict)
        ),
        privacy=history_privacy,
    )

    metrics.privacy.sensitive_items_found += (
        current_privacy.sensitive_items_found
        + summary_privacy.sensitive_items_found
    )

    metrics.privacy.email_addresses_masked += (
        current_privacy.email_addresses_masked
        + summary_privacy.email_addresses_masked
    )

    metrics.privacy.phone_numbers_masked += (
        current_privacy.phone_numbers_masked
        + summary_privacy.phone_numbers_masked
    )

    metrics.privacy.cpf_numbers_masked += (
        current_privacy.cpf_numbers_masked
        + summary_privacy.cpf_numbers_masked
    )

    metrics.privacy.card_numbers_masked += (
        current_privacy.card_numbers_masked
        + summary_privacy.card_numbers_masked
    )

    context = BuiltAgentContext(
        current_message=sanitized_current,
        language=str(
            language or "pt"
        ),
        currency=str(
            currency or "BRL"
        ),
        conversation_summary=(
            sanitized_summary
        ),
        selected_history=selected_history,
        financial_profile=clean_profile,
        selected_tool_results=(
            selected_tools
        ),
        sources=sources,
        instructions=list(
            DEFAULT_CONTEXT_INSTRUCTIONS
        ),
        metrics=metrics,
    )

    serialized = json.dumps(
        _context_to_serializable(context),
        ensure_ascii=False,
        default=str,
    )

    estimated_tokens = estimate_tokens(
        serialized
    )

    context.metrics.budget = (
        create_context_budget(
            max_tokens=max_context_tokens,
            reserved_output_tokens=(
                reserved_output_tokens
            ),
            estimated_input_tokens=(
                estimated_tokens
            ),
        )
    )

    context.metrics.characters_after = len(
        serialized
    )

    return context


def render_context_for_llm(
    context: BuiltAgentContext,
) -> str:
    """
    Converte o contexto estruturado em texto controlado.
    """
    history_lines = [
        (
            f"{message.role.upper()}: "
            f"{message.content}"
        )
        for message in context.selected_history
    ]

    tool_lines = [
        json.dumps(
            result,
            ensure_ascii=False,
            default=str,
        )
        for result in (
            context.selected_tool_results
        )
    ]

    sections = [
        "## INSTRUÇÕES",
        "\n".join(
            f"- {instruction}"
            for instruction in context.instructions
        ),
        "",
        "## CONFIGURAÇÃO",
        (
            f"Idioma: {context.language}\n"
            f"Moeda: {context.currency}"
        ),
    ]

    if context.conversation_summary:
        sections.extend(
            [
                "",
                "## RESUMO DA CONVERSA",
                context.conversation_summary,
            ]
        )

    if history_lines:
        sections.extend(
            [
                "",
                "## HISTÓRICO RELEVANTE",
                "\n".join(history_lines),
            ]
        )

    if context.financial_profile:
        sections.extend(
            [
                "",
                "## PERFIL FINANCEIRO RELEVANTE",
                json.dumps(
                    context.financial_profile,
                    ensure_ascii=False,
                    default=str,
                ),
            ]
        )

    if tool_lines:
        sections.extend(
            [
                "",
                "## RESULTADOS DAS FERRAMENTAS",
                "\n".join(tool_lines),
            ]
        )

    if context.sources:
        sections.extend(
            [
                "",
                "## FONTES DISPONÍVEIS",
                "\n".join(
                    f"- {source}"
                    for source in context.sources
                ),
            ]
        )

    sections.extend(
        [
            "",
            "## SOLICITAÇÃO ATUAL",
            context.current_message,
        ]
    )

    rendered = "\n".join(sections).strip()

    available_tokens = (
        context.metrics.budget
        .available_input_tokens
    )

    return truncate_text_to_token_budget(
        rendered,
        max_tokens=available_tokens,
    )


__all__ = [
    "DEFAULT_CONTEXT_INSTRUCTIONS",
    "build_agent_context",
    "render_context_for_llm",
]
