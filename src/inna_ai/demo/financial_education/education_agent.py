"""
Modulo da Educadora Financeira da INNA.

A Educadora permanece desacoplada da implementacao interna do RAG.
Durante a refatoracao modular, utiliza o executor RAG compartilhado
existente no nucleo agentic.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from inna_ai.orchestration.state import InnaAgentState


def education_agent_node(
    state: "InnaAgentState",
) -> "InnaAgentState":
    """
    Agente de educacao financeira fundamentado no
    RAG hibrido e formal da INNA.
    """

    # Import tardio para evitar dependencia circular durante
    # a migracao gradual da arquitetura.
    from inna_ai.orchestration.nodes import _execute_rag_for_agent

    return _execute_rag_for_agent(
        state,
        agent="education_agent",
    )
