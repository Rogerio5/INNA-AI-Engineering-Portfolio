"""Runtime Phoenix/OpenTelemetry da INNA."""

from __future__ import annotations

import logging
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from time import perf_counter
from typing import Any

from opentelemetry import trace
from opentelemetry.sdk.trace.sampling import (
    ParentBased,
    TraceIdRatioBased,
)
from opentelemetry.trace import Status, StatusCode

from inna_ai.observability.phoenix.config import PhoenixConfigurationError, PhoenixSettings, load_phoenix_settings
from inna_ai.observability.phoenix.privacy import sanitize_attributes

logger = logging.getLogger(__name__)

_RUNTIME_LOCK = threading.RLock()
_TRACER_PROVIDER: Any | None = None
_RUNTIME_SETTINGS: PhoenixSettings | None = None
_RUNTIME_ERROR: str | None = None
_INITIALIZED = False


@dataclass(frozen=True, slots=True)
class PhoenixRuntimeStatus:
    initialized: bool
    enabled: bool
    ready: bool
    project_name: str
    environment: str
    sample_rate: float
    capture_content: bool
    processor: str
    error: str | None


def initialize_phoenix(
    *,
    force: bool = False,
) -> PhoenixRuntimeStatus:
    """
    Inicializa Phoenix uma única vez.

    Em caso de erro, a aplicação continua funcionando sem exportação.
    """

    global _INITIALIZED
    global _TRACER_PROVIDER
    global _RUNTIME_SETTINGS
    global _RUNTIME_ERROR

    with _RUNTIME_LOCK:
        if _INITIALIZED and not force:
            return get_phoenix_runtime_status()

        _RUNTIME_ERROR = None

        try:
            settings = load_phoenix_settings()
            _RUNTIME_SETTINGS = settings
        except PhoenixConfigurationError as exc:
            _INITIALIZED = True
            _TRACER_PROVIDER = None
            _RUNTIME_ERROR = str(exc)

            logger.warning(
                "Phoenix desabilitado por configuração inválida: %s",
                exc,
            )

            return get_phoenix_runtime_status()

        if not settings.enabled:
            _INITIALIZED = True
            _TRACER_PROVIDER = None

            logger.info("Phoenix está desabilitado por configuração.")

            return get_phoenix_runtime_status()

        try:
            from phoenix.otel import register

            sampler = ParentBased(
                root=TraceIdRatioBased(settings.sample_rate)
            )

            traces_endpoint = (
                settings.collector_endpoint
                if settings.collector_endpoint.endswith(
                    "/v1/traces"
                )
                else (
                    settings.collector_endpoint
                    + "/v1/traces"
                )
            )

            _TRACER_PROVIDER = register(
                project_name=settings.project_name,
                endpoint=traces_endpoint,
                protocol="http/protobuf",
                batch=True,
                sampler=sampler,
                auto_instrument=False,
            )

            _INITIALIZED = True

            logger.info(
                "Phoenix inicializado: project=%s environment=%s "
                "sample_rate=%.2f capture_content=%s",
                settings.project_name,
                settings.environment,
                settings.sample_rate,
                settings.capture_content,
            )

        except Exception as exc:  # fail-open deliberado
            _INITIALIZED = True
            _TRACER_PROVIDER = None
            _RUNTIME_ERROR = type(exc).__name__

            logger.exception(
                "Falha ao inicializar Phoenix; aplicação seguirá "
                "sem exportação de traces."
            )

        return get_phoenix_runtime_status()


def get_phoenix_runtime_status() -> PhoenixRuntimeStatus:
    settings = _RUNTIME_SETTINGS

    return PhoenixRuntimeStatus(
        initialized=_INITIALIZED,
        enabled=bool(settings and settings.enabled),
        ready=bool(_TRACER_PROVIDER),
        project_name=(
            settings.project_name if settings else ""
        ),
        environment=(
            settings.environment if settings else ""
        ),
        sample_rate=(
            settings.sample_rate if settings else 0.0
        ),
        capture_content=(
            settings.capture_content if settings else False
        ),
        processor=(
            "BatchSpanProcessor"
            if _TRACER_PROVIDER is not None
            else "none"
        ),
        error=_RUNTIME_ERROR,
    )


def get_inna_tracer(
    instrumentation_name: str = "inna.observability",
):
    if not _INITIALIZED:
        initialize_phoenix()

    return trace.get_tracer(instrumentation_name)


@contextmanager
def traced_operation(
    name: str,
    *,
    attributes: dict[str, Any] | None = None,
    instrumentation_name: str = "inna.observability",
) -> Iterator[Any]:
    """
    Cria um span sanitizado.

    O fluxo da aplicação continua mesmo se a telemetria falhar.
    """

    tracer = get_inna_tracer(instrumentation_name)
    started_at = perf_counter()

    safe_attributes = sanitize_attributes(attributes)

    settings = _RUNTIME_SETTINGS

    safe_attributes.update(
        {
            "service.name": (
                settings.service_name
                if settings
                else "inna-ai-engineering-portfolio"
            ),
            "deployment.environment": (
                settings.environment
                if settings
                else "unknown"
            ),
            "telemetry.provider": "phoenix",
        }
    )

    with tracer.start_as_current_span(
        name,
        record_exception=False,
        set_status_on_exception=False,
    ) as span:
        for key, value in safe_attributes.items():
            span.set_attribute(key, value)

        try:
            yield span

        except Exception as exc:
            # Nunca exporta mensagem ou stack trace da exceção.
            # Somente o tipo técnico é permitido na telemetria.
            span.set_status(
                Status(
                    StatusCode.ERROR,
                    type(exc).__name__,
                )
            )
            span.set_attribute(
                "operation.error_type",
                type(exc).__name__,
            )
            raise

        else:
            span.set_status(Status(StatusCode.OK))

        finally:
            elapsed_ms = round(
                (perf_counter() - started_at) * 1000,
                3,
            )

            span.set_attribute(
                "operation.duration_ms",
                elapsed_ms,
            )


def force_flush_phoenix(
    timeout_millis: int = 10_000,
) -> bool:
    provider = _TRACER_PROVIDER

    if provider is None:
        return True

    try:
        return bool(
            provider.force_flush(
                timeout_millis=timeout_millis
            )
        )
    except Exception:
        logger.exception("Falha ao executar flush do Phoenix.")
        return False


def shutdown_phoenix() -> bool:
    provider = _TRACER_PROVIDER

    if provider is None:
        return True

    try:
        provider.shutdown()
        return True
    except Exception:
        logger.exception("Falha ao encerrar Phoenix.")
        return False


__all__ = [
    "PhoenixRuntimeStatus",
    "force_flush_phoenix",
    "get_inna_tracer",
    "get_phoenix_runtime_status",
    "initialize_phoenix",
    "shutdown_phoenix",
    "traced_operation",
]
