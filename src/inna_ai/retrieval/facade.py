"""Fachada pública e reduzida do RAG."""

from __future__ import annotations

import logging
import time
from typing import Any


logger = logging.getLogger(
    "inna_ai.retrieval"
)


def _classify_chunk(
    text: str,
) -> str:
    del text
    return "geral"


def answer_with_rag(
    pergunta: str,
    idioma: str = "pt",
    top_k: int = 2,
) -> dict[str, Any]:
    """
    Executa retrieval textual seguro sobre a camada
    pública e devolve evidências normalizadas.

    A geração generativa completa será conectada em
    uma fase posterior do portfólio.
    """
    question = str(
        pergunta or ""
    ).strip()

    if len(question) < 3:
        return {
            "resposta": (
                "A pergunta precisa possuir "
                "pelo menos 3 caracteres."
            ),
            "fontes": [],
            "contexto_usado": "",
            "modo": "validation_error",
            "documentos": [],
        }

    try:
        limit = max(
            1,
            min(
                int(top_k),
                10,
            ),
        )
    except (TypeError, ValueError):
        limit = 2

    try:
        from inna_ai.retrieval.hybrid.retrieval import (
            buscar_chunks_textuais,
        )

        raw = buscar_chunks_textuais(
            question,
            limite=limit,
            classificar_chunk=(
                _classify_chunk
            ),
        )

        results = (
            raw.get(
                "resultados",
                [],
            )
            if isinstance(
                raw,
                dict,
            )
            else []
        )

    except Exception as exc:
        return {
            "resposta": (
                "O backend de retrieval não está "
                "disponível nesta execução."
            ),
            "fontes": [],
            "contexto_usado": "",
            "modo": (
                "retrieval_unavailable"
            ),
            "documentos": [],
            "error_type":
                type(exc).__name__,
        }

    documents = [
        item
        for item in results
        if isinstance(
            item,
            dict,
        )
    ]

    context_parts = []

    sources = []

    for item in documents[:limit]:

        text = str(
            item.get(
                "chunk_text"
            )
            or item.get(
                "texto"
            )
            or ""
        ).strip()

        if text:
            context_parts.append(
                text
            )

        source = str(
            item.get(
                "nome_original"
            )
            or item.get(
                "fonte"
            )
            or item.get(
                "source"
            )
            or ""
        ).strip()

        if (
            source
            and source not in sources
        ):
            sources.append(
                source
            )

    context = "\n\n".join(
        context_parts
    )

    if context:

        answer = (
            "Evidências recuperadas da base "
            "educacional:\n\n"
            + context[:6000]
        )

    else:

        answer = (
            "Não encontrei evidência suficiente "
            "na base educacional."
        )

    return {
        "resposta": answer,
        "fontes": sources,
        "contexto_usado": context,
        "modo":
            "portfolio_hybrid_retrieval",
        "documentos": documents,
        "idioma": str(
            idioma or "pt"
        ),
    }


def save_rag_log(
    pergunta: str,
    resultado: dict,
    tempo_resposta_ms: int | None = None,
) -> None:
    """
    Registra somente metadados técnicos,
    nunca o conteúdo recuperado.
    """
    payload = (
        resultado
        if isinstance(
            resultado,
            dict,
        )
        else {}
    )

    logger.info(
        "rag_event question_length=%s "
        "mode=%s sources=%s duration_ms=%s",
        len(
            str(
                pergunta
                or ""
            )
        ),
        str(
            payload.get(
                "modo",
                "",
            )
        ),
        len(
            payload.get(
                "fontes",
                [],
            )
            or []
        ),
        int(
            tempo_resposta_ms
            or 0
        ),
    )


__all__ = [
    "answer_with_rag",
    "save_rag_log",
]
