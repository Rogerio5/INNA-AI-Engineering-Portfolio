"""Cliente Neo4j reutilizÃ¡vel para o Knowledge Graph da INNA."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from inna_ai.retrieval.graph.config import Neo4jCABundleMode, Neo4jSettings
from inna_ai.retrieval.graph.exceptions import KnowledgeGraphConfigurationError, KnowledgeGraphConnectionError

DriverFactory = Callable[..., Any]
TrustCustomCAsFactory = Callable[[str], Any]
CertificatePathFactory = Callable[[], str]


class Neo4jClient:
    """Gerencia um Ãºnico driver Neo4j por instÃ¢ncia da camada de infraestrutura."""

    def __init__(
        self,
        settings: Neo4jSettings,
        *,
        driver_factory: DriverFactory | None = None,
        trust_custom_cas_factory: TrustCustomCAsFactory | None = None,
        certificate_path_factory: CertificatePathFactory | None = None,
    ) -> None:
        self._settings = settings
        self._driver_factory = driver_factory
        self._trust_custom_cas_factory = trust_custom_cas_factory
        self._certificate_path_factory = certificate_path_factory
        self._driver: Any | None = None

    @property
    def database(self) -> str:
        return self._settings.database

    @property
    def connected(self) -> bool:
        return self._driver is not None

    def _resolve_driver_factory(self) -> DriverFactory:
        if self._driver_factory is not None:
            return self._driver_factory

        try:
            from neo4j import GraphDatabase
        except ImportError as exc:
            raise KnowledgeGraphConfigurationError(
                "Pacote neo4j nÃ£o instalado."
            ) from exc

        return GraphDatabase.driver

    def _resolve_certifi_dependencies(
        self,
    ) -> tuple[TrustCustomCAsFactory, CertificatePathFactory]:
        if (
            self._trust_custom_cas_factory is not None
            and self._certificate_path_factory is not None
        ):
            return (
                self._trust_custom_cas_factory,
                self._certificate_path_factory,
            )

        try:
            import certifi
            from neo4j import TrustCustomCAs
        except ImportError as exc:
            raise KnowledgeGraphConfigurationError(
                "Modo TLS certifi requer os pacotes neo4j e certifi."
            ) from exc

        return TrustCustomCAs, certifi.where

    def _driver_uri_for_certifi(self) -> str:
        parts = urlsplit(self._settings.uri)

        scheme_map = {
            "neo4j+s": "neo4j",
            "bolt+s": "bolt",
        }

        driver_scheme = scheme_map.get(parts.scheme.lower())
        if driver_scheme is None:
            raise KnowledgeGraphConfigurationError(
                "Modo TLS certifi exige URI neo4j+s:// ou bolt+s://."
            )

        return urlunsplit(
            (
                driver_scheme,
                parts.netloc,
                parts.path,
                parts.query,
                parts.fragment,
            )
        )

    def _driver_connection_parameters(self) -> tuple[str, dict[str, Any]]:
        password = self._settings.password
        if password is None:
            raise KnowledgeGraphConfigurationError(
                "NEO4J_PASSWORD nÃ£o configurado."
            )

        uri = self._settings.uri
        kwargs: dict[str, Any] = {
            "auth": (
                self._settings.username,
                password.get_secret_value(),
            ),
            "connection_timeout": self._settings.connection_timeout_seconds,
        }

        if self._settings.ca_bundle_mode is Neo4jCABundleMode.CERTIFI:
            trust_factory, certificate_path_factory = (
                self._resolve_certifi_dependencies()
            )

            uri = self._driver_uri_for_certifi()
            kwargs["encrypted"] = True
            kwargs["trusted_certificates"] = trust_factory(
                certificate_path_factory()
            )

        return uri, kwargs

    def connect(self) -> Any:
        if not self._settings.enabled:
            raise KnowledgeGraphConfigurationError(
                "Knowledge Graph/Neo4j estÃ¡ desabilitado."
            )

        if self._driver is None:
            factory = self._resolve_driver_factory()
            uri, kwargs = self._driver_connection_parameters()

            try:
                self._driver = factory(uri, **kwargs)
            except Exception as exc:
                raise KnowledgeGraphConnectionError(
                    "Falha ao criar driver Neo4j."
                ) from exc

        return self._driver

    def verify_connectivity(self) -> None:
        driver = self.connect()
        try:
            driver.verify_connectivity()
        except Exception as exc:
            raise KnowledgeGraphConnectionError(
                "Falha ao validar conectividade com Neo4j."
            ) from exc

    def close(self) -> None:
        if self._driver is None:
            return

        try:
            self._driver.close()
        finally:
            self._driver = None

    def __enter__(self) -> Neo4jClient:
        self.connect()
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()