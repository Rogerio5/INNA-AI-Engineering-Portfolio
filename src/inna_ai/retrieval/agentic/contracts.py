"""
Contratos tipados do Agentic RAG da INNA.

Fases disponíveis:
- contratos do Query Planner;
- contratos do Router Agent;
- contratos de evidência e coleta segura.

Os modelos utilizam extra="forbid" para rejeitar
campos inesperados.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
)


class ResearchComplexity(StrEnum):
    SIMPLE = "simple"
    COMPLEX = "complex"


class ResearchSource(StrEnum):
    KNOWLEDGE_BASE = "knowledge_base"
    FINANCIAL_HISTORY = "financial_history"


class PlanGenerationMode(StrEnum):
    DETERMINISTIC = "deterministic"
    LLM = "llm"
    FALLBACK = "fallback"


class EvidenceCollectionStatus(StrEnum):
    COLLECTED = "collected"
    EMPTY = "empty"
    REJECTED = "rejected"


ALLOWED_TOOL_BY_SOURCE: dict[
    ResearchSource,
    str,
] = {
    ResearchSource.KNOWLEDGE_BASE: ("buscar_conhecimento_rag"),
    ResearchSource.FINANCIAL_HISTORY: ("consultar_historico_financeiro"),
}


class ResearchSubquery(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
    )

    step_id: str = Field(
        min_length=1,
        max_length=120,
        pattern=r"^[a-z][a-z0-9_]*$",
    )
    question: str = Field(
        min_length=3,
        max_length=4000,
    )
    source: ResearchSource
    tool_name: str = Field(
        min_length=1,
        max_length=120,
        pattern=r"^[a-z][a-z0-9_]*$",
    )
    priority: int = Field(
        default=50,
        ge=1,
        le=100,
    )
    required: bool = True
    top_k: int = Field(
        default=4,
        ge=1,
        le=10,
    )
    max_results: int = Field(
        default=5,
        ge=1,
        le=20,
    )

    @model_validator(mode="after")
    def validate_authorized_tool(self) -> Self:
        expected_tool = ALLOWED_TOOL_BY_SOURCE[self.source]

        if self.tool_name != expected_tool:
            raise ValueError("A ferramenta não corresponde à fonte autorizada.")

        return self


class ResearchPlan(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
    )

    original_question: str = Field(
        min_length=3,
        max_length=4000,
    )
    language: str = Field(
        default="pt",
        min_length=2,
        max_length=10,
    )
    complexity: ResearchComplexity
    rationale: str = Field(
        min_length=3,
        max_length=500,
    )
    subqueries: list[ResearchSubquery] = Field(
        min_length=1,
        max_length=8,
    )
    generation_mode: PlanGenerationMode
    requires_iteration: bool = False
    max_rounds: int = Field(
        default=2,
        ge=1,
        le=3,
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
    )

    @model_validator(mode="after")
    def validate_unique_step_ids(self) -> Self:
        step_ids = [item.step_id for item in self.subqueries]

        if len(step_ids) != len(set(step_ids)):
            raise ValueError("Os identificadores das subconsultas devem ser únicos.")

        return self


class EvidenceItem(BaseModel):
    """
    Evidência normalizada e rastreável.

    content armazena somente o trecho necessário.
    content_sha256 permite comprovar integridade sem
    repetir o conteúdo em logs ou auditorias.
    """

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
    )

    evidence_id: str = Field(
        min_length=1,
        max_length=180,
        pattern=r"^[a-z][a-z0-9_]*$",
    )
    step_id: str = Field(
        min_length=1,
        max_length=120,
        pattern=r"^[a-z][a-z0-9_]*$",
    )
    source: ResearchSource
    tool_name: str = Field(
        min_length=1,
        max_length=120,
        pattern=r"^[a-z][a-z0-9_]*$",
    )
    query: str = Field(
        min_length=3,
        max_length=4000,
    )
    content: str = Field(
        min_length=1,
        max_length=12000,
    )
    references: list[str] = Field(
        default_factory=list,
        max_length=20,
    )
    relevance_score: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
    )
    content_sha256: str = Field(
        min_length=64,
        max_length=64,
        pattern=r"^[a-f0-9]{64}$",
    )
    sensitive: bool = False
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        max_length=30,
    )

    @model_validator(mode="after")
    def validate_source_tool_mapping(self) -> Self:
        expected_tool = ALLOWED_TOOL_BY_SOURCE[self.source]

        if self.tool_name != expected_tool:
            raise ValueError(
                "A ferramenta da evidência não corresponde à fonte autorizada."
            )

        if self.source == ResearchSource.FINANCIAL_HISTORY and not self.sensitive:
            raise ValueError(
                "Evidências de histórico financeiro devem ser marcadas como sensíveis."
            )

        if self.source == ResearchSource.KNOWLEDGE_BASE and self.sensitive:
            raise ValueError(
                "Conhecimento educacional público não deve ser marcado como sensível."
            )

        return self


class EvidenceCollectionResult(BaseModel):
    """
    Resultado estruturado do Evidence Collector.

    A resposta gerada pela ferramenta é separada das
    evidências recuperadas para evitar circularidade:
    uma resposta do modelo não se torna evidência apenas
    por ter sido gerada.
    """

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
    )

    step: ResearchSubquery
    status: EvidenceCollectionStatus
    evidence: list[EvidenceItem] = Field(
        default_factory=list,
        max_length=30,
    )
    tool_answer: str = Field(
        default="",
        max_length=12000,
    )
    source_schema: str = Field(
        min_length=1,
        max_length=160,
    )
    output_sha256: str = Field(
        min_length=64,
        max_length=64,
        pattern=r"^[a-f0-9]{64}$",
    )
    raw_item_count: int = Field(
        default=0,
        ge=0,
        le=1000,
    )
    selected_count: int = Field(
        default=0,
        ge=0,
        le=30,
    )
    discarded_count: int = Field(
        default=0,
        ge=0,
        le=1000,
    )
    warnings: list[str] = Field(
        default_factory=list,
        max_length=30,
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        max_length=30,
    )

    @model_validator(mode="after")
    def validate_collection_integrity(self) -> Self:
        if self.selected_count != len(self.evidence):
            raise ValueError(
                "selected_count deve corresponder à quantidade de evidências."
            )

        if self.status == EvidenceCollectionStatus.COLLECTED and not self.evidence:
            raise ValueError(
                "Uma coleta concluída precisa possuir ao menos uma evidência."
            )

        if self.status == EvidenceCollectionStatus.EMPTY and self.evidence:
            raise ValueError("Uma coleta vazia não pode possuir evidências.")

        evidence_ids = [item.evidence_id for item in self.evidence]

        if len(evidence_ids) != len(set(evidence_ids)):
            raise ValueError("Os IDs das evidências devem ser únicos.")

        for item in self.evidence:
            if item.step_id != self.step.step_id:
                raise ValueError("A evidência não pertence à etapa informada.")

            if item.source != self.step.source:
                raise ValueError("A evidência não pertence à fonte da etapa.")

            if item.tool_name != self.step.tool_name:
                raise ValueError("A evidência não pertence à ferramenta da etapa.")

        return self


class SufficiencyDecision(StrEnum):
    SUFFICIENT = "sufficient"
    NEEDS_MORE_RESEARCH = "needs_more_research"
    INSUFFICIENT = "insufficient"


class EvidenceGapType(StrEnum):
    REQUIRED_STEP_MISSING = "required_step_missing"
    SOURCE_MISSING = "source_missing"
    EMPTY_COLLECTION = "empty_collection"
    REJECTED_COLLECTION = "rejected_collection"
    LOW_EVIDENCE_VOLUME = "low_evidence_volume"
    LOW_RELEVANCE = "low_relevance"
    MISSING_REFERENCES = "missing_references"
    SCORE_BELOW_THRESHOLD = "score_below_threshold"


class EvidenceGap(BaseModel):
    """
    Lacuna detectada durante a avaliação de suficiência.

    suggested_query contém apenas uma consulta de
    refinamento. Não contém cadeia de pensamento.
    """

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
    )

    gap_id: str = Field(
        min_length=1,
        max_length=160,
        pattern=r"^[a-z][a-z0-9_]*$",
    )
    gap_type: EvidenceGapType
    message: str = Field(
        min_length=3,
        max_length=1000,
    )
    severity: int = Field(
        ge=1,
        le=100,
    )
    step_id: str | None = Field(
        default=None,
        max_length=120,
    )
    source: ResearchSource | None = None
    suggested_query: str = Field(
        default="",
        max_length=1200,
    )


class SufficiencyAssessment(BaseModel):
    """
    Decisão estruturada sobre a suficiência da pesquisa.

    A pontuação sozinha não aprova a pesquisa. Também
    existem gates obrigatórios de etapas, fontes,
    relevância, referências e integridade.
    """

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    decision: SufficiencyDecision
    sufficient: bool
    score: float = Field(
        ge=0.0,
        le=1.0,
    )
    threshold: float = Field(
        ge=0.0,
        le=1.0,
    )
    required_step_completion: float = Field(
        ge=0.0,
        le=1.0,
    )
    source_coverage: float = Field(
        ge=0.0,
        le=1.0,
    )
    evidence_relevance: float = Field(
        ge=0.0,
        le=1.0,
    )
    reference_coverage: float = Field(
        ge=0.0,
        le=1.0,
    )
    evidence_quantity: float = Field(
        ge=0.0,
        le=1.0,
    )
    collection_quality: float = Field(
        ge=0.0,
        le=1.0,
    )
    evidence_count: int = Field(
        ge=0,
    )
    completed_required_steps: int = Field(
        ge=0,
    )
    total_required_steps: int = Field(
        ge=0,
    )
    covered_sources: list[ResearchSource] = Field(
        default_factory=list,
        max_length=10,
    )
    missing_sources: list[ResearchSource] = Field(
        default_factory=list,
        max_length=10,
    )
    gaps: list[EvidenceGap] = Field(
        default_factory=list,
        max_length=30,
    )
    reasons: list[str] = Field(
        default_factory=list,
        max_length=20,
    )
    retry_recommended: bool
    current_round: int = Field(
        ge=1,
        le=3,
    )
    max_rounds: int = Field(
        ge=1,
        le=3,
    )
    next_queries: list[str] = Field(
        default_factory=list,
        max_length=6,
    )
    metrics: dict[str, Any] = Field(
        default_factory=dict,
        max_length=30,
    )

    @model_validator(mode="after")
    def validate_decision_integrity(
        self,
    ) -> Self:
        decision_is_sufficient = self.decision == SufficiencyDecision.SUFFICIENT

        if self.sufficient != decision_is_sufficient:
            raise ValueError("A decisão e o campo sufficient estão inconsistentes.")

        if (
            self.retry_recommended
            and self.decision != SufficiencyDecision.NEEDS_MORE_RESEARCH
        ):
            raise ValueError(
                "Retry só pode ser recomendado quando a decisão exige mais pesquisa."
            )

        if self.retry_recommended and self.current_round >= self.max_rounds:
            raise ValueError("Retry não pode ser recomendado após o limite de rodadas.")

        if self.completed_required_steps > self.total_required_steps:
            raise ValueError(
                "A quantidade de etapas concluídas não pode superar o total."
            )

        return self


__all__ = [
    "ALLOWED_TOOL_BY_SOURCE",
    "EvidenceCollectionResult",
    "EvidenceCollectionStatus",
    "EvidenceItem",
    "PlanGenerationMode",
    "ResearchComplexity",
    "ResearchPlan",
    "ResearchSource",
    "ResearchSubquery",
    "EvidenceGap",
    "EvidenceGapType",
    "SufficiencyAssessment",
    "SufficiencyDecision",
]
