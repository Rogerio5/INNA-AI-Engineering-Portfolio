from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class KnowledgeRelationshipType(StrEnum):
    HAS_CHUNK = "has_chunk"
    MENTIONS = "mentions"
    EXPLAINS = "explains"
    RELATED_TO = "related_to"
    CONTRASTS_WITH = "contrasts_with"
    DEPENDS_ON = "depends_on"
    BELONGS_TO = "belongs_to"
    SOURCED_FROM = "sourced_from"


class KnowledgeGraphRelationship(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
    )

    source_id: str = Field(min_length=1, max_length=200)
    target_id: str = Field(min_length=1, max_length=200)
    relationship_type: KnowledgeRelationshipType
    properties: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def reject_self_relationship(self) -> KnowledgeGraphRelationship:
        if self.source_id == self.target_id:
            raise ValueError("Knowledge Graph relationships cannot target the same node.")
        return self