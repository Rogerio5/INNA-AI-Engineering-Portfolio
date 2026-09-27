"""Schema Cypher idempotente do Knowledge Graph da INNA."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from inna_ai.retrieval.graph.models import KnowledgeNodeType
from inna_ai.retrieval.graph.relationships import KnowledgeRelationshipType

COMMON_NODE_LABEL = "KnowledgeNode"

NODE_LABEL_BY_TYPE: dict[KnowledgeNodeType, str] = {
    KnowledgeNodeType.DOCUMENT: "Document",
    KnowledgeNodeType.CHUNK: "Chunk",
    KnowledgeNodeType.FINANCIAL_CONCEPT: "FinancialConcept",
    KnowledgeNodeType.FINANCIAL_TOPIC: "FinancialTopic",
    KnowledgeNodeType.SOURCE: "Source",
}

RELATIONSHIP_TYPE_TO_CYPHER: dict[KnowledgeRelationshipType, str] = {
    relationship_type: relationship_type.value.upper()
    for relationship_type in KnowledgeRelationshipType
}


class CypherSchemaStatementKind(StrEnum):
    UNIQUE_CONSTRAINT = "unique_constraint"
    RANGE_INDEX = "range_index"
    FULLTEXT_INDEX = "fulltext_index"


@dataclass(frozen=True, slots=True)
class CypherSchemaStatement:
    name: str
    kind: CypherSchemaStatementKind
    cypher: str
    labels: tuple[str, ...]
    properties: tuple[str, ...]


CONSTRAINT_STATEMENTS: tuple[CypherSchemaStatement, ...] = (
    CypherSchemaStatement(
        name="kg_knowledge_node_node_id_unique",
        kind=CypherSchemaStatementKind.UNIQUE_CONSTRAINT,
        cypher=(
            "CREATE CONSTRAINT kg_knowledge_node_node_id_unique IF NOT EXISTS "
            "FOR (n:KnowledgeNode) REQUIRE n.node_id IS UNIQUE"
        ),
        labels=(COMMON_NODE_LABEL,),
        properties=("node_id",),
    ),
    CypherSchemaStatement(
        name="kg_document_document_key_unique",
        kind=CypherSchemaStatementKind.UNIQUE_CONSTRAINT,
        cypher=(
            "CREATE CONSTRAINT kg_document_document_key_unique IF NOT EXISTS "
            "FOR (n:Document) REQUIRE n.document_key IS UNIQUE"
        ),
        labels=("Document",),
        properties=("document_key",),
    ),
    CypherSchemaStatement(
        name="kg_chunk_chunk_key_unique",
        kind=CypherSchemaStatementKind.UNIQUE_CONSTRAINT,
        cypher=(
            "CREATE CONSTRAINT kg_chunk_chunk_key_unique IF NOT EXISTS "
            "FOR (n:Chunk) REQUIRE n.chunk_key IS UNIQUE"
        ),
        labels=("Chunk",),
        properties=("chunk_key",),
    ),
    CypherSchemaStatement(
        name="kg_financial_concept_concept_key_unique",
        kind=CypherSchemaStatementKind.UNIQUE_CONSTRAINT,
        cypher=(
            "CREATE CONSTRAINT kg_financial_concept_concept_key_unique "
            "IF NOT EXISTS FOR (n:FinancialConcept) "
            "REQUIRE n.concept_key IS UNIQUE"
        ),
        labels=("FinancialConcept",),
        properties=("concept_key",),
    ),
    CypherSchemaStatement(
        name="kg_financial_topic_topic_key_unique",
        kind=CypherSchemaStatementKind.UNIQUE_CONSTRAINT,
        cypher=(
            "CREATE CONSTRAINT kg_financial_topic_topic_key_unique "
            "IF NOT EXISTS FOR (n:FinancialTopic) "
            "REQUIRE n.topic_key IS UNIQUE"
        ),
        labels=("FinancialTopic",),
        properties=("topic_key",),
    ),
    CypherSchemaStatement(
        name="kg_source_source_key_unique",
        kind=CypherSchemaStatementKind.UNIQUE_CONSTRAINT,
        cypher=(
            "CREATE CONSTRAINT kg_source_source_key_unique IF NOT EXISTS "
            "FOR (n:Source) REQUIRE n.source_key IS UNIQUE"
        ),
        labels=("Source",),
        properties=("source_key",),
    ),
)


INDEX_STATEMENTS: tuple[CypherSchemaStatement, ...] = (
    CypherSchemaStatement(
        name="kg_chunk_document_ordinal_range",
        kind=CypherSchemaStatementKind.RANGE_INDEX,
        cypher=(
            "CREATE INDEX kg_chunk_document_ordinal_range IF NOT EXISTS "
            "FOR (n:Chunk) ON (n.document_key, n.ordinal)"
        ),
        labels=("Chunk",),
        properties=("document_key", "ordinal"),
    ),
    CypherSchemaStatement(
        name="kg_financial_knowledge_fulltext",
        kind=CypherSchemaStatementKind.FULLTEXT_INDEX,
        cypher=(
            "CREATE FULLTEXT INDEX kg_financial_knowledge_fulltext "
            "IF NOT EXISTS FOR (n:FinancialConcept|FinancialTopic) "
            "ON EACH [n.label, n.description, n.aliases]"
        ),
        labels=("FinancialConcept", "FinancialTopic"),
        properties=("label", "description", "aliases"),
    ),
)


SCHEMA_STATEMENTS: tuple[CypherSchemaStatement, ...] = (
    *CONSTRAINT_STATEMENTS,
    *INDEX_STATEMENTS,
)


def cypher_label_for_node_type(node_type: KnowledgeNodeType) -> str:
    """Retorna o label Cypher fixo de um tipo de nÃ³ suportado."""

    return NODE_LABEL_BY_TYPE[node_type]


def cypher_relationship_type(
    relationship_type: KnowledgeRelationshipType,
) -> str:
    """Retorna o relationship type Cypher fixo do domÃ­nio."""

    return RELATIONSHIP_TYPE_TO_CYPHER[relationship_type]


def schema_statement_names() -> tuple[str, ...]:
    """Retorna nomes estÃ¡veis para auditoria e aplicaÃ§Ã£o idempotente."""

    return tuple(statement.name for statement in SCHEMA_STATEMENTS)
