"""Agente financeiro educacional do portfólio público."""

from __future__ import annotations

from inna_ai.orchestration.contracts import (
    AgentResponse,
)
from inna_ai.orchestration.state import (
    InnaAgentState,
)


_ALLOWED_INTENTS = {
    "diagnostico_financeiro",
    "historico_financeiro",
    "educacao_financeira",
    "consulta_rag",
    "relatorio",
    "desconhecido",
}


def financial_agent_node(
    state: InnaAgentState,
) -> InnaAgentState:
    """
    Demonstra a integração de um agente financeiro
    sem carregar regras comerciais da Sabino.AI.
    """
    result = dict(
        state or {}
    )

    intent = str(
        result.get(
            "intent",
            "educacao_financeira",
        )
    )

    if intent not in _ALLOWED_INTENTS:
        intent = "desconhecido"

    response = AgentResponse(
        agent="financial_agent",
        intent=intent,
        summary=(
            "Modo educacional do portfólio: "
            "a análise financeira comercial completa "
            "não faz parte deste repositório público."
        ),
        recommendations=[
            (
                "Use os recursos de educação financeira "
                "e RAG para explorar conceitos e cenários."
            )
        ],
        next_steps=[
            (
                "Forneça uma pergunta educacional "
                "para consultar a base de conhecimento."
            )
        ],
        confidence=0.80,
    )

    trace = list(
        result.get(
            "trace",
            [],
        )
    )

    trace.append(
        "agent:financial_agent:educational_demo"
    )

    structured = dict(
        result.get(
            "structured_response",
            {},
        )
    )

    structured[
        "financial_education_demo"
    ] = {
        "commercial_rules": False,
        "agent_response":
            response.model_dump(),
    }

    result.update(
        {
            "response":
                response.summary,
            "structured_response":
                structured,
            "trace":
                trace,
        }
    )

    return result


__all__ = [
    "financial_agent_node",
]
