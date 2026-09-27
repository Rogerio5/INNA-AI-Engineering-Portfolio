"""
Nó LangGraph responsável pelo resumo incremental da thread.
"""

from __future__ import annotations

from typing import Any, Mapping

from inna_ai.orchestration.state import InnaAgentState
from inna_ai.memory.conversation_summary import update_conversation_summary_state


def conversation_summary_node(
    state: InnaAgentState,
) -> dict[str, Any]:
    """
    Atualiza o resumo conversacional após a execução do agente.

    O nó retorna somente os campos que precisam ser
    persistidos no checkpoint do LangGraph.
    """
    safe_state: dict[str, Any] = (
        dict(state)
        if isinstance(state, Mapping)
        else {}
    )

    previous_summary = str(
        safe_state.get(
            "conversation_summary",
            "",
        )
        or ""
    )

    summary_update = (
        update_conversation_summary_state(
            safe_state
        )
    )

    updated_summary = str(
        summary_update.get(
            "conversation_summary",
            "",
        )
        or ""
    )

    changed = (
        updated_summary != previous_summary
    )

    previous_version = int(
        safe_state.get(
            "conversation_summary_version",
            0,
        )
        or 0
    )

    version = (
        previous_version + 1
        if changed
        else previous_version
    )

    history = safe_state.get(
        "conversation_history",
        [],
    )

    source_messages = (
        len(history)
        if isinstance(history, list)
        else 0
    )

    trace = list(
        summary_update.get(
            "trace",
            safe_state.get("trace", []),
        )
        or []
    )

    trace.append(
        "conversation_summary_node:"
        + (
            f"updated:v{version}"
            if changed
            else f"unchanged:v{version}"
        )
    )

    return {
        "conversation_summary": (
            updated_summary
        ),
        "conversation_summary_updated": (
            changed
        ),
        "conversation_summary_version": (
            version
        ),
        "conversation_summary_source_messages": (
            source_messages
        ),
        "conversation_summary_source": (
            "conversation_history"
        ),
        "trace": trace,
    }


__all__ = [
    "conversation_summary_node",
]
