"""Planner determinístico enxuto para Agentic RAG."""

from __future__ import annotations

from inna_ai.retrieval.agentic.contracts import (
    ALLOWED_TOOL_BY_SOURCE,
    PlanGenerationMode,
    ResearchComplexity,
    ResearchPlan,
    ResearchSource,
    ResearchSubquery,
)


def create_research_plan(
    question: str,
    *,
    language: str = "pt",
    user_id: str | None = None,
    intent: str = "unknown",
    planner_mode: str | None = None,
    trace_id: str | None = None,
) -> ResearchPlan:
    """
    Cria plano seguro e determinístico sobre a
    base educacional pública.
    """
    normalized = str(
        question or ""
    ).strip()

    if len(normalized) < 3:
        raise ValueError(
            "A pergunta precisa possuir "
            "pelo menos três caracteres."
        )

    complexity = (
        ResearchComplexity.COMPLEX
        if (
            len(normalized) > 220
            or normalized.count("?") > 1
        )
        else ResearchComplexity.SIMPLE
    )

    source = (
        ResearchSource.KNOWLEDGE_BASE
    )

    step = ResearchSubquery(
        step_id="knowledge_base_1",
        question=normalized,
        source=source,
        tool_name=(
            ALLOWED_TOOL_BY_SOURCE[
                source
            ]
        ),
        priority=100,
        required=True,
        top_k=4,
        max_results=5,
    )

    return ResearchPlan(
        original_question=normalized,
        language=str(
            language or "pt"
        ).strip().lower(),
        complexity=complexity,
        rationale=(
            "Plano determinístico do portfólio "
            "para recuperação educacional."
        ),
        subqueries=[step],
        generation_mode=(
            PlanGenerationMode.DETERMINISTIC
        ),
        requires_iteration=False,
        max_rounds=1,
        metadata={
            "portfolio": True,
            "intent": str(intent),
            "planner_mode": (
                str(
                    planner_mode
                    or "deterministic"
                )
            ),
            "user_context_available":
                bool(user_id),
            "trace_available":
                bool(trace_id),
        },
    )


__all__ = [
    "create_research_plan",
]
