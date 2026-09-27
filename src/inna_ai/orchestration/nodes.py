"""Nós públicos e desacoplados do portfólio INNA."""

from __future__ import annotations

from inna_ai.orchestration.state import InnaAgentState


def rag_agent_node(
    state: InnaAgentState,
) -> InnaAgentState:
    """Executa o RAG Agent canônico do portfólio."""
    from inna_ai.orchestration.gateway.rag_agent import (
        _execute_rag_for_agent,
    )

    return _execute_rag_for_agent(
        state,
        agent="rag_agent",
    )


def report_agent_node(
    state: InnaAgentState,
) -> InnaAgentState:
    """
    Nó demonstrativo de relatório.

    Mantém somente a superfície necessária para o
    portfólio público, sem regras comerciais de relatório.
    """
    result = dict(state or {})

    trace = list(
        result.get("trace", [])
    )

    trace.append(
        "agent:report_agent:portfolio_demo"
    )

    structured = dict(
        result.get(
            "structured_response",
            {},
        )
    )

    structured["portfolio_report"] = {
        "status": "prepared",
        "scope": "financial_education_demo",
        "commercial_rules": False,
    }

    summary = str(
        result.get("response")
        or (
            "Relatório educacional demonstrativo "
            "preparado a partir do estado do agente."
        )
    ).strip()

    result.update(
        {
            "response": summary,
            "structured_response": structured,
            "trace": trace,
        }
    )

    return result


__all__ = [
    "rag_agent_node",
    "report_agent_node",
]
