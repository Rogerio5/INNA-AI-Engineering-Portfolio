"""
Auto-Merging Retrieval lógico da INNA.

Esta primeira implementação é deliberadamente isolada do runtime.

Ela não altera:
- Hybrid Retrieval;
- Vector Retrieval;
- Text Retrieval;
- RRF;
- rerank;
- Sentence-Window;
- TOP_K;
- embeddings.

Como a base atual ainda não possui uma hierarquia explícita
parent -> child persistida, a prova de conceito cria grupos
lógicos a partir de:

    documento_id + chunk_index

O objetivo desta fase é validar agrupamento, threshold,
ordenação, deduplicação, limite de contexto e fallback seguro.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

AUTO_MERGING_POLICY = "logical_parent_by_chunk_index"


def _safe_positive_int(
    value: Any,
) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None

    if parsed < 0:
        return None

    return parsed


def _result_identity(
    item: dict[str, Any],
) -> tuple[Any, ...]:
    chunk_id = item.get("chunk_id")

    if chunk_id not in (None, ""):
        return (
            "chunk_id",
            str(chunk_id),
        )

    return (
        "document_chunk",
        item.get("documento_id"),
        item.get("chunk_index"),
    )


def _logical_parent_index(
    chunk_index: int,
    *,
    parent_size: int,
) -> int:
    return chunk_index // parent_size


def _chunk_text(
    item: dict[str, Any],
) -> str:
    return str(
        item.get("chunk_text")
        or item.get("trecho")
        or item.get("texto")
        or ""
    ).strip()


def _mark_not_merged(
    item: dict[str, Any],
    *,
    reason: str,
) -> dict[str, Any]:
    result = dict(item)

    result["auto_merging_applied"] = False
    result["auto_merging_policy"] = AUTO_MERGING_POLICY
    result["auto_merging_skip_reason"] = reason

    return result


def _build_merged_result(
    items: list[dict[str, Any]],
    *,
    parent_index: int,
    max_characters: int,
) -> dict[str, Any] | None:
    ordered_items = sorted(
        items,
        key=lambda item: (
            _safe_positive_int(
                item.get("chunk_index")
            )
            or 0
        ),
    )

    unique_items: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()

    for item in ordered_items:
        identity = _result_identity(item)

        if identity in seen:
            continue

        seen.add(identity)
        unique_items.append(item)

    texts = [
        text
        for text in (
            _chunk_text(item)
            for item in unique_items
        )
        if text
    ]

    if not texts:
        return None

    merged_text = "\n\n".join(texts)

    if len(merged_text) > max_characters:
        return None

    # Preserva como representante o resultado mais bem posicionado
    # na lista original recebida.
    representative = dict(items[0])

    child_indexes = [
        _safe_positive_int(
            item.get("chunk_index")
        )
        for item in unique_items
    ]

    child_indexes = [
        index
        for index in child_indexes
        if index is not None
    ]

    child_chunk_ids = [
        str(item.get("chunk_id"))
        for item in unique_items
        if item.get("chunk_id") not in (None, "")
    ]

    representative["chunk_text"] = merged_text

    if "trecho" in representative:
        representative["trecho"] = merged_text

    if "texto" in representative:
        representative["texto"] = merged_text

    representative["auto_merging_applied"] = True
    representative["auto_merging_policy"] = (
        AUTO_MERGING_POLICY
    )
    representative["auto_merging_skip_reason"] = None
    representative["auto_merging_parent_index"] = (
        parent_index
    )
    representative["auto_merging_child_count"] = len(
        unique_items
    )
    representative["auto_merging_child_indexes"] = (
        child_indexes
    )
    representative["auto_merging_child_chunk_ids"] = (
        child_chunk_ids
    )

    return representative


def auto_merge_results(
    results: list[dict[str, Any]],
    *,
    parent_size: int = 3,
    min_children: int = 2,
    max_characters: int = 4000,
) -> list[dict[str, Any]]:
    """
    Consolida resultados irmãos em um parent lógico.

    Regras da prova de conceito:

    1. Somente resultados com documento_id e chunk_index
       estruturados participam do agrupamento.

    2. O parent lógico é calculado por:

           chunk_index // parent_size

    3. Um grupo somente é consolidado quando possui pelo
       menos min_children resultados únicos recuperados.

    4. O texto consolidado respeita max_characters.

    5. Em qualquer situação não elegível, os resultados
       originais são preservados.
    """
    if parent_size < 2:
        raise ValueError(
            "parent_size deve ser >= 2"
        )

    if min_children < 2:
        raise ValueError(
            "min_children deve ser >= 2"
        )

    if min_children > parent_size:
        raise ValueError(
            "min_children não pode exceder parent_size"
        )

    if max_characters < 1:
        raise ValueError(
            "max_characters deve ser >= 1"
        )

    if not results:
        return []

    groups: dict[
        tuple[int, int],
        list[tuple[int, dict[str, Any]]],
    ] = defaultdict(list)

    group_key_by_position: dict[
        int,
        tuple[int, int],
    ] = {}

    for position, raw_item in enumerate(results):
        item = dict(raw_item)

        document_id = _safe_positive_int(
            item.get("documento_id")
        )
        chunk_index = _safe_positive_int(
            item.get("chunk_index")
        )

        if (
            document_id is None
            or document_id <= 0
            or chunk_index is None
        ):
            continue

        parent_index = _logical_parent_index(
            chunk_index,
            parent_size=parent_size,
        )

        key = (
            document_id,
            parent_index,
        )

        groups[key].append(
            (
                position,
                item,
            )
        )

        group_key_by_position[position] = key

    merged_by_group: dict[
        tuple[int, int],
        dict[str, Any] | None,
    ] = {}

    eligible_groups: set[
        tuple[int, int]
    ] = set()

    for key, positioned_items in groups.items():
        unique_identities = {
            _result_identity(item)
            for _, item in positioned_items
        }

        if len(unique_identities) < min_children:
            continue

        parent_index = key[1]

        group_items = [
            item
            for _, item in positioned_items
        ]

        merged = _build_merged_result(
            group_items,
            parent_index=parent_index,
            max_characters=max_characters,
        )

        eligible_groups.add(key)
        merged_by_group[key] = merged

    final_results: list[dict[str, Any]] = []
    emitted_groups: set[
        tuple[int, int]
    ] = set()

    for position, raw_item in enumerate(results):
        item = dict(raw_item)

        key = group_key_by_position.get(
            position
        )

        if key is None:
            final_results.append(
                _mark_not_merged(
                    item,
                    reason=(
                        "missing_structured_identity"
                    ),
                )
            )
            continue

        if key not in eligible_groups:
            final_results.append(
                _mark_not_merged(
                    item,
                    reason=(
                        "insufficient_sibling_hits"
                    ),
                )
            )
            continue

        if key in emitted_groups:
            continue

        emitted_groups.add(key)

        merged = merged_by_group.get(key)

        if merged is None:
            for _, original_group_item in groups[key]:
                final_results.append(
                    _mark_not_merged(
                        original_group_item,
                        reason=(
                            "parent_context_too_large_or_empty"
                        ),
                    )
                )

            continue

        final_results.append(
            merged
        )

    return final_results
