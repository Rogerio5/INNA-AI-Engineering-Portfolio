"""
Seleção de resultados de ferramentas da INNA.
"""

from __future__ import annotations

from typing import Any


_ALLOWED_TOOL_FIELDS = {
    "tool",
    "ok",
    "mode",
    "duration_ms",
    "retrieved_documents",
    "sources",
    "error_type",
    "result",
    "summary",
}


def select_tool_results(
    tool_results: list[dict[str, Any]] | None,
    *,
    max_results: int = 8,
) -> list[dict[str, Any]]:
    max_results = max(
        1,
        min(int(max_results), 30),
    )

    selected: list[dict[str, Any]] = []

    for raw_result in reversed(
        list(tool_results or [])
    ):
        if not isinstance(raw_result, dict):
            continue

        cleaned = {
            key: value
            for key, value in raw_result.items()
            if key in _ALLOWED_TOOL_FIELDS
        }

        if not cleaned:
            continue

        selected.append(cleaned)

        if len(selected) >= max_results:
            break

    return list(reversed(selected))


def extract_unique_sources(
    tool_results: list[dict[str, Any]] | None,
    *,
    max_sources: int = 12,
) -> list[str]:
    max_sources = max(
        1,
        min(int(max_sources), 50),
    )

    sources: list[str] = []

    for result in tool_results or []:
        if not isinstance(result, dict):
            continue

        raw_sources = result.get(
            "sources",
            [],
        )

        if isinstance(raw_sources, str):
            raw_sources = [raw_sources]

        if not isinstance(
            raw_sources,
            (list, tuple),
        ):
            continue

        for source in raw_sources:
            normalized = str(
                source or ""
            ).strip()

            if (
                normalized
                and normalized not in sources
            ):
                sources.append(normalized)

            if len(sources) >= max_sources:
                return sources

    return sources


__all__ = [
    "select_tool_results",
    "extract_unique_sources",
]
