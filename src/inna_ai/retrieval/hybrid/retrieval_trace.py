"""
Rastreabilidade estruturada da recuperação RAG da INNA.
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4


@dataclass(frozen=True, slots=True)
class RagRetrievalResultTrace:
    position: int
    chunk_id: str | int | None
    document_id: str | int | None
    document_key: str | None
    title: str | None
    source: str | None
    search_origins: tuple[str, ...]
    score: float | None
    hybrid_score: float | None
    rerank_score: float | None
    sentence_window_applied: bool | None
    sentence_window_policy: str | None
    sentence_window_document_key: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class RagRetrievalTrace:
    trace_id: str
    query: str
    language: str
    search_mode: str
    top_k: int
    started_at: str
    started_monotonic: float = field(
        repr=False
    )
    finished_at: str | None = None
    total_time_ms: int | None = None
    results: list[
        RagRetrievalResultTrace
    ] = field(default_factory=list)

    def finish(
        self,
        results: list[dict] | None,
        *,
        search_mode: str | None = None,
    ) -> RagRetrievalTrace:
        if search_mode:
            self.search_mode = str(
                search_mode
            )

        self.results = (
            build_result_traces(
                results or []
            )
        )

        self.finished_at = (
            datetime.now(
                UTC
            ).isoformat()
        )

        elapsed = (
            time.monotonic()
            - self.started_monotonic
        )

        self.total_time_ms = max(
            0,
            round(elapsed * 1000),
        )

        return self

    def to_dict(self) -> dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "query": self.query,
            "language": self.language,
            "search_mode": self.search_mode,
            "top_k": self.top_k,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "total_time_ms": self.total_time_ms,
            "results_total": len(
                self.results
            ),
            "results": [
                result.to_dict()
                for result in self.results
            ],
        }


def _optional_float(
    value: Any,
) -> float | None:
    if value is None:
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _optional_text(
    value: Any,
) -> str | None:
    if value is None:
        return None

    normalized = str(value).strip()

    return normalized or None


def _optional_bool(
    value: Any,
) -> bool | None:
    if isinstance(value, bool):
        return value

    if value in (0, 1):
        return bool(value)

    if isinstance(value, str):
        normalized = value.strip().lower()

        if normalized in {
            "true",
            "1",
            "yes",
            "on",
        }:
            return True

        if normalized in {
            "false",
            "0",
            "no",
            "off",
        }:
            return False

    return None


def _search_origins(
    item: dict,
) -> tuple[str, ...]:
    origins = item.get(
        "origem_busca"
    ) or ()

    if isinstance(origins, str):
        origins = (origins,)

    return tuple(
        str(origin)
        for origin in origins
        if origin
    )


def build_result_traces(
    results: list[dict],
) -> list[RagRetrievalResultTrace]:
    traces = []

    for position, item in enumerate(
        results,
        start=1,
    ):
        traces.append(
            RagRetrievalResultTrace(
                position=position,
                chunk_id=(
                    item.get("chunk_id")
                    or item.get("id")
                ),
                document_id=(
                    item.get("documento_id")
                    or item.get("document_id")
                ),
                document_key=_optional_text(
                    item.get("documento_key")
                    or item.get("document_key")
                ),
                title=(
                    item.get("titulo")
                    or item.get("title")
                ),
                source=(
                    item.get("fonte")
                    or item.get("source")
                ),
                search_origins=(
                    _search_origins(item)
                ),
                score=_optional_float(
                    item.get("score")
                ),
                hybrid_score=_optional_float(
                    item.get("score_hibrido")
                ),
                rerank_score=_optional_float(
                    item.get("score_rerank")
                ),
                sentence_window_applied=(
                    _optional_bool(
                        item.get(
                            "sentence_window_applied"
                        )
                    )
                ),
                sentence_window_policy=(
                    _optional_text(
                        item.get(
                            "sentence_window_policy"
                        )
                    )
                ),
                sentence_window_document_key=(
                    _optional_text(
                        item.get(
                            "sentence_window_document_key"
                        )
                    )
                ),
            )
        )

    return traces


def start_retrieval_trace(
    *,
    query: str,
    language: str = "pt",
    search_mode: str = "pending",
    top_k: int = 4,
) -> RagRetrievalTrace:
    normalized_query = str(
        query or ""
    ).strip()

    if not normalized_query:
        raise ValueError(
            "A consulta da recuperação "
            "não pode estar vazia."
        )

    normalized_top_k = int(top_k)

    if normalized_top_k < 1:
        raise ValueError(
            "top_k deve ser maior que zero."
        )

    return RagRetrievalTrace(
        trace_id=str(uuid4()),
        query=normalized_query,
        language=str(
            language or "pt"
        ),
        search_mode=str(
            search_mode or "pending"
        ),
        top_k=normalized_top_k,
        started_at=datetime.now(
            UTC
        ).isoformat(),
        started_monotonic=(
            time.monotonic()
        ),
    )


__all__ = [
    "RagRetrievalResultTrace",
    "RagRetrievalTrace",
    "build_result_traces",
    "start_retrieval_trace",
]
