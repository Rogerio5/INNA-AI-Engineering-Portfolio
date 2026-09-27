from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class KnowledgeNodeType(StrEnum):
    DOCUMENT = "document"
    CHUNK = "chunk"
    FINANCIAL_CONCEPT = "financial_concept"
    FINANCIAL_TOPIC = "financial_topic"
    SOURCE = "source"


class KnowledgeGraphNode(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
    )

    node_id: str = Field(min_length=1, max_length=200)
    node_type: KnowledgeNodeType
    label: str = Field(min_length=1, max_length=300)
    metadata: dict[str, Any] = Field(default_factory=dict)


class DocumentNode(KnowledgeGraphNode):
    node_type: Literal[KnowledgeNodeType.DOCUMENT] = KnowledgeNodeType.DOCUMENT
    document_key: str = Field(min_length=1, max_length=200)
    version: str | None = Field(default=None, max_length=100)


class ChunkNode(KnowledgeGraphNode):
    node_type: Literal[KnowledgeNodeType.CHUNK] = KnowledgeNodeType.CHUNK
    chunk_key: str = Field(min_length=1, max_length=200)
    document_key: str = Field(min_length=1, max_length=200)
    ordinal: int = Field(ge=0)
    content_hash: str | None = Field(default=None, min_length=1, max_length=128)


class FinancialConceptNode(KnowledgeGraphNode):
    node_type: Literal[KnowledgeNodeType.FINANCIAL_CONCEPT] = (
        KnowledgeNodeType.FINANCIAL_CONCEPT
    )
    concept_key: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    aliases: tuple[str, ...] = Field(default_factory=tuple)


class FinancialTopicNode(KnowledgeGraphNode):
    node_type: Literal[KnowledgeNodeType.FINANCIAL_TOPIC] = (
        KnowledgeNodeType.FINANCIAL_TOPIC
    )
    topic_key: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)


class SourceNode(KnowledgeGraphNode):
    node_type: Literal[KnowledgeNodeType.SOURCE] = KnowledgeNodeType.SOURCE
    source_key: str = Field(min_length=1, max_length=200)
    source_type: str = Field(min_length=1, max_length=100)
    uri: str | None = Field(default=None, max_length=2000)