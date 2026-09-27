"""ConstrÃ³i um plano determinÃ­stico de Knowledge Graph a partir do RAG canÃ´nico."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Any

from inna_ai.retrieval.graph.models import ChunkNode, DocumentNode, SourceNode
from inna_ai.retrieval.graph.rag_source import RagChunkRecord, RagKnowledgeSnapshot
from inna_ai.retrieval.graph.relationships import KnowledgeGraphRelationship, KnowledgeRelationshipType

BuildNode = DocumentNode | ChunkNode | SourceNode


@dataclass(frozen=True, slots=True)
class KnowledgeGraphBuildPlan:
    nodes: tuple[BuildNode, ...]
    relationships: tuple[KnowledgeGraphRelationship, ...]
    document_count: int
    chunk_count: int

    @property
    def node_count(self) -> int:
        return len(self.nodes)

    @property
    def relationship_count(self) -> int:
        return len(self.relationships)


def _non_empty_metadata(values: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in values.items()
        if value is not None and value != ""
    }


def _content_hash(chunk: RagChunkRecord) -> str:
    persisted = str(
        chunk.metadata.get("content_hash") or ""
    ).strip()

    if persisted:
        return persisted

    return sha256(
        chunk.text.encode("utf-8")
    ).hexdigest()


def _document_chunks(
    snapshot: RagKnowledgeSnapshot,
) -> dict[int, list[RagChunkRecord]]:
    grouped: dict[int, list[RagChunkRecord]] = {}

    for chunk in snapshot.chunks:
        grouped.setdefault(
            chunk.document_id,
            [],
        ).append(chunk)

    return grouped


def _document_title(
    document_key: str,
    original_name: str | None,
    chunks: list[RagChunkRecord],
) -> str:
    for chunk in chunks:
        title = str(
            chunk.metadata.get("document_title")
            or chunk.metadata.get("section_title")
            or ""
        ).strip()

        if title:
            return title

    if original_name:
        normalized = str(original_name).strip()
        if normalized:
            return normalized

    return document_key


def _document_version(
    chunks: list[RagChunkRecord],
) -> str:
    for chunk in chunks:
        version = str(
            chunk.metadata.get("version") or ""
        ).strip()

        if version:
            return version

    return "1"


def _chunk_metadata(
    chunk: RagChunkRecord,
) -> dict[str, Any]:
    allowed_keys = (
        "area",
        "canonical_hash",
        "categoria",
        "context_optimization",
        "database_document_id",
        "document_path",
        "document_title",
        "documento_key",
        "documento_origem",
        "embedding_dimension",
        "embedding_model",
        "embedding_status",
        "fase",
        "fonte",
        "idioma",
        "ingestion_mode",
        "ingestion_status",
        "knowledge_base",
        "language",
        "origem",
        "retrieval_focus",
        "schema_adapter_version",
        "schema_version",
        "section_title",
        "source_ids",
        "tipo",
        "topic",
        "version",
        "word_count",
    )

    metadata = {
        key: chunk.metadata[key]
        for key in allowed_keys
        if key in chunk.metadata
    }

    metadata["database_document_id"] = (
        chunk.document_id
    )
    metadata["rag_chunk_id"] = chunk.chunk_id

    return metadata


class KnowledgeGraphBuilder:
    """Cria nÃ³s e relaÃ§Ãµes do RAG sem persistir no Neo4j."""

    def build(
        self,
        snapshot: RagKnowledgeSnapshot,
    ) -> KnowledgeGraphBuildPlan:
        documents_by_id = {
            document.document_id: document
            for document in snapshot.documents
        }

        if len(documents_by_id) != len(
            snapshot.documents
        ):
            raise ValueError(
                "Snapshot contÃ©m document_id duplicado."
            )

        document_keys = {
            document.document_key
            for document in snapshot.documents
        }

        if len(document_keys) != len(
            snapshot.documents
        ):
            raise ValueError(
                "Snapshot contÃ©m document_key duplicado."
            )

        chunks_by_document = _document_chunks(
            snapshot
        )

        nodes: list[BuildNode] = []
        relationships: list[
            KnowledgeGraphRelationship
        ] = []

        for document in snapshot.documents:
            chunks = chunks_by_document.get(
                document.document_id,
                [],
            )

            if not chunks:
                raise ValueError(
                    "Documento canÃ´nico sem chunks."
                )

            document_node_id = (
                f"document:{document.document_key}"
            )
            source_node_id = (
                f"source:rag:{document.document_key}"
            )

            document_label = _document_title(
                document.document_key,
                document.original_name,
                chunks,
            )

            nodes.append(
                DocumentNode(
                    node_id=document_node_id,
                    label=document_label,
                    document_key=(
                        document.document_key
                    ),
                    version=_document_version(
                        chunks
                    ),
                    metadata=_non_empty_metadata(
                        {
                            "database_document_id": (
                                document.document_id
                            ),
                            "rag_origin": (
                                document.origin
                            ),
                            "rag_original_name": (
                                document.original_name
                            ),
                            "rag_saved_name": (
                                document.saved_name
                            ),
                        }
                    ),
                )
            )

            nodes.append(
                SourceNode(
                    node_id=source_node_id,
                    label=(
                        f"RAG Source - "
                        f"{document.document_key}"
                    ),
                    source_key=(
                        f"rag:{document.document_key}"
                    ),
                    source_type=(
                        str(document.origin).strip()
                        if document.origin
                        else "rag_document"
                    ),
                    metadata=_non_empty_metadata(
                        {
                            "database_document_id": (
                                document.document_id
                            ),
                            "document_key": (
                                document.document_key
                            ),
                            "saved_name": (
                                document.saved_name
                            ),
                        }
                    ),
                )
            )

            relationships.append(
                KnowledgeGraphRelationship(
                    source_id=document_node_id,
                    target_id=source_node_id,
                    relationship_type=(
                        KnowledgeRelationshipType.SOURCED_FROM
                    ),
                    properties={
                        "mapping": "canonical_rag",
                    },
                )
            )

        for chunk in snapshot.chunks:
            document = documents_by_id.get(
                chunk.document_id
            )

            if document is None:
                raise ValueError(
                    "Chunk referencia document_id ausente "
                    "no snapshot."
                )

            if (
                chunk.document_key
                != document.document_key
            ):
                raise ValueError(
                    "Chunk possui document_key incompatÃ­vel "
                    "com o documento."
                )

            document_node_id = (
                f"document:{document.document_key}"
            )
            chunk_node_id = (
                f"chunk:{chunk.chunk_id}"
            )

            nodes.append(
                ChunkNode(
                    node_id=chunk_node_id,
                    label=(
                        f"{document.document_key} "
                        f"- chunk {chunk.chunk_index}"
                    ),
                    chunk_key=chunk.chunk_id,
                    document_key=(
                        document.document_key
                    ),
                    ordinal=chunk.chunk_index,
                    content_hash=_content_hash(
                        chunk
                    ),
                    metadata=_chunk_metadata(
                        chunk
                    ),
                )
            )

            relationships.append(
                KnowledgeGraphRelationship(
                    source_id=document_node_id,
                    target_id=chunk_node_id,
                    relationship_type=(
                        KnowledgeRelationshipType.HAS_CHUNK
                    ),
                    properties={
                        "ordinal": (
                            chunk.chunk_index
                        ),
                        "mapping": (
                            "canonical_rag"
                        ),
                    },
                )
            )

        node_ids = [
            node.node_id
            for node in nodes
        ]

        if len(node_ids) != len(
            set(node_ids)
        ):
            raise ValueError(
                "Plano gerou node_id duplicado."
            )

        relationship_keys = [
            (
                relationship.source_id,
                relationship.relationship_type,
                relationship.target_id,
            )
            for relationship in relationships
        ]

        if len(relationship_keys) != len(
            set(relationship_keys)
        ):
            raise ValueError(
                "Plano gerou relacionamento duplicado."
            )

        return KnowledgeGraphBuildPlan(
            nodes=tuple(nodes),
            relationships=tuple(
                relationships
            ),
            document_count=len(
                snapshot.documents
            ),
            chunk_count=len(
                snapshot.chunks
            ),
        )


__all__ = [
    "KnowledgeGraphBuildPlan",
    "KnowledgeGraphBuilder",
]
