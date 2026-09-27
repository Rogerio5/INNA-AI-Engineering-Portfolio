"""Camada de persist??ncia Neo4j do Knowledge Graph da INNA."""

from __future__ import annotations

import json
from typing import Any

from pydantic import ValidationError

from inna_ai.retrieval.graph.cypher_schema import COMMON_NODE_LABEL, cypher_label_for_node_type, cypher_relationship_type
from inna_ai.retrieval.graph.exceptions import KnowledgeGraphPersistenceError
from inna_ai.retrieval.graph.models import ChunkNode, DocumentNode, FinancialConceptNode, FinancialTopicNode, KnowledgeGraphNode, KnowledgeNodeType, SourceNode
from inna_ai.retrieval.graph.neo4j_client import Neo4jClient
from inna_ai.retrieval.graph.relationships import KnowledgeGraphRelationship
from inna_ai.retrieval.graph.schema import KnowledgeGraphSchema

_NODE_MODEL_BY_TYPE: dict[KnowledgeNodeType, type[KnowledgeGraphNode]] = {
    KnowledgeNodeType.DOCUMENT: DocumentNode,
    KnowledgeNodeType.CHUNK: ChunkNode,
    KnowledgeNodeType.FINANCIAL_CONCEPT: FinancialConceptNode,
    KnowledgeNodeType.FINANCIAL_TOPIC: FinancialTopicNode,
    KnowledgeNodeType.SOURCE: SourceNode,
}


def _json_dumps(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _node_properties(node: KnowledgeGraphNode) -> dict[str, Any]:
    properties = node.model_dump(mode="json")
    metadata = properties.pop("metadata", {})
    properties["metadata_json"] = _json_dumps(metadata)
    return properties


def _node_from_properties(properties: dict[str, Any]) -> KnowledgeGraphNode:
    payload = dict(properties)
    raw_node_type = payload.get("node_type")

    try:
        node_type = KnowledgeNodeType(raw_node_type)
    except (TypeError, ValueError) as exc:
        raise KnowledgeGraphPersistenceError(
            "Tipo de n?? persistido ?? inv??lido."
        ) from exc

    raw_metadata = payload.pop("metadata_json", "{}")
    try:
        metadata = json.loads(raw_metadata) if raw_metadata else {}
    except (TypeError, json.JSONDecodeError) as exc:
        raise KnowledgeGraphPersistenceError(
            "Metadados persistidos do n?? s??o inv??lidos."
        ) from exc

    if not isinstance(metadata, dict):
        raise KnowledgeGraphPersistenceError(
            "Metadados persistidos do n?? devem ser um objeto JSON."
        )

    payload["metadata"] = metadata
    payload["node_type"] = node_type

    model = _NODE_MODEL_BY_TYPE[node_type]
    try:
        return model.model_validate(payload)
    except ValidationError as exc:
        raise KnowledgeGraphPersistenceError(
            "N?? persistido n??o corresponde ao modelo de dom??nio."
        ) from exc


class KnowledgeGraphRepository:
    """Persiste n??s e relacionamentos do dom??nio usando Cypher parametrizado."""

    def __init__(
        self,
        client: Neo4jClient,
        *,
        schema: KnowledgeGraphSchema | None = None,
    ) -> None:
        self._client = client
        self._schema = schema or KnowledgeGraphSchema()

    @property
    def database(self) -> str:
        return self._client.database

    def upsert_node(self, node: KnowledgeGraphNode) -> None:
        label = cypher_label_for_node_type(node.node_type)
        query = (
            f"MERGE (n:{COMMON_NODE_LABEL}:{label} {{node_id: $node_id}}) "
            "SET n += $properties "
            "RETURN n.node_id AS node_id"
        )
        properties = _node_properties(node)

        def write_node(tx: Any) -> None:
            record = tx.run(
                query,
                node_id=node.node_id,
                properties=properties,
            ).single()
            if record is None or record.get("node_id") != node.node_id:
                raise KnowledgeGraphPersistenceError(
                    "Neo4j n??o confirmou a persist??ncia do n??."
                )

        try:
            driver = self._client.connect()
            with driver.session(database=self.database) as session:
                session.execute_write(write_node)
        except KnowledgeGraphPersistenceError:
            raise
        except Exception as exc:
            raise KnowledgeGraphPersistenceError(
                "Falha ao persistir n?? no Knowledge Graph."
            ) from exc

    def node_exists(self, node_id: str) -> bool:
        normalized_node_id = str(node_id or "").strip()
        if not normalized_node_id:
            raise ValueError("node_id n??o pode ser vazio.")

        query = (
            f"MATCH (n:{COMMON_NODE_LABEL} {{node_id: $node_id}}) "
            "RETURN count(n) > 0 AS exists"
        )

        def read_exists(tx: Any) -> bool:
            record = tx.run(query, node_id=normalized_node_id).single()
            return bool(record and record.get("exists"))

        try:
            driver = self._client.connect()
            with driver.session(database=self.database) as session:
                return bool(session.execute_read(read_exists))
        except Exception as exc:
            raise KnowledgeGraphPersistenceError(
                "Falha ao consultar exist??ncia de n?? no Knowledge Graph."
            ) from exc

    def get_node(self, node_id: str) -> KnowledgeGraphNode | None:
        normalized_node_id = str(node_id or "").strip()
        if not normalized_node_id:
            raise ValueError("node_id n??o pode ser vazio.")

        query = (
            f"MATCH (n:{COMMON_NODE_LABEL} {{node_id: $node_id}}) "
            "RETURN properties(n) AS properties"
        )

        def read_node(tx: Any) -> dict[str, Any] | None:
            record = tx.run(query, node_id=normalized_node_id).single()
            if record is None:
                return None
            properties = record.get("properties")
            return dict(properties) if properties is not None else None

        try:
            driver = self._client.connect()
            with driver.session(database=self.database) as session:
                properties = session.execute_read(read_node)
        except Exception as exc:
            raise KnowledgeGraphPersistenceError(
                "Falha ao consultar n?? no Knowledge Graph."
            ) from exc

        if properties is None:
            return None
        return _node_from_properties(properties)

    def upsert_relationship(
        self,
        relationship: KnowledgeGraphRelationship,
    ) -> None:
        relationship_type = cypher_relationship_type(
            relationship.relationship_type
        )
        lookup_query = (
            f"MATCH (source:{COMMON_NODE_LABEL} {{node_id: $source_id}}) "
            f"MATCH (target:{COMMON_NODE_LABEL} {{node_id: $target_id}}) "
            "RETURN source.node_type AS source_type, "
            "target.node_type AS target_type"
        )
        merge_query = (
            f"MATCH (source:{COMMON_NODE_LABEL} {{node_id: $source_id}}) "
            f"MATCH (target:{COMMON_NODE_LABEL} {{node_id: $target_id}}) "
            f"MERGE (source)-[r:{relationship_type}]->(target) "
            "SET r.properties_json = $properties_json "
            "RETURN type(r) AS relationship_type"
        )
        properties_json = _json_dumps(relationship.properties)

        def write_relationship(tx: Any) -> None:
            endpoints = tx.run(
                lookup_query,
                source_id=relationship.source_id,
                target_id=relationship.target_id,
            ).single()
            if endpoints is None:
                raise KnowledgeGraphPersistenceError(
                    "Relacionamento referencia n?? de origem ou destino inexistente."
                )

            try:
                source_type = KnowledgeNodeType(endpoints.get("source_type"))
                target_type = KnowledgeNodeType(endpoints.get("target_type"))
            except (TypeError, ValueError) as exc:
                raise KnowledgeGraphPersistenceError(
                    "Tipo persistido dos n??s do relacionamento ?? inv??lido."
                ) from exc

            if not self._schema.relationship_allowed(
                source_type,
                relationship.relationship_type,
                target_type,
            ):
                raise KnowledgeGraphPersistenceError(
                    "Relacionamento n??o ?? permitido pelo schema do Knowledge Graph."
                )

            record = tx.run(
                merge_query,
                source_id=relationship.source_id,
                target_id=relationship.target_id,
                properties_json=properties_json,
            ).single()
            if (
                record is None
                or record.get("relationship_type") != relationship_type
            ):
                raise KnowledgeGraphPersistenceError(
                    "Neo4j n??o confirmou a persist??ncia do relacionamento."
                )

        try:
            driver = self._client.connect()
            with driver.session(database=self.database) as session:
                session.execute_write(write_relationship)
        except KnowledgeGraphPersistenceError:
            raise
        except Exception as exc:
            raise KnowledgeGraphPersistenceError(
                "Falha ao persistir relacionamento no Knowledge Graph."
            ) from exc
