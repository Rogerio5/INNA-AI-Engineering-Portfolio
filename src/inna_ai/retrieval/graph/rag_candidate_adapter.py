from __future__ import annotations

from typing import Any

from inna_ai.retrieval.graph.retriever import GraphRetrievalResult


def _first_non_empty(
    metadata: dict[str, Any],
    *keys: str,
) -> str:
    for key in keys:
        value = metadata.get(key)

        if value is None:
            continue

        normalized = str(value).strip()

        if normalized:
            return normalized

    return ""


def graph_result_to_rag_candidate(
    result: GraphRetrievalResult,
) -> dict[str, Any]:
    metadata = dict(
        result.metadata or {}
    )

    title = (
        _first_non_empty(
            metadata,
            "document_title",
            "section_title",
        )
        or result.document_key
    )

    source = (
        _first_non_empty(
            metadata,
            "fonte",
            "document_path",
            "documento_origem",
            "origem",
        )
        or result.document_key
    )

    category = (
        _first_non_empty(
            metadata,
            "categoria",
            "topic",
        )
        or result.concept_key
    )

    language = (
        _first_non_empty(
            metadata,
            "idioma",
            "language",
        )
        or "pt"
    )

    text = str(
        result.text or ""
    )

    score = float(
        result.graph_score or 0.0
    )

    return {
        "documento_id": int(
            result.document_id
        ),
        "documento_key": (
            result.document_key
        ),
        "chunk_id": result.chunk_id,
        "chunk_index": int(
            result.chunk_index
        ),
        "chunk_text": text,
        "texto": text,
        "trecho": text,
        "titulo": title,
        "fonte": source,
        "categoria": category,
        "idioma": language,
        "score": score,
        "score_graph": score,
        "graph_concept_key": (
            result.concept_key
        ),
        "graph_concept_node_id": (
            result.concept_node_id
        ),
        "graph_retrieval": True,
    }


def graph_results_to_rag_candidates(
    results: list[GraphRetrievalResult],
) -> list[dict[str, Any]]:
    candidates: list[
        dict[str, Any]
    ] = []

    seen: set[
        tuple[int, str]
    ] = set()

    for result in results:
        identity = (
            int(result.document_id),
            str(result.chunk_id),
        )

        if identity in seen:
            continue

        seen.add(identity)

        candidates.append(
            graph_result_to_rag_candidate(
                result
            )
        )

    return candidates


__all__ = [
    "graph_result_to_rag_candidate",
    "graph_results_to_rag_candidates",
]
