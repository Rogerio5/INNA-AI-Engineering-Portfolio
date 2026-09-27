"""
Evidence Collector profissional do Agentic RAG.

Responsabilidades:
- receber somente saídas das ferramentas governadas;
- converter os contratos reais em EvidenceItem;
- preservar proveniência;
- gerar IDs e hashes determinísticos;
- calcular relevância lexical;
- remover evidências duplicadas;
- remover identidade e campos não autorizados;
- separar respostas geradas de evidências recuperadas;
- detectar saídas inconsistentes.

O collector não acessa diretamente:
- Gemini;
- PostgreSQL ou Neon;
- RAG;
- rede;
- arquivos do usuário.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import (
    Mapping,
    Sequence,
)
from typing import Any

from inna_ai.retrieval.agentic.contracts import EvidenceCollectionResult, EvidenceCollectionStatus, EvidenceItem, ResearchSource, ResearchSubquery
from inna_ai.retrieval.agentic.evidence import canonical_output_sha256, content_sha256, deduplicate_evidence, lexical_relevance

COLLECTOR_VERSION = "3.0.0"

_MAX_CONTENT_LENGTH = 12000
_MAX_REFERENCE_LENGTH = 500
_MAX_REFERENCES = 20
_MAX_EVIDENCE_ITEMS = 30

_FORBIDDEN_IDENTITY_FIELDS = frozenset(
    {
        "user_id",
        "usuario_id",
        "usuario",
        "nome",
        "email",
        "cpf",
        "telefone",
        "phone",
        "session_id",
        "thread_id",
        "trace_id",
        "token",
        "access_token",
        "refresh_token",
        "senha",
        "password",
    }
)

_HISTORY_ALLOWED_FIELDS = (
    "data_hora",
    "saldo_estimado",
    "comprometimento_renda_percentual",
    "meses_reserva_estimados",
    "score_financeiro",
    "nivel_risco",
    "situacao",
    "moeda",
    "idioma",
)


class EvidenceCollectionError(RuntimeError):
    """
    Falha segura na conversão de uma saída em evidência.
    """


class UnsupportedEvidenceSourceError(EvidenceCollectionError):
    """
    A fonte solicitada não possui coletor autorizado.
    """


class UnsafeToolOutputError(EvidenceCollectionError):
    """
    A saída recebida possui estrutura inválida ou perigosa.
    """


def _to_mapping(
    value: Any,
) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)

    model_dump = getattr(
        value,
        "model_dump",
        None,
    )

    if callable(model_dump):
        dumped = model_dump(mode="python")

        if isinstance(dumped, Mapping):
            return dict(dumped)

    raise UnsafeToolOutputError(
        "A saída da ferramenta precisa ser um mapeamento ou modelo Pydantic."
    )


def _to_optional_mapping(
    value: Any,
) -> dict[str, Any] | None:
    try:
        return _to_mapping(value)
    except UnsafeToolOutputError:
        return None


def _safe_text(
    value: Any,
    *,
    maximum_length: int,
) -> str:
    text = str(value or "")

    text = "".join(
        character
        for character in text
        if character in ("\n", "\t") or ord(character) >= 32
    )

    return text.strip()[:maximum_length]


def _text_list(
    value: Any,
    *,
    maximum_items: int = 100,
    maximum_length: int = _MAX_CONTENT_LENGTH,
    deduplicate: bool = True,
) -> list[str]:
    """
    Converte uma saída em uma lista de textos seguros.

    Contextos recuperados podem preservar duplicidades
    para que a camada formal de deduplicação consiga:

    - registrar métricas;
    - emitir avisos;
    - comparar proveniência;
    - calcular a quantidade realmente descartada.

    Referências e outros campos podem continuar usando
    deduplicate=True.
    """

    if isinstance(value, str):
        raw_items: Sequence[Any] = [value]

    elif isinstance(
        value,
        (list, tuple),
    ):
        raw_items = value

    else:
        raw_items = []

    normalized: list[str] = []

    for item in raw_items[:maximum_items]:
        text = _safe_text(
            item,
            maximum_length=maximum_length,
        )

        if not text:
            continue

        if deduplicate and text in normalized:
            continue

        normalized.append(text)

    return normalized


def _safe_reference(
    value: Any,
) -> str:
    text = _safe_text(
        value,
        maximum_length=(_MAX_REFERENCE_LENGTH),
    )

    text = " ".join(text.split())

    return text


def _safe_int(
    value: Any,
    *,
    default: int = 0,
    minimum: int = 0,
    maximum: int = 1_000_000,
) -> int:
    if isinstance(value, bool):
        return default

    try:
        normalized = int(value)
    except (TypeError, ValueError):
        return default

    return max(
        minimum,
        min(maximum, normalized),
    )


def _build_evidence_id(
    *,
    step: ResearchSubquery,
    content: str,
    references: list[str],
    index: int,
) -> str:
    serialized = json.dumps(
        {
            "step_id": step.step_id,
            "source": step.source.value,
            "tool_name": step.tool_name,
            "content": content,
            "references": references,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )

    digest = hashlib.sha256(
        serialized.encode(
            "utf-8",
            errors="replace",
        )
    ).hexdigest()[:20]

    source_token = (
        "knowledge" if (step.source == ResearchSource.KNOWLEDGE_BASE) else "history"
    )

    return (f"ev_{source_token}_{index:02d}_{digest}")[:180]


def _select_references(
    references: list[str],
    *,
    item_index: int,
    item_count: int,
) -> list[str]:
    if not references:
        return []

    if len(references) == item_count:
        return [references[item_index]]

    return references[:_MAX_REFERENCES]


def _build_evidence(
    *,
    step: ResearchSubquery,
    content: str,
    references: list[str],
    index: int,
    sensitive: bool,
    metadata: dict[str, Any],
    minimum_relevance: float = 0.0,
) -> EvidenceItem:
    normalized_content = _safe_text(
        content,
        maximum_length=(_MAX_CONTENT_LENGTH),
    )

    if not normalized_content:
        raise UnsafeToolOutputError("Não é possível criar uma evidência vazia.")

    safe_references = [
        reference
        for reference in (_safe_reference(item) for item in references)
        if reference
    ][:_MAX_REFERENCES]

    relevance = max(
        float(minimum_relevance),
        lexical_relevance(
            step.question,
            normalized_content,
        ),
    )

    relevance = round(
        min(1.0, relevance),
        6,
    )

    return EvidenceItem(
        evidence_id=_build_evidence_id(
            step=step,
            content=normalized_content,
            references=safe_references,
            index=index,
        ),
        step_id=step.step_id,
        source=step.source,
        tool_name=step.tool_name,
        query=step.question,
        content=normalized_content,
        references=safe_references,
        relevance_score=relevance,
        content_sha256=content_sha256(normalized_content),
        sensitive=sensitive,
        metadata={
            "collector_version": (COLLECTOR_VERSION),
            **metadata,
        },
    )


def collect_rag_evidence(
    *,
    step: ResearchSubquery,
    output: Any,
    call_id: str | None = None,
    duration_ms: float | None = None,
) -> EvidenceCollectionResult:
    if step.source != ResearchSource.KNOWLEDGE_BASE:
        raise UnsupportedEvidenceSourceError(
            "O coletor RAG recebeu uma fonte incompatível."
        )

    mapping = _to_mapping(output)

    contexts = _text_list(
        mapping.get(
            "contexto_recuperado",
            mapping.get(
                "retrieval_context",
                [],
            ),
        ),
        maximum_items=100,
        deduplicate=False,
    )

    references = _text_list(
        mapping.get(
            "fontes",
            mapping.get(
                "sources",
                [],
            ),
        ),
        maximum_items=100,
        maximum_length=(_MAX_REFERENCE_LENGTH),
    )

    tool_answer = _safe_text(
        mapping.get(
            "resposta",
            mapping.get(
                "answer",
                "",
            ),
        ),
        maximum_length=(_MAX_CONTENT_LENGTH),
    )

    mode = _safe_text(
        mapping.get(
            "modo",
            mapping.get(
                "mode",
                "unknown",
            ),
        ),
        maximum_length=120,
    )

    retrieved_documents = _safe_int(
        mapping.get(
            "documentos_recuperados",
            mapping.get(
                "retrieved_documents",
                len(contexts),
            ),
        )
    )

    reported_duration_ms = _safe_int(
        mapping.get(
            "duracao_rag_ms",
            mapping.get(
                "duration_ms",
                duration_ms or 0,
            ),
        ),
        maximum=86_400_000,
    )

    raw_item_count = len(contexts)
    maximum_selected = min(
        _MAX_EVIDENCE_ITEMS,
        step.top_k,
    )

    collected: list[EvidenceItem] = []

    for index, content in enumerate(
        contexts[:maximum_selected],
    ):
        item_references = _select_references(
            references,
            item_index=index,
            item_count=len(contexts),
        )

        collected.append(
            _build_evidence(
                step=step,
                content=content,
                references=item_references,
                index=index,
                sensitive=False,
                metadata={
                    "collector": ("rag_retrieval_context_v1"),
                    "context_index": index,
                    "retrieval_mode": mode,
                    "reported_documents": (retrieved_documents),
                    "reported_duration_ms": (reported_duration_ms),
                    "call_id": _safe_text(
                        call_id,
                        maximum_length=100,
                    ),
                    "answer_used_as_evidence": False,
                },
            )
        )

    evidence = deduplicate_evidence(collected)

    warnings: list[str] = []

    if not contexts:
        warnings.append("retrieval_context_empty")

    if tool_answer and not contexts:
        warnings.append("answer_without_retrieval_context")

    if retrieved_documents and retrieved_documents != raw_item_count:
        warnings.append("document_count_context_count_mismatch")

    if len(evidence) < len(collected):
        warnings.append("duplicate_evidence_removed")

    if raw_item_count > maximum_selected:
        warnings.append("evidence_limit_applied")

    status = (
        EvidenceCollectionStatus.COLLECTED
        if evidence
        else EvidenceCollectionStatus.EMPTY
    )

    return EvidenceCollectionResult(
        step=step,
        status=status,
        evidence=evidence,
        tool_answer=tool_answer,
        source_schema=("BuscarConhecimentoRagOutput"),
        output_sha256=(canonical_output_sha256(mapping)),
        raw_item_count=raw_item_count,
        selected_count=len(evidence),
        discarded_count=max(
            0,
            raw_item_count - len(evidence),
        ),
        warnings=list(dict.fromkeys(warnings)),
        metadata={
            "collector_version": (COLLECTOR_VERSION),
            "source": step.source.value,
            "tool_name": step.tool_name,
            "retrieval_mode": mode,
            "reported_documents": (retrieved_documents),
            "reported_duration_ms": (reported_duration_ms),
            "answer_separated_from_evidence": True,
            "live_call_performed": False,
        },
    )


def _history_safe_payload(
    item: Mapping[str, Any],
) -> tuple[
    dict[str, Any],
    list[str],
]:
    safe_payload: dict[str, Any] = {}

    for field_name in _HISTORY_ALLOWED_FIELDS:
        value = item.get(field_name)

        if value is None or value == "":
            continue

        if isinstance(
            value,
            (str, int, float, bool),
        ):
            safe_payload[field_name] = value
        else:
            safe_payload[field_name] = _safe_text(
                value,
                maximum_length=500,
            )

    discarded_fields = sorted(
        str(key) for key in item if (str(key) not in _HISTORY_ALLOWED_FIELDS)
    )

    return (
        safe_payload,
        discarded_fields,
    )


def _history_content(
    safe_payload: Mapping[str, Any],
) -> str:
    labels = {
        "data_hora": "data_hora",
        "saldo_estimado": "saldo_estimado",
        "comprometimento_renda_percentual": ("comprometimento_renda_percentual"),
        "meses_reserva_estimados": ("meses_reserva_estimados"),
        "score_financeiro": "score_financeiro",
        "nivel_risco": "nivel_risco",
        "situacao": "situacao",
        "moeda": "moeda",
        "idioma": "idioma",
    }

    parts = [
        (f"{labels[field_name]}={safe_payload[field_name]}")
        for field_name in (_HISTORY_ALLOWED_FIELDS)
        if field_name in safe_payload
    ]

    return "Diagnóstico financeiro histórico: " + "; ".join(parts)


def collect_history_evidence(
    *,
    step: ResearchSubquery,
    output: Any,
    call_id: str | None = None,
    duration_ms: float | None = None,
) -> EvidenceCollectionResult:
    if step.source != ResearchSource.FINANCIAL_HISTORY:
        raise UnsupportedEvidenceSourceError(
            "O coletor de histórico recebeu uma fonte incompatível."
        )

    mapping = _to_mapping(output)

    raw_diagnostics = mapping.get(
        "diagnosticos",
        mapping.get(
            "diagnostics",
            [],
        ),
    )

    if raw_diagnostics is None:
        raw_diagnostics = []

    if not isinstance(
        raw_diagnostics,
        (list, tuple),
    ):
        raise UnsafeToolOutputError("O campo de diagnósticos precisa ser uma lista.")

    has_history = bool(
        mapping.get(
            "possui_historico",
            mapping.get(
                "has_history",
                bool(raw_diagnostics),
            ),
        )
    )

    reported_total = _safe_int(
        mapping.get(
            "total",
            mapping.get(
                "total_diagnosticos",
                len(raw_diagnostics),
            ),
        )
    )

    raw_item_count = len(raw_diagnostics)
    maximum_selected = min(
        _MAX_EVIDENCE_ITEMS,
        step.max_results,
    )

    collected: list[EvidenceItem] = []
    discarded_field_names: set[str] = set()
    invalid_item_count = 0

    for index, raw_item in enumerate(raw_diagnostics[:maximum_selected]):
        item = _to_optional_mapping(raw_item)

        if item is None:
            invalid_item_count += 1
            continue

        safe_payload, discarded_fields = _history_safe_payload(item)

        discarded_field_names.update(discarded_fields)

        if not safe_payload:
            invalid_item_count += 1
            continue

        content = _history_content(safe_payload)

        reference_value = safe_payload.get("data_hora") or f"record_{index + 1}"

        reference = "financial_history:" + _safe_reference(reference_value)

        collected.append(
            _build_evidence(
                step=step,
                content=content,
                references=[reference],
                index=index,
                sensitive=True,
                minimum_relevance=0.20,
                metadata={
                    "collector": ("financial_history_v1"),
                    "history_index": index,
                    "call_id": _safe_text(
                        call_id,
                        maximum_length=100,
                    ),
                    "allowed_fields": sorted(safe_payload),
                    "identity_included": False,
                    "sensitive_output": True,
                },
            )
        )

    warnings: list[str] = []

    if discarded_field_names:
        warnings.append("non_authorized_history_fields_discarded")

    if discarded_field_names & _FORBIDDEN_IDENTITY_FIELDS:
        warnings.append("identity_fields_removed")

    if invalid_item_count:
        warnings.append("invalid_history_items_discarded")

    if raw_item_count > maximum_selected:
        warnings.append("evidence_limit_applied")

    evidence = deduplicate_evidence(collected)

    if len(evidence) < len(collected):
        warnings.append("duplicate_evidence_removed")

    if not evidence and not has_history:
        absence_content = (
            "A consulta ao histórico financeiro "
            "do usuário autenticado não encontrou "
            "diagnósticos anteriores."
        )

        evidence = [
            _build_evidence(
                step=step,
                content=absence_content,
                references=["financial_history:empty"],
                index=0,
                sensitive=True,
                minimum_relevance=0.35,
                metadata={
                    "collector": ("financial_history_absence_v1"),
                    "empty_result": True,
                    "identity_included": False,
                    "sensitive_output": True,
                    "call_id": _safe_text(
                        call_id,
                        maximum_length=100,
                    ),
                },
            )
        ]

        warnings.append("history_empty_result")

    inconsistent_output = bool(has_history and not evidence)

    if inconsistent_output:
        warnings.append("inconsistent_history_output")

    if inconsistent_output:
        status = EvidenceCollectionStatus.REJECTED

    elif evidence:
        status = EvidenceCollectionStatus.COLLECTED

    else:
        status = EvidenceCollectionStatus.EMPTY

    effective_raw_count = max(
        raw_item_count,
        len(evidence),
    )

    reported_duration = _safe_int(
        duration_ms or 0,
        maximum=86_400_000,
    )

    return EvidenceCollectionResult(
        step=step,
        status=status,
        evidence=evidence,
        tool_answer=(
            f"Foram selecionadas {len(evidence)} evidências do histórico financeiro."
        ),
        source_schema=("ConsultarHistoricoFinanceiroOutput"),
        output_sha256=(canonical_output_sha256(mapping)),
        raw_item_count=effective_raw_count,
        selected_count=len(evidence),
        discarded_count=max(
            0,
            raw_item_count - len(collected),
        ),
        warnings=list(dict.fromkeys(warnings)),
        metadata={
            "collector_version": (COLLECTOR_VERSION),
            "source": step.source.value,
            "tool_name": step.tool_name,
            "has_history": has_history,
            "reported_total": reported_total,
            "reported_duration_ms": (reported_duration),
            "discarded_field_count": len(discarded_field_names),
            "discarded_identity_fields": sorted(
                discarded_field_names & _FORBIDDEN_IDENTITY_FIELDS
            ),
            "identity_in_evidence": False,
            "live_call_performed": False,
        },
    )


def collect_evidence_from_tool_output(
    *,
    step: ResearchSubquery,
    output: Any,
    call_id: str | None = None,
    duration_ms: float | None = None,
) -> EvidenceCollectionResult:
    if step.source == ResearchSource.KNOWLEDGE_BASE:
        return collect_rag_evidence(
            step=step,
            output=output,
            call_id=call_id,
            duration_ms=duration_ms,
        )

    if step.source == ResearchSource.FINANCIAL_HISTORY:
        return collect_history_evidence(
            step=step,
            output=output,
            call_id=call_id,
            duration_ms=duration_ms,
        )

    raise UnsupportedEvidenceSourceError(
        "A fonte informada não possui um Evidence Collector autorizado."
    )


def collect_evidence_from_tool_result(
    *,
    step: ResearchSubquery,
    tool_result: Any,
) -> EvidenceCollectionResult:
    """
    Integra o Evidence Collector ao ToolResult real.

    Não executa a ferramenta. Apenas processa um resultado
    que já foi produzido pelo runtime governado.
    """

    result_tool_name = _safe_text(
        getattr(
            tool_result,
            "tool_name",
            "",
        ),
        maximum_length=120,
    )

    if result_tool_name != step.tool_name:
        raise EvidenceCollectionError(
            "O ToolResult não corresponde à ferramenta planejada."
        )

    output = getattr(
        tool_result,
        "output",
        None,
    )

    if output is None:
        error = getattr(
            tool_result,
            "error",
            None,
        )

        error_code = _safe_text(
            getattr(
                error,
                "code",
                "tool_output_missing",
            ),
            maximum_length=160,
        )

        raise EvidenceCollectionError(
            f"O ToolResult não contém uma saída utilizável. code={error_code}"
        )

    return collect_evidence_from_tool_output(
        step=step,
        output=output,
        call_id=_safe_text(
            getattr(
                tool_result,
                "call_id",
                "",
            ),
            maximum_length=100,
        ),
        duration_ms=float(
            getattr(
                tool_result,
                "duration_ms",
                0.0,
            )
            or 0.0
        ),
    )


class EvidenceCollector:
    """
    Fachada injetável e testável do coletor.
    """

    def collect(
        self,
        *,
        step: ResearchSubquery,
        output: Any,
        call_id: str | None = None,
        duration_ms: float | None = None,
    ) -> EvidenceCollectionResult:
        return collect_evidence_from_tool_output(
            step=step,
            output=output,
            call_id=call_id,
            duration_ms=duration_ms,
        )

    def collect_tool_result(
        self,
        *,
        step: ResearchSubquery,
        tool_result: Any,
    ) -> EvidenceCollectionResult:
        return collect_evidence_from_tool_result(
            step=step,
            tool_result=tool_result,
        )


__all__ = [
    "COLLECTOR_VERSION",
    "EvidenceCollectionError",
    "EvidenceCollector",
    "UnsafeToolOutputError",
    "UnsupportedEvidenceSourceError",
    "collect_evidence_from_tool_output",
    "collect_evidence_from_tool_result",
    "collect_history_evidence",
    "collect_rag_evidence",
]
