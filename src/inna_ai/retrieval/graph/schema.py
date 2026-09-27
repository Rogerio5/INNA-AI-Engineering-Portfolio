from __future__ import annotations

from collections.abc import Iterable

from pydantic import BaseModel, ConfigDict

from inna_ai.retrieval.graph.models import KnowledgeGraphNode, KnowledgeNodeType
from inna_ai.retrieval.graph.relationships import KnowledgeGraphRelationship, KnowledgeRelationshipType

RelationshipRule = tuple[
    KnowledgeNodeType,
    KnowledgeRelationshipType,
    KnowledgeNodeType,
]


ALLOWED_RELATIONSHIPS: frozenset[RelationshipRule] = frozenset(
    {
        (
            KnowledgeNodeType.DOCUMENT,
            KnowledgeRelationshipType.HAS_CHUNK,
            KnowledgeNodeType.CHUNK,
        ),
        (
            KnowledgeNodeType.CHUNK,
            KnowledgeRelationshipType.MENTIONS,
            KnowledgeNodeType.FINANCIAL_CONCEPT,
        ),
        (
            KnowledgeNodeType.DOCUMENT,
            KnowledgeRelationshipType.EXPLAINS,
            KnowledgeNodeType.FINANCIAL_CONCEPT,
        ),
        (
            KnowledgeNodeType.FINANCIAL_CONCEPT,
            KnowledgeRelationshipType.RELATED_TO,
            KnowledgeNodeType.FINANCIAL_CONCEPT,
        ),
        (
            KnowledgeNodeType.FINANCIAL_CONCEPT,
            KnowledgeRelationshipType.CONTRASTS_WITH,
            KnowledgeNodeType.FINANCIAL_CONCEPT,
        ),
        (
            KnowledgeNodeType.FINANCIAL_CONCEPT,
            KnowledgeRelationshipType.DEPENDS_ON,
            KnowledgeNodeType.FINANCIAL_CONCEPT,
        ),
        (
            KnowledgeNodeType.FINANCIAL_CONCEPT,
            KnowledgeRelationshipType.BELONGS_TO,
            KnowledgeNodeType.FINANCIAL_TOPIC,
        ),
        (
            KnowledgeNodeType.DOCUMENT,
            KnowledgeRelationshipType.SOURCED_FROM,
            KnowledgeNodeType.SOURCE,
        ),
    }
)


class KnowledgeGraphSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    version: str = "1.0"

    def relationship_allowed(
        self,
        source_type: KnowledgeNodeType,
        relationship_type: KnowledgeRelationshipType,
        target_type: KnowledgeNodeType,
    ) -> bool:
        return (source_type, relationship_type, target_type) in ALLOWED_RELATIONSHIPS

    def validate_relationship(
        self,
        *,
        source: KnowledgeGraphNode,
        relationship: KnowledgeGraphRelationship,
        target: KnowledgeGraphNode,
    ) -> None:
        if relationship.source_id != source.node_id:
            raise ValueError("Relationship source_id does not match source node.")
        if relationship.target_id != target.node_id:
            raise ValueError("Relationship target_id does not match target node.")
        if not self.relationship_allowed(
            source.node_type,
            relationship.relationship_type,
            target.node_type,
        ):
            raise ValueError(
                "Relationship is not allowed by the Knowledge Graph schema: "
                f"{source.node_type} -> {relationship.relationship_type} -> "
                f"{target.node_type}."
            )

    def validate_graph(
        self,
        *,
        nodes: Iterable[KnowledgeGraphNode],
        relationships: Iterable[KnowledgeGraphRelationship],
    ) -> None:
        node_by_id = {node.node_id: node for node in nodes}

        for relationship in relationships:
            source = node_by_id.get(relationship.source_id)
            target = node_by_id.get(relationship.target_id)

            if source is None:
                raise ValueError(
                    f"Unknown relationship source node: {relationship.source_id}."
                )
            if target is None:
                raise ValueError(
                    f"Unknown relationship target node: {relationship.target_id}."
                )

            self.validate_relationship(
                source=source,
                relationship=relationship,
                target=target,
            )