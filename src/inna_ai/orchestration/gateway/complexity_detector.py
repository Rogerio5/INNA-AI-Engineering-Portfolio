"""Detector determinístico de complexidade de solicitações da INNA."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

RequestComplexity = Literal["simple", "complex"]


@dataclass(frozen=True)
class ComplexityAssessment:
    """Resultado estruturado da análise de complexidade."""

    complexity: RequestComplexity
    signals: tuple[str, ...]
    reason: str


def assess_request_complexity(
    *,
    user_message: str,
    intent: str,
    use_database: bool = False,
    use_rag: bool = False,
    generate_report: bool = False,
    handoff_required: bool = False,
    multi_domain: bool = False,
) -> ComplexityAssessment:
    """Avalia complexidade sem executar LLM.

    Usa somente sinais estruturais já produzidos pela arquitetura
    existente. Isso mantém a classificação barata e previsível.
    """

    del user_message

    normalized_intent = str(intent or "").strip()

    signals: list[str] = []

    if multi_domain:
        signals.append("multi_domain")

    if handoff_required:
        signals.append("handoff_required")

    if (
        generate_report
        and normalized_intent != "relatorio"
    ):
        signals.append("composite_report_workflow")

    if use_database and use_rag:
        signals.append("database_and_rag")

    if signals:
        return ComplexityAssessment(
            complexity="complex",
            signals=tuple(signals),
            reason="complexity_signals_detected",
        )

    return ComplexityAssessment(
        complexity="simple",
        signals=(),
        reason="single_capability_route",
    )


__all__ = [
    "ComplexityAssessment",
    "RequestComplexity",
    "assess_request_complexity",
]
