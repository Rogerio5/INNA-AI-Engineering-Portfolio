"""Adaptador read-only da fonte RAG canÃ´nica para o Knowledge Graph."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

ConnectionFactory = Callable[[], Any]


@dataclass(frozen=True, slots=True)
class RagDocumentRecord:
    document_id: int
    document_key: str
    original_name: str | None
    saved_name: str | None
    origin: str | None


@dataclass(frozen=True, slots=True)
class RagChunkRecord:
    document_id: int
    document_key: str
    chunk_id: str
    chunk_index: int
    text: str
    metadata: dict[str, Any]


@dataclass(frozen=True, slots=True)
class RagKnowledgeSnapshot:
    documents: tuple[RagDocumentRecord, ...]
    chunks: tuple[RagChunkRecord, ...]


def _default_connection_factory() -> Any:
    from inna_ai.retrieval.storage.vector_store import _conectar_postgres

    return _conectar_postgres()


def _coerce_metadata(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)

    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}

        if isinstance(parsed, dict):
            return dict(parsed)

    return {}


class RagKnowledgeSource:
    """Carrega documentos ativos com nome_logico e seus chunks."""

    def __init__(
        self,
        connection_factory: ConnectionFactory | None = None,
    ) -> None:
        self._connection_factory = (
            connection_factory or _default_connection_factory
        )

    def load_canonical_snapshot(self) -> RagKnowledgeSnapshot:
        connection = self._connection_factory()

        try:
            connection.rollback()
            connection.set_session(
                readonly=True,
                autocommit=False,
            )

            cursor = connection.cursor()

            try:
                cursor.execute(
                    """
                    SELECT
                        d.id,
                        d.nome_logico,
                        d.nome_original,
                        d.nome_salvo,
                        d.origem,
                        c.chunk_id,
                        c.chunk_index,
                        c.texto,
                        c.metadata
                    FROM public.documentos_upload_rag d
                    JOIN public.chunks_embeddings_rag c
                        ON c.documento_id = d.id
                    WHERE
                        COALESCE(d.ativo, TRUE)
                        AND d.nome_logico IS NOT NULL
                        AND BTRIM(d.nome_logico) <> ''
                        AND c.chunk_id IS NOT NULL
                        AND BTRIM(c.chunk_id) <> ''
                    ORDER BY
                        d.nome_logico,
                        c.chunk_index,
                        c.chunk_id;
                    """
                )

                rows = cursor.fetchall()
            finally:
                cursor.close()

            documents: dict[int, RagDocumentRecord] = {}
            chunks: list[RagChunkRecord] = []

            for row in rows:
                (
                    document_id,
                    document_key,
                    original_name,
                    saved_name,
                    origin,
                    chunk_id,
                    chunk_index,
                    text,
                    metadata,
                ) = row

                document_id = int(document_id)
                document_key = str(document_key).strip()
                chunk_id = str(chunk_id).strip()

                if not document_key:
                    raise ValueError(
                        "Documento canÃ´nico sem document_key."
                    )

                if not chunk_id:
                    raise ValueError(
                        "Chunk canÃ´nico sem chunk_id."
                    )

                existing = documents.get(document_id)

                if existing is None:
                    documents[document_id] = RagDocumentRecord(
                        document_id=document_id,
                        document_key=document_key,
                        original_name=(
                            str(original_name)
                            if original_name is not None
                            else None
                        ),
                        saved_name=(
                            str(saved_name)
                            if saved_name is not None
                            else None
                        ),
                        origin=(
                            str(origin)
                            if origin is not None
                            else None
                        ),
                    )
                elif existing.document_key != document_key:
                    raise ValueError(
                        "document_id associado a chaves diferentes."
                    )

                chunks.append(
                    RagChunkRecord(
                        document_id=document_id,
                        document_key=document_key,
                        chunk_id=chunk_id,
                        chunk_index=int(chunk_index),
                        text=str(text or ""),
                        metadata=_coerce_metadata(metadata),
                    )
                )

            connection.rollback()

            ordered_documents = tuple(
                sorted(
                    documents.values(),
                    key=lambda item: (
                        item.document_key,
                        item.document_id,
                    ),
                )
            )

            return RagKnowledgeSnapshot(
                documents=ordered_documents,
                chunks=tuple(chunks),
            )
        finally:
            try:
                connection.rollback()
            except Exception:
                pass

            connection.close()


__all__ = [
    "RagChunkRecord",
    "RagDocumentRecord",
    "RagKnowledgeSnapshot",
    "RagKnowledgeSource",
]
