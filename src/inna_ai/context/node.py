"""
Nó LangGraph responsável por construir contexto.
"""

from __future__ import annotations

from inna_ai.orchestration.state import InnaAgentState
from inna_ai.context.context_builder import build_agent_context, render_context_for_llm


def context_builder_node(
    state: InnaAgentState,
) -> dict:
    """
    Prepara contexto antes do supervisor.
    """
    existing_context = state.get(
        "context",
        {},
    )

    if not isinstance(
        existing_context,
        dict,
    ):
        existing_context = {}

    financial_profile = (
        existing_context.get(
            "financial_profile",
            {},
        )
    )

    built_context = build_agent_context(
        current_message=state.get(
            "user_message",
            "",
        ),
        conversation_history=state.get(
            "conversation_history",
            [],
        ),
        conversation_summary=state.get(
            "conversation_summary",
            "",
        ),
        financial_profile=financial_profile,
        tool_results=state.get(
            "tool_results",
            [],
        ),
        language=state.get(
            "language",
            "pt",
        ),
        currency=state.get(
            "currency",
            "BRL",
        ),
        max_context_tokens=4000,
        reserved_output_tokens=800,
        max_history_messages=12,
    )

    context_payload = (
        built_context.model_dump()
    )

    context_payload["rendered_prompt"] = (
        render_context_for_llm(
            built_context
        )
    )

    context_payload[
        "financial_profile"
    ] = financial_profile

    return {
        "context": context_payload,
        "trace": [
            (
                "context_builder:"
                f"{len(built_context.selected_history)}"
                "_messages"
            )
        ],
    }


__all__ = [
    "context_builder_node",
]
