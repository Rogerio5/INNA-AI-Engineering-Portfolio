"""
Verificação determinística de suficiência do Agentic RAG.

O módulo mede:
- conclusão das etapas obrigatórias;
- cobertura das fontes;
- relevância das evidências;
- referências rastreáveis;
- quantidade de evidências;
- qualidade das coletas;
- possibilidade de uma nova rodada.

Este módulo não acessa Gemini, banco, rede ou RAG.
"""

from __future__ import annotations

import os
from collections import defaultdict
from typing import Any

from inna_ai.retrieval.agentic.contracts import EvidenceCollectionResult, EvidenceCollectionStatus, EvidenceGap, EvidenceGapType, EvidenceItem, ResearchComplexity, ResearchPlan, ResearchSource, ResearchSubquery, SufficiencyAssessment, SufficiencyDecision
from inna_ai.retrieval.agentic.evidence import deduplicate_evidence

SUFFICIENCY_VERSION = "4.0.0"

_SEVERE_WARNINGS = frozenset(
    {
        "inconsistent_history_output",
        "answer_without_retrieval_context",
        "retrieval_context_empty",
        "invalid_history_items_discarded",
    }
)


def _clamp(
    value: float,
) -> float:
    return max(
        0.0,
        min(1.0, float(value)),
    )


def _read_float_environment(
    name: str,
    default: float,
) -> float:
    try:
        value = float(str(os.getenv(name, default)).strip())
    except (TypeError, ValueError):
        value = default

    return _clamp(value)


def resolve_sufficiency_threshold(
    plan: ResearchPlan,
    explicit_threshold: float | None = None,
) -> float:
    if explicit_threshold is not None:
        return _clamp(explicit_threshold)

    if plan.complexity == ResearchComplexity.SIMPLE:
        return _read_float_environment(
            "INNA_AGENTIC_RAG_MIN_SUFFICIENCY_SIMPLE",
            0.66,
        )

    return _read_float_environment(
        "INNA_AGENTIC_RAG_MIN_SUFFICIENCY",
        0.74,
    )


def _minimum_relevance(
    plan: ResearchPlan,
) -> float:
    if plan.complexity == ResearchComplexity.SIMPLE:
        return _read_float_environment(
            "INNA_AGENTIC_RAG_MIN_RELEVANCE_SIMPLE",
            0.10,
        )

    return _read_float_environment(
        "INNA_AGENTIC_RAG_MIN_RELEVANCE",
        0.12,
    )


def _minimum_reference_coverage(
    plan: ResearchPlan,
) -> float:
    default = 0.50 if (plan.complexity == ResearchComplexity.SIMPLE) else 0.60

    return _read_float_environment(
        "INNA_AGENTIC_RAG_MIN_REFERENCE_COVERAGE",
        default,
    )


def _minimum_evidence_count(
    plan: ResearchPlan,
) -> int:
    required_steps = sum(item.required for item in plan.subqueries)

    if plan.complexity == ResearchComplexity.SIMPLE:
        return 1

    return max(
        2,
        required_steps,
    )


def _target_evidence_count(
    plan: ResearchPlan,
) -> int:
    minimum = _minimum_evidence_count(plan)

    if plan.complexity == ResearchComplexity.SIMPLE:
        return minimum

    return max(
        minimum,
        len(plan.subqueries) * 2,
    )


def _group_collections(
    collections: list[EvidenceCollectionResult],
) -> dict[
    str,
    list[EvidenceCollectionResult],
]:
    grouped: dict[
        str,
        list[EvidenceCollectionResult],
    ] = defaultdict(list)

    for collection in collections:
        grouped[collection.step.step_id].append(collection)

    return dict(grouped)


def _collected_evidence(
    collections: list[EvidenceCollectionResult],
) -> list[EvidenceItem]:
    evidence: list[EvidenceItem] = []

    for collection in collections:
        if collection.status != EvidenceCollectionStatus.COLLECTED:
            continue

        evidence.extend(collection.evidence)

    return deduplicate_evidence(evidence)


def _step_has_success(
    results: list[EvidenceCollectionResult],
) -> bool:
    return any(
        (item.status == EvidenceCollectionStatus.COLLECTED and bool(item.evidence))
        for item in results
    )


def _step_is_rejected(
    results: list[EvidenceCollectionResult],
) -> bool:
    return (
        bool(results)
        and not _step_has_success(results)
        and any(item.status == EvidenceCollectionStatus.REJECTED for item in results)
    )


def _step_is_empty(
    results: list[EvidenceCollectionResult],
) -> bool:
    return (
        bool(results)
        and not _step_has_success(results)
        and all(item.status == EvidenceCollectionStatus.EMPTY for item in results)
    )


def _step_max_relevance(
    step_id: str,
    evidence: list[EvidenceItem],
) -> float:
    values = [item.relevance_score for item in evidence if item.step_id == step_id]

    return max(
        values,
        default=0.0,
    )


def _calculate_source_coverage(
    required_sources: set[ResearchSource],
    evidence: list[EvidenceItem],
) -> tuple[
    float,
    set[ResearchSource],
]:
    covered_sources = {item.source for item in evidence}

    if not required_sources:
        return 1.0, covered_sources

    covered_required = required_sources.intersection(covered_sources)

    coverage = len(covered_required) / len(required_sources)

    return coverage, covered_sources


def _calculate_reference_coverage(
    evidence: list[EvidenceItem],
) -> float:
    if not evidence:
        return 0.0

    referenced = sum(bool(item.references) for item in evidence)

    return referenced / len(evidence)


def _calculate_collection_quality(
    *,
    required_step_ids: set[str],
    grouped: dict[
        str,
        list[EvidenceCollectionResult],
    ],
    collections: list[EvidenceCollectionResult],
) -> float:
    if not required_step_ids:
        return 1.0

    rejected_count = sum(
        _step_is_rejected(grouped.get(step_id, [])) for step_id in required_step_ids
    )

    empty_count = sum(
        _step_is_empty(grouped.get(step_id, [])) for step_id in required_step_ids
    )

    severe_warning_count = sum(
        warning in _SEVERE_WARNINGS
        for collection in collections
        for warning in collection.warnings
    )

    rejected_ratio = rejected_count / len(required_step_ids)
    empty_ratio = empty_count / len(required_step_ids)

    penalty = (
        0.25 * rejected_ratio
        + 0.15 * empty_ratio
        + min(
            0.25,
            severe_warning_count * 0.05,
        )
    )

    return _clamp(1.0 - penalty)


def _build_gap(
    *,
    index: int,
    gap_type: EvidenceGapType,
    message: str,
    severity: int,
    step_id: str | None = None,
    source: ResearchSource | None = None,
    suggested_query: str = "",
) -> EvidenceGap:
    return EvidenceGap(
        gap_id=(f"gap_{index:02d}_{gap_type.value}")[:160],
        gap_type=gap_type,
        message=message,
        severity=severity,
        step_id=step_id,
        source=source,
        suggested_query=(suggested_query[:1200]),
    )


def _step_contract_signature(
    step: ResearchSubquery,
) -> tuple[Any, ...]:
    """
    Produz uma assinatura completa e estável da etapa.

    O step_id isoladamente não é suficiente porque
    planos diferentes podem gerar IDs iguais, como
    step_01_knowledge.

    A assinatura não é registrada em logs e não expõe
    dados da pergunta em auditorias.
    """

    return (
        step.step_id,
        step.question,
        step.source.value,
        step.tool_name,
        step.priority,
        step.required,
        step.top_k,
        step.max_results,
    )


def assess_evidence_sufficiency(
    *,
    question: str,
    plan: ResearchPlan,
    collections: list[EvidenceCollectionResult],
    round_number: int = 1,
    threshold: float | None = None,
) -> SufficiencyAssessment:
    normalized_question = str(question or "").strip()

    if len(normalized_question) < 3:
        raise ValueError("A pergunta precisa possuir pelo menos três caracteres.")

    if not 1 <= int(round_number) <= 3:
        raise ValueError("round_number deve estar entre 1 e 3.")

    planned_step_ids = {item.step_id for item in plan.subqueries}

    collection_step_ids = {item.step.step_id for item in collections}

    unexpected_step_ids = collection_step_ids - planned_step_ids

    if unexpected_step_ids:
        raise ValueError(
            "Foram recebidas coletas de etapas que não pertencem ao plano."
        )

    planned_steps_by_id = {step.step_id: step for step in plan.subqueries}

    mismatched_step_ids: list[str] = []

    for collection in collections:
        planned_step = planned_steps_by_id.get(collection.step.step_id)

        if planned_step is None:
            continue

        collection_signature = _step_contract_signature(collection.step)
        planned_signature = _step_contract_signature(planned_step)

        if collection_signature != planned_signature:
            mismatched_step_ids.append(collection.step.step_id)

    if mismatched_step_ids:
        unique_mismatches = sorted(set(mismatched_step_ids))

        raise ValueError(
            "Foram recebidas coletas de etapas "
            "que não pertencem ao plano atual ou "
            "não correspondem ao contrato planejado. "
            "step_ids=" + ",".join(unique_mismatches)
        )

    effective_threshold = resolve_sufficiency_threshold(
        plan,
        threshold,
    )
    minimum_relevance = _minimum_relevance(plan)
    minimum_reference_coverage = _minimum_reference_coverage(plan)
    minimum_evidence_count = _minimum_evidence_count(plan)
    target_evidence_count = _target_evidence_count(plan)

    grouped = _group_collections(collections)
    evidence = _collected_evidence(collections)

    required_steps = [item for item in plan.subqueries if item.required]

    required_step_ids = {item.step_id for item in required_steps}

    completed_required_step_ids = {
        step_id
        for step_id in required_step_ids
        if _step_has_success(grouped.get(step_id, []))
    }

    required_step_completion = (
        len(completed_required_step_ids) / len(required_step_ids)
        if required_step_ids
        else 1.0
    )

    required_sources = {item.source for item in required_steps}

    (
        source_coverage,
        covered_sources,
    ) = _calculate_source_coverage(
        required_sources,
        evidence,
    )

    step_relevancies = [
        _step_max_relevance(
            item.step_id,
            evidence,
        )
        for item in required_steps
    ]

    evidence_relevance = (
        sum(step_relevancies) / len(step_relevancies) if step_relevancies else 0.0
    )

    reference_coverage = _calculate_reference_coverage(evidence)

    evidence_quantity = _clamp(
        len(evidence)
        / max(
            1,
            target_evidence_count,
        )
    )

    collection_quality = _calculate_collection_quality(
        required_step_ids=(required_step_ids),
        grouped=grouped,
        collections=collections,
    )

    score = (
        0.30 * required_step_completion
        + 0.15 * source_coverage
        + 0.20 * evidence_relevance
        + 0.15 * reference_coverage
        + 0.10 * evidence_quantity
        + 0.10 * collection_quality
    )

    score = round(
        _clamp(score),
        6,
    )

    gaps: list[EvidenceGap] = []
    gap_index = 1

    for step in required_steps:
        step_results = grouped.get(
            step.step_id,
            [],
        )

        if _step_has_success(step_results):
            continue

        if _step_is_rejected(step_results):
            gap_type = EvidenceGapType.REJECTED_COLLECTION
            message = (
                "A coleta obrigatória foi rejeitada por inconsistência ou segurança."
            )
            severity = 100

        elif _step_is_empty(step_results):
            gap_type = EvidenceGapType.EMPTY_COLLECTION
            message = "A etapa obrigatória foi executada, mas não produziu evidências."
            severity = 85

        else:
            gap_type = EvidenceGapType.REQUIRED_STEP_MISSING
            message = "A etapa obrigatória ainda não possui uma coleta válida."
            severity = 90

        gaps.append(
            _build_gap(
                index=gap_index,
                gap_type=gap_type,
                message=message,
                severity=severity,
                step_id=step.step_id,
                source=step.source,
                suggested_query=step.question,
            )
        )

        gap_index += 1

    for source in sorted(
        required_sources,
        key=lambda item: item.value,
    ):
        if source in covered_sources:
            continue

        gaps.append(
            _build_gap(
                index=gap_index,
                gap_type=(EvidenceGapType.SOURCE_MISSING),
                message=("A fonte obrigatória ainda não possui evidências válidas."),
                severity=85,
                source=source,
                suggested_query=(normalized_question),
            )
        )

        gap_index += 1

    if len(evidence) < minimum_evidence_count:
        gaps.append(
            _build_gap(
                index=gap_index,
                gap_type=(EvidenceGapType.LOW_EVIDENCE_VOLUME),
                message=("A quantidade de evidências está abaixo do mínimo exigido."),
                severity=75,
                suggested_query=(
                    normalized_question + " Recupere mais trechos "
                    "independentes e relevantes."
                ),
            )
        )

        gap_index += 1

    if evidence_relevance < minimum_relevance:
        gaps.append(
            _build_gap(
                index=gap_index,
                gap_type=(EvidenceGapType.LOW_RELEVANCE),
                message=("As evidências não cobrem diretamente a pergunta."),
                severity=80,
                suggested_query=(
                    normalized_question + " Foque nos termos e critérios "
                    "centrais da pergunta."
                ),
            )
        )

        gap_index += 1

    if reference_coverage < minimum_reference_coverage:
        gaps.append(
            _build_gap(
                index=gap_index,
                gap_type=(EvidenceGapType.MISSING_REFERENCES),
                message=("Parte das evidências não possui referência rastreável."),
                severity=70,
                suggested_query=(
                    normalized_question + " Recupere evidências com "
                    "fontes identificadas."
                ),
            )
        )

        gap_index += 1

    if score < effective_threshold:
        gaps.append(
            _build_gap(
                index=gap_index,
                gap_type=(EvidenceGapType.SCORE_BELOW_THRESHOLD),
                message=("A pontuação agregada ficou abaixo do limite configurado."),
                severity=65,
                suggested_query=(normalized_question),
            )
        )

    unresolved_rejected_required = any(
        _step_is_rejected(grouped.get(step_id, [])) for step_id in required_step_ids
    )

    critical_gates_passed = bool(
        required_step_completion == 1.0
        and source_coverage == 1.0
        and len(evidence) >= minimum_evidence_count
        and evidence_relevance >= minimum_relevance
        and reference_coverage >= minimum_reference_coverage
        and not unresolved_rejected_required
    )

    sufficient = bool(critical_gates_passed and score >= effective_threshold)

    retry_recommended = bool(not sufficient and int(round_number) < plan.max_rounds)

    if sufficient:
        decision = SufficiencyDecision.SUFFICIENT

    elif retry_recommended:
        decision = SufficiencyDecision.NEEDS_MORE_RESEARCH

    else:
        decision = SufficiencyDecision.INSUFFICIENT

    next_queries: list[str] = []

    for gap in sorted(
        gaps,
        key=lambda item: -item.severity,
    ):
        query = str(gap.suggested_query or "").strip()

        if query and query not in next_queries:
            next_queries.append(query)

        if len(next_queries) >= 6:
            break

    reasons = [
        (
            "Todas as etapas obrigatórias possuem evidências válidas."
            if required_step_completion == 1.0
            else ("Existem etapas obrigatórias sem evidências válidas.")
        ),
        (
            "Todas as fontes obrigatórias estão cobertas."
            if source_coverage == 1.0
            else ("Existem fontes obrigatórias sem cobertura.")
        ),
        (
            "A pontuação atingiu o limite de suficiência."
            if score >= effective_threshold
            else ("A pontuação ficou abaixo do limite de suficiência.")
        ),
    ]

    return SufficiencyAssessment(
        decision=decision,
        sufficient=sufficient,
        score=score,
        threshold=effective_threshold,
        required_step_completion=round(
            required_step_completion,
            6,
        ),
        source_coverage=round(
            source_coverage,
            6,
        ),
        evidence_relevance=round(
            evidence_relevance,
            6,
        ),
        reference_coverage=round(
            reference_coverage,
            6,
        ),
        evidence_quantity=round(
            evidence_quantity,
            6,
        ),
        collection_quality=round(
            collection_quality,
            6,
        ),
        evidence_count=len(evidence),
        completed_required_steps=len(completed_required_step_ids),
        total_required_steps=len(required_step_ids),
        covered_sources=sorted(
            covered_sources,
            key=lambda item: item.value,
        ),
        missing_sources=sorted(
            required_sources - covered_sources,
            key=lambda item: item.value,
        ),
        gaps=gaps,
        reasons=reasons,
        retry_recommended=(retry_recommended),
        current_round=int(round_number),
        max_rounds=plan.max_rounds,
        next_queries=next_queries,
        metrics={
            "sufficiency_version": (SUFFICIENCY_VERSION),
            "minimum_relevance": (minimum_relevance),
            "minimum_reference_coverage": (minimum_reference_coverage),
            "minimum_evidence_count": (minimum_evidence_count),
            "target_evidence_count": (target_evidence_count),
            "critical_gates_passed": (critical_gates_passed),
            "unresolved_rejected_required": (unresolved_rejected_required),
            "live_call_performed": False,
        },
    )


def assessment_to_audit_payload(
    assessment: SufficiencyAssessment,
) -> dict[str, Any]:
    """
    Gera auditoria sem pergunta, evidências,
    referências ou consultas de refinamento.
    """

    return {
        "event": ("agentic_rag_sufficiency_assessed"),
        "sufficiency_version": (SUFFICIENCY_VERSION),
        "decision": (assessment.decision.value),
        "sufficient": (assessment.sufficient),
        "score": assessment.score,
        "threshold": assessment.threshold,
        "evidence_count": (assessment.evidence_count),
        "required_step_completion": (assessment.required_step_completion),
        "source_coverage": (assessment.source_coverage),
        "evidence_relevance": (assessment.evidence_relevance),
        "reference_coverage": (assessment.reference_coverage),
        "collection_quality": (assessment.collection_quality),
        "gap_types": [item.gap_type.value for item in assessment.gaps],
        "retry_recommended": (assessment.retry_recommended),
        "current_round": (assessment.current_round),
        "max_rounds": (assessment.max_rounds),
        "next_query_count": len(assessment.next_queries),
        "content_logged": False,
    }


class SufficiencyEvaluator:
    """
    Fachada injetável e testável da avaliação.
    """

    def evaluate(
        self,
        *,
        question: str,
        plan: ResearchPlan,
        collections: list[EvidenceCollectionResult],
        round_number: int = 1,
        threshold: float | None = None,
    ) -> SufficiencyAssessment:
        return assess_evidence_sufficiency(
            question=question,
            plan=plan,
            collections=collections,
            round_number=round_number,
            threshold=threshold,
        )


__all__ = [
    "SUFFICIENCY_VERSION",
    "SufficiencyEvaluator",
    "assess_evidence_sufficiency",
    "assessment_to_audit_payload",
    "resolve_sufficiency_threshold",
]
