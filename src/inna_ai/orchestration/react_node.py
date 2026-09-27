"""Nó LangGraph do ReAct governado da INNA."""

from __future__ import annotations

from typing import Any

from inna_ai.orchestration.react_loop import executar_loop_react
from inna_ai.orchestration.state import InnaAgentState


def react_agent_node(
    state: InnaAgentState,
) -> dict[str, Any]:
    """
    Executa o ciclo ReAct governado.

    Só executa quando react_enabled=True.
    """

    if not bool(
        state.get(
            "react_enabled",
            False,
        )
    ):
        return {
            "react_status": "disabled",
        }

    user_message = str(
        state.get(
            "user_message",
            "",
        )
        or ""
    ).strip()

    if not user_message:
        return {
            "react_status": "blocked",
            "human_review_force_required": True,
        }

    history = state.get(
        "react_history",
        [],
    )

    if not isinstance(
        history,
        list,
    ):
        history = []

    trace_id = str(
        state.get(
            "trace_id",
            "",
        )
        or ""
    ).strip()

    result = executar_loop_react(
        user_message=user_message,
        history=history,
        parent_trace_id=(
            trace_id or None
        ),
        usuario_id=str(
            state.get(
                "user_id",
                state.get("usuario_id", ""),
            )
            or ""
        ).strip() or None,
        request_id=str(
            state.get(
                "request_id",
                "",
            )
            or ""
        ).strip() or None,
    )

    trace = list(
        state.get(
            "trace",
            [],
        )
        or []
    )

    trace.append(
        "react:"
        f"{result.get('react_status', 'unknown')}:"
        f"{result.get('react_iteration', 0)}"
    )

    result["trace"] = trace

    return result


__all__ = [
    "react_agent_node",
]

