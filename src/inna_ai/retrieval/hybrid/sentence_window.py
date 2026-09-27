from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping, Sequence
from typing import Any

_SENTENCE_SPLIT_PATTERN = re.compile(r"(?<=[.!?])\s+")

_WORD_PATTERN = re.compile(r"[A-Za-zÀ-ÿ0-9]+")

_STOPWORDS = {
    "a",
    "ao",
    "aos",
    "as",
    "com",
    "como",
    "da",
    "das",
    "de",
    "do",
    "dos",
    "e",
    "ela",
    "ele",
    "em",
    "essa",
    "esse",
    "esta",
    "este",
    "eu",
    "me",
    "meu",
    "minha",
    "na",
    "nas",
    "no",
    "nos",
    "o",
    "os",
    "ou",
    "para",
    "por",
    "que",
    "se",
    "sem",
    "sobre",
    "um",
    "uma",
}


def normalize_sentence_window_text(
    value: object,
) -> str:
    """
    Normaliza texto somente para comparação lexical.

    O texto exibido ao usuário permanece preservado.
    """

    rendered = unicodedata.normalize(
        "NFD",
        str(value or ""),
    )

    rendered = "".join(
        character for character in rendered if unicodedata.category(character) != "Mn"
    )

    return re.sub(
        r"\s+",
        " ",
        rendered.lower(),
    ).strip()


def split_sentences(
    text: object,
) -> list[str]:
    """
    Divide um texto em sentenças sem dependências externas.
    """

    rendered = re.sub(
        r"\s+",
        " ",
        str(text or ""),
    ).strip()

    if not rendered:
        return []

    parts = [
        part.strip() for part in _SENTENCE_SPLIT_PATTERN.split(rendered) if part.strip()
    ]

    return parts or [rendered]


def extract_result_text(
    item: Mapping[str, Any],
) -> str:
    """
    Obtém o texto usando o contrato atual do RAG da INNA.
    """

    for field_name in (
        "chunk_text",
        "texto",
        "trecho",
        "conteudo",
        "content",
    ):
        value = str(
            item.get(
                field_name,
                "",
            )
            or ""
        ).strip()

        if value:
            return value

    return ""


def _safe_int(
    value: object,
    default: int = 0,
) -> int:
    try:
        return int(value)
    except (
        TypeError,
        ValueError,
    ):
        return default


def _query_terms(
    query: object,
) -> set[str]:
    normalized_query = normalize_sentence_window_text(query)

    return {
        token
        for token in _WORD_PATTERN.findall(normalized_query)
        if (len(token) >= 3 and token not in _STOPWORDS)
    }


def _sentence_score(
    sentence: str,
    query_terms: set[str],
) -> float:
    normalized_sentence = normalize_sentence_window_text(sentence)

    sentence_terms = set(_WORD_PATTERN.findall(normalized_sentence))

    overlap = len(sentence_terms & query_terms)

    score = float(overlap * 4)

    for query_term in query_terms:
        if query_term in normalized_sentence:
            score += 0.5

    if len(sentence) < 25:
        score -= 0.25

    return score


def build_sentence_window(
    *,
    query: str,
    chunks: Sequence[Mapping[str, Any]],
    matched_chunk_index: int,
    window_size: int = 2,
    max_characters: int = 4000,
) -> dict[str, Any]:
    """
    Seleciona a sentença mais relevante do chunk recuperado
    e inclui sentenças anteriores e posteriores.

    Os chunks vizinhos servem somente para ampliar o contexto.
    """

    safe_window_size = max(
        0,
        min(
            int(window_size),
            8,
        ),
    )

    safe_max_characters = max(
        300,
        min(
            int(max_characters),
            12000,
        ),
    )

    ordered_chunks = sorted(
        (dict(chunk) for chunk in chunks),
        key=lambda chunk: _safe_int(
            chunk.get(
                "chunk_index",
                0,
            )
        ),
    )

    sentence_records: list[dict[str, Any]] = []

    for chunk in ordered_chunks:
        chunk_index = _safe_int(
            chunk.get(
                "chunk_index",
                0,
            )
        )

        chunk_text = extract_result_text(chunk)

        for sentence_position, sentence in enumerate(split_sentences(chunk_text)):
            sentence_records.append(
                {
                    "sentence": sentence,
                    "chunk_index": chunk_index,
                    "sentence_position": (sentence_position),
                }
            )

    if not sentence_records:
        return {
            "text": "",
            "anchor_index": None,
            "chunk_indices": [],
            "sentence_count": 0,
        }

    query_terms = _query_terms(query)

    candidate_indices = [
        index
        for index, record in enumerate(sentence_records)
        if record["chunk_index"] == matched_chunk_index
    ]

    if not candidate_indices:
        candidate_indices = list(range(len(sentence_records)))

    anchor_index = max(
        candidate_indices,
        key=lambda index: (
            _sentence_score(
                sentence_records[index]["sentence"],
                query_terms,
            ),
            -abs(sentence_records[index]["chunk_index"] - matched_chunk_index),
            -sentence_records[index]["sentence_position"],
        ),
    )

    start_index = max(
        0,
        anchor_index - safe_window_size,
    )

    end_index = min(
        len(sentence_records),
        anchor_index + safe_window_size + 1,
    )

    selected_records = sentence_records[start_index:end_index]

    selected_sentences: list[str] = []

    current_length = 0

    for record in selected_records:
        sentence = str(record["sentence"]).strip()

        if not sentence:
            continue

        projected_length = (
            current_length + len(sentence) + (1 if selected_sentences else 0)
        )

        if projected_length > safe_max_characters and selected_sentences:
            break

        remaining = safe_max_characters - current_length

        if len(sentence) > remaining:
            sentence = sentence[:remaining].rstrip()

        if sentence:
            selected_sentences.append(sentence)

            current_length += len(sentence) + 1

    chunk_indices: list[int] = []

    for record in selected_records:
        chunk_index = int(record["chunk_index"])

        if chunk_index not in chunk_indices:
            chunk_indices.append(chunk_index)

    return {
        "text": " ".join(selected_sentences).strip(),
        "anchor_index": anchor_index,
        "chunk_indices": chunk_indices,
        "sentence_count": len(selected_sentences),
    }


def expand_result_with_sentence_window(
    *,
    query: str,
    result: Mapping[str, Any],
    chunks: Sequence[Mapping[str, Any]],
    window_size: int = 2,
    max_characters: int = 4000,
) -> dict[str, Any]:
    """
    Cria uma nova versão do resultado com contexto expandido.

    O texto original permanece em matched_chunk_text.
    """

    expanded = dict(result)

    original_text = extract_result_text(expanded)

    matched_chunk_index = _safe_int(
        expanded.get(
            "chunk_index",
            0,
        )
    )

    window = build_sentence_window(
        query=query,
        chunks=chunks,
        matched_chunk_index=(matched_chunk_index),
        window_size=window_size,
        max_characters=max_characters,
    )

    window_text = str(
        window.get(
            "text",
            "",
        )
        or ""
    ).strip()

    if not window_text:
        expanded["sentence_window_applied"] = False

        return expanded

    expanded["matched_chunk_text"] = original_text

    expanded["sentence_window_text"] = window_text

    expanded["sentence_window_applied"] = True

    expanded["sentence_window_version"] = "native_v1"

    expanded["sentence_window_size"] = max(
        0,
        int(window_size),
    )

    expanded["sentence_window_anchor_index"] = window.get("anchor_index")

    expanded["sentence_window_chunk_indices"] = window.get(
        "chunk_indices",
        [],
    )

    expanded["sentence_window_sentence_count"] = window.get(
        "sentence_count",
        0,
    )

    # answer_with_rag prioriza chunk_text.
    expanded["chunk_text"] = window_text
    expanded["texto"] = window_text
    expanded["trecho"] = window_text

    current_mode = str(
        expanded.get(
            "modo_busca",
            "",
        )
        or ""
    ).strip()

    if current_mode and not current_mode.endswith("_sentence_window"):
        expanded["modo_busca"] = current_mode + "_sentence_window"

    return expanded
