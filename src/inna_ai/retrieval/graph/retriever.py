"""RecuperaÃ§Ã£o GraphRAG read-only com hidrataÃ§Ã£o dos chunks no PostgreSQL."""

from __future__ import annotations

import atexit
import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from threading import RLock
from typing import Any

from inna_ai.retrieval.graph.config import Neo4jSettings, load_neo4j_settings
from inna_ai.retrieval.graph.neo4j_client import Neo4jClient

PostgresConnectionFactory = Callable[[], Any]


@dataclass(frozen=True, slots=True)
class GraphRetrievalResult:
    document_id: int
    chunk_id: str
    document_key: str
    chunk_index: int
    text: str
    concept_key: str
    concept_node_id: str
    graph_score: float
    metadata: dict[str, Any]


def _default_postgres_connection_factory() -> Any:
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


def _normalize_fulltext_search(value: str) -> str:
    tokens = re.findall(
        r"\w+",
        str(value or ""),
        flags=re.UNICODE,
    )

    return " ".join(tokens).strip()


class GraphKnowledgeRetriever:
    """Busca conceitos no Neo4j e hidrata chunks canÃ´nicos no Neon."""

    def __init__(
        self,
        neo4j_client: Neo4jClient,
        *,
        database: str,
        postgres_connection_factory: (
            PostgresConnectionFactory | None
        ) = None,
        owns_neo4j_client: bool = False,
    ) -> None:
        self._neo4j_client = neo4j_client
        self._database = database
        self._postgres_connection_factory = (
            postgres_connection_factory
            or _default_postgres_connection_factory
        )
        self._owns_neo4j_client = owns_neo4j_client

    @classmethod
    def from_environment(
        cls,
        settings: Neo4jSettings | None = None,
    ) -> GraphKnowledgeRetriever:
        resolved_settings = (
            settings or load_neo4j_settings()
        )

        if not resolved_settings.enabled:
            raise RuntimeError(
                "Knowledge Graph estÃ¡ desabilitado."
            )

        client = Neo4jClient(
            resolved_settings
        )

        client.verify_connectivity()

        return cls(
            client,
            database=resolved_settings.database,
            owns_neo4j_client=True,
        )

    def close(self) -> None:
        if self._owns_neo4j_client:
            self._neo4j_client.close()
            self._owns_neo4j_client = False

    def __enter__(self) -> GraphKnowledgeRetriever:
        return self

    def __exit__(
        self,
        exc_type: object,
        exc_value: object,
        traceback: object,
    ) -> None:
        self.close()

    def search(
        self,
        search_text: str,
        *,
        concept_limit: int = 3,
        chunk_limit: int = 8,
    ) -> list[GraphRetrievalResult]:
        normalized_search = (
            _normalize_fulltext_search(
                search_text
            )
        )

        if not normalized_search:
            return []

        if concept_limit <= 0:
            return []

        if chunk_limit <= 0:
            return []

        driver = self._neo4j_client.connect()

        with driver.session(
            database=self._database
        ) as session:
            graph_rows = session.run(
                """
                CALL db.index.fulltext.queryNodes(
                    'kg_financial_knowledge_fulltext',
                    $search_text
                )
                YIELD node, score
                WHERE
                    node:FinancialConcept
                    AND NOT node.node_id
                        CONTAINS 'kg-smoke'
                WITH
                    node AS concept,
                    score
                ORDER BY
                    score DESC,
                    concept.concept_key
                LIMIT $concept_limit

                MATCH
                    (document:Document)
                    -[:EXPLAINS]->
                    (concept)

                MATCH
                    (document)
                    -[:HAS_CHUNK]->
                    (chunk:Chunk)
                    -[:MENTIONS]->
                    (concept)

                RETURN
                    concept.node_id
                        AS concept_node_id,
                    concept.concept_key
                        AS concept_key,
                    score
                        AS graph_score,
                    document.document_key
                        AS document_key,
                    chunk.chunk_key
                        AS chunk_id,
                    chunk.ordinal
                        AS chunk_index

                ORDER BY
                    graph_score DESC,
                    document_key,
                    chunk_index,
                    chunk_id
                """,
                search_text=normalized_search,
                concept_limit=int(
                    concept_limit
                ),
            ).data()

        return self._hydrate_graph_rows(
            graph_rows,
            chunk_limit=chunk_limit,
        )

    def retrieve_by_concept(
        self,
        concept_key: str,
        *,
        chunk_limit: int = 8,
    ) -> list[GraphRetrievalResult]:
        normalized_concept = str(
            concept_key or ""
        ).strip()

        if not normalized_concept:
            return []

        if chunk_limit <= 0:
            return []

        driver = self._neo4j_client.connect()

        with driver.session(
            database=self._database
        ) as session:
            graph_rows = session.run(
                """
                MATCH
                    (concept:FinancialConcept {
                        concept_key: $concept_key
                    })
                WHERE NOT concept.node_id
                    CONTAINS 'kg-smoke'

                MATCH
                    (document:Document)
                    -[:EXPLAINS]->
                    (concept)

                MATCH
                    (document)
                    -[:HAS_CHUNK]->
                    (chunk:Chunk)
                    -[:MENTIONS]->
                    (concept)

                RETURN
                    concept.node_id
                        AS concept_node_id,
                    concept.concept_key
                        AS concept_key,
                    1.0
                        AS graph_score,
                    document.document_key
                        AS document_key,
                    chunk.chunk_key
                        AS chunk_id,
                    chunk.ordinal
                        AS chunk_index

                ORDER BY
                    document_key,
                    chunk_index,
                    chunk_id
                """,
                concept_key=normalized_concept,
            ).data()

        return self._hydrate_graph_rows(
            graph_rows,
            chunk_limit=chunk_limit,
        )

    def _hydrate_graph_rows(
        self,
        graph_rows: list[dict[str, Any]],
        *,
        chunk_limit: int,
    ) -> list[GraphRetrievalResult]:
        unique_graph_rows: list[
            dict[str, Any]
        ] = []
        seen_chunk_ids: set[str] = set()

        for row in graph_rows:
            chunk_id = str(
                row.get("chunk_id") or ""
            ).strip()

            if not chunk_id:
                continue

            if chunk_id in seen_chunk_ids:
                continue

            seen_chunk_ids.add(
                chunk_id
            )
            unique_graph_rows.append(
                row
            )

            if len(unique_graph_rows) >= (
                chunk_limit
            ):
                break

        if not unique_graph_rows:
            return []

        requested_chunk_ids = [
            str(row["chunk_id"])
            for row in unique_graph_rows
        ]

        connection = (
            self._postgres_connection_factory()
        )

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
                        c.chunk_id,
                        d.nome_logico,
                        c.chunk_index,
                        c.texto,
                        c.metadata
                    FROM public.chunks_embeddings_rag c
                    JOIN public.documentos_upload_rag d
                        ON d.id = c.documento_id
                    WHERE
                        COALESCE(d.ativo, TRUE)
                        AND d.nome_logico IS NOT NULL
                        AND BTRIM(d.nome_logico) <> ''
                        AND c.chunk_id = ANY(
                            %s::text[]
                        );
                    """,
                    (
                        requested_chunk_ids,
                    ),
                )

                hydrated_rows = (
                    cursor.fetchall()
                )
            finally:
                cursor.close()

            connection.rollback()
        finally:
            try:
                connection.rollback()
            except Exception:
                pass

            connection.close()

        hydrated_by_id = {
            str(row[1]): row
            for row in hydrated_rows
        }

        results: list[
            GraphRetrievalResult
        ] = []

        for graph_row in unique_graph_rows:
            chunk_id = str(
                graph_row["chunk_id"]
            )

            hydrated = hydrated_by_id.get(
                chunk_id
            )

            if hydrated is None:
                continue

            (
                hydrated_document_id,
                _chunk_id,
                hydrated_document_key,
                hydrated_chunk_index,
                text,
                metadata,
            ) = hydrated

            graph_document_key = str(
                graph_row.get(
                    "document_key"
                )
                or ""
            )

            if (
                str(hydrated_document_key)
                != graph_document_key
            ):
                raise RuntimeError(
                    "Graph/PostgreSQL document_key "
                    "divergente para chunk."
                )

            if (
                int(hydrated_chunk_index)
                != int(
                    graph_row["chunk_index"]
                )
            ):
                raise RuntimeError(
                    "Graph/PostgreSQL chunk_index "
                    "divergente."
                )

            results.append(
                GraphRetrievalResult(
                    document_id=int(
                        hydrated_document_id
                    ),
                    chunk_id=chunk_id,
                    document_key=(
                        graph_document_key
                    ),
                    chunk_index=int(
                        hydrated_chunk_index
                    ),
                    text=str(text or ""),
                    concept_key=str(
                        graph_row.get(
                            "concept_key"
                        )
                        or ""
                    ),
                    concept_node_id=str(
                        graph_row.get(
                            "concept_node_id"
                        )
                        or ""
                    ),
                    graph_score=float(
                        graph_row.get(
                            "graph_score"
                        )
                        or 0.0
                    ),
                    metadata=_coerce_metadata(
                        metadata
                    ),
                )
            )

        return results



_shared_graph_retriever: GraphKnowledgeRetriever | None = None
_shared_graph_retriever_lock = RLock()


def get_shared_graph_retriever() -> GraphKnowledgeRetriever:
    global _shared_graph_retriever

    retriever = _shared_graph_retriever

    if retriever is not None:
        return retriever

    with _shared_graph_retriever_lock:
        retriever = _shared_graph_retriever

        if retriever is None:
            retriever = (
                GraphKnowledgeRetriever.from_environment()
            )
            _shared_graph_retriever = retriever

        return retriever


def reset_shared_graph_retriever() -> None:
    global _shared_graph_retriever

    with _shared_graph_retriever_lock:
        retriever = _shared_graph_retriever
        _shared_graph_retriever = None

    if retriever is None:
        return

    close = getattr(
        retriever,
        "close",
        None,
    )

    if callable(close):
        try:
            close()
        except Exception:
            pass


atexit.register(
    reset_shared_graph_retriever
)

__all__ = [
    "reset_shared_graph_retriever",
    "get_shared_graph_retriever",
    "GraphKnowledgeRetriever",
    "GraphRetrievalResult",
]
