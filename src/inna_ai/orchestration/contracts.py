"""
Schemas estruturados usados pelo núcleo de agentes da INNA.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


AgentIntent = Literal[
    "diagnostico_financeiro",
    "historico_financeiro",
    "educacao_financeira",
    "consulta_rag",
    "relatorio",
    "desconhecido",
]

AgentNode = Literal[
    "financial_agent",
    "education_agent",
    "rag_agent",
    "report_agent",
    "fallback_agent",
]

ClassificationSource = Literal[
    "rule",
    "gemini",
    "fallback",
]


class SupervisorDecision(BaseModel):
    """
    Decisão final e validada do supervisor híbrido.
    """

    intent: AgentIntent
    next_node: AgentNode

    confidence: float = Field(
        ge=0.0,
        le=1.0,
    )

    use_rag: bool = False
    use_database: bool = False
    generate_report: bool = False

    reason: str = Field(
        min_length=3,
        max_length=500,
    )

    classification_source: ClassificationSource = (
        "rule"
    )

    classification_duration_ms: int = Field(
        default=0,
        ge=0,
    )

    gemini_called: bool = False
    fallback_used: bool = False

    classification_error: str | None = None


class SupervisorLLMDecision(BaseModel):
    """
    Estrutura restrita que pode ser produzida pelo Gemini.

    Métricas, erros e fonte da classificação são
    adicionados pela aplicação.
    """

    intent: AgentIntent
    next_node: AgentNode

    confidence: float = Field(
        ge=0.0,
        le=1.0,
    )

    use_rag: bool = False
    use_database: bool = False
    generate_report: bool = False

    reason: str = Field(
        min_length=3,
        max_length=500,
    )


class AgentResponse(BaseModel):
    agent: str
    intent: AgentIntent

    summary: str

    recommendations: list[str] = Field(
        default_factory=list
    )

    next_steps: list[str] = Field(
        default_factory=list
    )

    sources: list[str] = Field(
        default_factory=list
    )

    confidence: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
    )


class AgentExecutionResult(BaseModel):
    ok: bool

    response: AgentResponse | None = None

    errors: list[str] = Field(
        default_factory=list
    )

    trace: list[str] = Field(
        default_factory=list
    )


__all__ = [
    "AgentIntent",
    "AgentNode",
    "ClassificationSource",
    "SupervisorDecision",
    "SupervisorLLMDecision",
    "AgentResponse",
    "AgentExecutionResult",
]
