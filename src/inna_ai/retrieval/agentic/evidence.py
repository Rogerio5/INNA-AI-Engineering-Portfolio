"""
Funções de qualidade e integridade das evidências.

Este módulo não acessa banco, rede, Gemini ou ferramentas.
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections.abc import Mapping
from typing import Any

from inna_ai.retrieval.agentic.contracts import EvidenceItem

_STOPWORDS = {
    "a",
    "as",
    "o",
    "os",
    "de",
    "da",
    "das",
    "do",
    "dos",
    "e",
    "em",
    "para",
    "por",
    "com",
    "sem",
    "que",
    "qual",
    "quais",
    "como",
    "meu",
    "meus",
    "minha",
    "minhas",
    "uma",
    "um",
    "the",
    "and",
    "or",
    "of",
    "to",
    "in",
    "for",
    "my",
    "how",
    "what",
    "el",
    "la",
    "los",
    "las",
    "y",
    "mi",
    "mis",
}


def normalize_evidence_text(
    value: str,
) -> str:
    normalized = unicodedata.normalize(
        "NFKD",
        str(value or ""),
    )

    without_accents = "".join(
        character for character in normalized if not unicodedata.combining(character)
    )

    return " ".join(without_accents.lower().split())


def evidence_terms(
    value: str,
) -> set[str]:
    return {
        token
        for token in re.findall(
            r"[a-z0-9]+",
            normalize_evidence_text(value),
        )
        if len(token) >= 3 and token not in _STOPWORDS
    }


def lexical_relevance(
    query: str,
    content: str,
) -> float:
    """
    Combina cobertura dos termos da consulta e Jaccard.

    A maior parte do peso fica na cobertura da pergunta,
    evitando penalizar excessivamente chunks extensos.
    """

    query_terms = evidence_terms(query)
    content_terms = evidence_terms(content)

    if not query_terms or not content_terms:
        return 0.0

    overlap = len(query_terms.intersection(content_terms))

    query_coverage = overlap / len(query_terms)

    union_size = len(query_terms.union(content_terms))

    jaccard = overlap / union_size if union_size else 0.0

    score = 0.85 * query_coverage + 0.15 * jaccard

    return round(
        max(
            0.0,
            min(1.0, score),
        ),
        6,
    )


def content_sha256(
    content: str,
) -> str:
    return hashlib.sha256(
        str(content).encode(
            "utf-8",
            errors="replace",
        )
    ).hexdigest()


def canonical_output_sha256(
    output: Mapping[str, Any],
) -> str:
    serialized = json.dumps(
        dict(output),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )

    return content_sha256(serialized)


def token_jaccard_similarity(
    left: str,
    right: str,
) -> float:
    left_terms = evidence_terms(left)
    right_terms = evidence_terms(right)

    if not left_terms and not right_terms:
        return 1.0

    if not left_terms or not right_terms:
        return 0.0

    union = left_terms.union(right_terms)

    if not union:
        return 0.0

    return len(left_terms.intersection(right_terms)) / len(union)


def deduplicate_evidence(
    evidence: list[EvidenceItem],
    *,
    near_duplicate_threshold: float = 0.94,
) -> list[EvidenceItem]:
    """
    Consolida duplicidades preservando proveniência.

    Regras profissionais:

    1. Conteúdo exatamente igual:
       - mantém a evidência de maior relevância;
       - une todas as referências;
       - registra a consolidação nos metadados.

    2. Conteúdo apenas semelhante:
       - consolida somente quando há referência em comum;
       - ou quando ambas não possuem referências.

    3. Conteúdos semelhantes de documentos diferentes:
       - permanecem como evidências independentes.

    A lista é ordenada pela relevância antes da análise,
    garantindo que o melhor registro seja preservado.
    """

    threshold = max(
        0.0,
        min(
            1.0,
            float(near_duplicate_threshold),
        ),
    )

    ordered = sorted(
        evidence,
        key=lambda item: (
            -item.relevance_score,
            item.evidence_id,
        ),
    )

    selected: list[EvidenceItem] = []

    exact_content_indexes: dict[
        tuple[str, str],
        int,
    ] = {}

    def normalized_references(
        item: EvidenceItem,
    ) -> tuple[str, ...]:
        normalized: list[str] = []

        for reference in item.references:
            value = normalize_evidence_text(reference)

            if value and value not in normalized:
                normalized.append(value)

        return tuple(normalized)

    def merge_references(
        left: EvidenceItem,
        right: EvidenceItem,
    ) -> list[str]:
        merged: list[str] = []
        normalized_seen: set[str] = set()

        for reference in list(left.references) + list(right.references):
            normalized = normalize_evidence_text(reference)

            if not normalized or normalized in normalized_seen:
                continue

            normalized_seen.add(normalized)
            merged.append(reference)

            if len(merged) >= 20:
                break

        return merged

    def merge_into_existing(
        *,
        existing_index: int,
        candidate: EvidenceItem,
        mode: str,
    ) -> None:
        existing = selected[existing_index]

        merged_references = merge_references(
            existing,
            candidate,
        )

        merged_metadata = {
            **existing.metadata,
            "deduplication_mode": mode,
            "merged_reference_count": len(merged_references),
            "merged_evidence_count": int(
                existing.metadata.get(
                    "merged_evidence_count",
                    1,
                )
            )
            + 1,
        }

        selected[existing_index] = EvidenceItem.model_validate(
            {
                **existing.model_dump(mode="python"),
                "references": (merged_references),
                "metadata": merged_metadata,
            }
        )

    for candidate in ordered:
        exact_key = (
            candidate.source.value,
            candidate.content_sha256,
        )

        exact_index = exact_content_indexes.get(exact_key)

        if exact_index is not None:
            merge_into_existing(
                existing_index=exact_index,
                candidate=candidate,
                mode="exact_content_merge",
            )
            continue

        candidate_references = set(normalized_references(candidate))

        near_duplicate_index: int | None = None

        for index, existing in enumerate(selected):
            if existing.source != candidate.source:
                continue

            existing_references = set(normalized_references(existing))

            references_overlap = bool(
                existing_references.intersection(candidate_references)
            )

            both_without_references = bool(
                not existing_references and not candidate_references
            )

            if not (references_overlap or both_without_references):
                continue

            similarity = token_jaccard_similarity(
                existing.content,
                candidate.content,
            )

            if similarity >= threshold:
                near_duplicate_index = index
                break

        if near_duplicate_index is not None:
            merge_into_existing(
                existing_index=(near_duplicate_index),
                candidate=candidate,
                mode=("near_duplicate_merge"),
            )
            continue

        selected.append(candidate)

        exact_content_indexes[exact_key] = len(selected) - 1

    return selected


__all__ = [
    "canonical_output_sha256",
    "content_sha256",
    "deduplicate_evidence",
    "evidence_terms",
    "lexical_relevance",
    "normalize_evidence_text",
    "token_jaccard_similarity",
]
