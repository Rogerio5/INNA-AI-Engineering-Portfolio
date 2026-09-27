"""ConfiguraÃ§Ã£o segura do backend Neo4j do Knowledge Graph."""

from __future__ import annotations

import os
from collections.abc import Mapping
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator

from inna_ai.retrieval.graph.exceptions import KnowledgeGraphConfigurationError

_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})
_FALSE_VALUES = frozenset({"0", "false", "no", "off", ""})


class Neo4jCABundleMode(StrEnum):
    """Origem de confianÃ§a TLS usada pelo driver Neo4j."""

    SYSTEM = "system"
    CERTIFI = "certifi"


class Neo4jSettings(BaseModel):
    """ConfiguraÃ§Ã£o imutÃ¡vel para acesso ao Neo4j."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    enabled: bool = False
    uri: str = "neo4j://localhost:7687"
    username: str = "neo4j"
    password: SecretStr | None = None
    database: str = "neo4j"
    connection_timeout_seconds: float = Field(default=5.0, ge=1.0, le=60.0)
    ca_bundle_mode: Neo4jCABundleMode = Neo4jCABundleMode.SYSTEM

    @model_validator(mode="after")
    def validate_enabled_configuration(self) -> Neo4jSettings:
        if not self.enabled:
            return self

        if not self.uri.strip():
            raise ValueError("NEO4J_URI nÃ£o pode ser vazio quando Neo4j estÃ¡ habilitado.")
        if not self.username.strip():
            raise ValueError("NEO4J_USERNAME nÃ£o pode ser vazio quando Neo4j estÃ¡ habilitado.")
        if self.password is None or not self.password.get_secret_value():
            raise ValueError("NEO4J_PASSWORD Ã© obrigatÃ³rio quando Neo4j estÃ¡ habilitado.")
        if not self.database.strip():
            raise ValueError("NEO4J_DATABASE nÃ£o pode ser vazio quando Neo4j estÃ¡ habilitado.")

        if self.ca_bundle_mode is Neo4jCABundleMode.CERTIFI:
            normalized_uri = self.uri.strip().lower()
            if not normalized_uri.startswith(("neo4j+s://", "bolt+s://")):
                raise ValueError(
                    "NEO4J_CA_BUNDLE_MODE=certifi exige URI neo4j+s:// ou bolt+s://."
                )

        return self


def _parse_bool(value: str, *, name: str) -> bool:
    normalized = str(value or "").strip().lower()
    if normalized in _TRUE_VALUES:
        return True
    if normalized in _FALSE_VALUES:
        return False
    raise KnowledgeGraphConfigurationError(
        f"{name} deve usar true/false, 1/0, yes/no ou on/off."
    )


def load_neo4j_settings(
    environment: Mapping[str, str] | None = None,
) -> Neo4jSettings:
    """Carrega apenas variÃ¡veis explicitamente suportadas pelo Knowledge Graph."""

    env = os.environ if environment is None else environment

    enabled = _parse_bool(
        env.get("INNA_KNOWLEDGE_GRAPH_ENABLED", "false"),
        name="INNA_KNOWLEDGE_GRAPH_ENABLED",
    )

    raw_password = str(env.get("NEO4J_PASSWORD", ""))

    try:
        return Neo4jSettings(
            enabled=enabled,
            uri=str(env.get("NEO4J_URI", "neo4j://localhost:7687")),
            username=str(env.get("NEO4J_USERNAME", "neo4j")),
            password=SecretStr(raw_password) if raw_password else None,
            database=str(env.get("NEO4J_DATABASE", "neo4j")),
            ca_bundle_mode=str(env.get("NEO4J_CA_BUNDLE_MODE", "system")),
        )
    except ValueError as exc:
        raise KnowledgeGraphConfigurationError(str(exc)) from exc