"""Configuração segura da integração Phoenix/OpenTelemetry da INNA."""

from __future__ import annotations

import os
from dataclasses import dataclass
from urllib.parse import urlparse


class PhoenixConfigurationError(ValueError):
    """Erro de configuração local do Phoenix."""


def _parse_bool(value: str | None, *, default: bool) -> bool:
    if value is None:
        return default

    normalized = value.strip().lower()

    if normalized in {"1", "true", "yes", "sim", "on"}:
        return True

    if normalized in {"0", "false", "no", "nao", "não", "off"}:
        return False

    raise PhoenixConfigurationError(
        f"Valor booleano inválido: {value!r}"
    )


def _parse_sample_rate(value: str | None) -> float:
    raw_value = (value or "0.10").strip()

    try:
        sample_rate = float(raw_value)
    except ValueError as exc:
        raise PhoenixConfigurationError(
            "PHOENIX_TRACE_SAMPLE_RATE deve ser numérico."
        ) from exc

    if not 0.0 <= sample_rate <= 1.0:
        raise PhoenixConfigurationError(
            "PHOENIX_TRACE_SAMPLE_RATE deve ficar entre 0.0 e 1.0."
        )

    return sample_rate


def _validate_endpoint(endpoint: str) -> str:
    normalized = endpoint.strip().rstrip("/")

    parsed = urlparse(normalized)

    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise PhoenixConfigurationError(
            "PHOENIX_COLLECTOR_ENDPOINT inválido."
        )

    return normalized


@dataclass(frozen=True, slots=True)
class PhoenixSettings:
    enabled: bool
    api_key: str
    collector_endpoint: str
    project_name: str
    capture_content: bool
    sample_rate: float
    environment: str
    service_name: str

    @property
    def ready(self) -> bool:
        return bool(
            self.enabled
            and self.api_key
            and self.collector_endpoint
            and self.project_name
        )


def load_phoenix_settings() -> PhoenixSettings:
    """Carrega configurações sem imprimir nem expor segredos."""

    enabled = _parse_bool(
        os.getenv("PHOENIX_ENABLED"),
        default=False,
    )

    capture_content = _parse_bool(
        os.getenv("PHOENIX_CAPTURE_CONTENT"),
        default=False,
    )

    api_key = os.getenv("PHOENIX_API_KEY", "").strip()
    endpoint_raw = os.getenv(
        "PHOENIX_COLLECTOR_ENDPOINT",
        "",
    ).strip()

    project_name = os.getenv(
        "PHOENIX_PROJECT_NAME",
        os.getenv("PHOENIX_PROJECT", "inna-production"),
    ).strip()

    endpoint = (
        _validate_endpoint(endpoint_raw)
        if endpoint_raw
        else ""
    )

    settings = PhoenixSettings(
        enabled=enabled,
        api_key=api_key,
        collector_endpoint=endpoint,
        project_name=project_name or "inna-production",
        capture_content=capture_content,
        sample_rate=_parse_sample_rate(
            os.getenv("PHOENIX_TRACE_SAMPLE_RATE")
        ),
        environment=os.getenv(
            "APP_ENV",
            os.getenv("RENDER_SERVICE_NAME", "development"),
        ).strip(),
        service_name=os.getenv(
            "OTEL_SERVICE_NAME",
            "inna-ai-engineering-portfolio",
        ).strip(),
    )

    if settings.enabled and not settings.ready:
        missing = []

        if not settings.api_key:
            missing.append("PHOENIX_API_KEY")

        if not settings.collector_endpoint:
            missing.append("PHOENIX_COLLECTOR_ENDPOINT")

        if not settings.project_name:
            missing.append("PHOENIX_PROJECT_NAME")

        raise PhoenixConfigurationError(
            "Configuração Phoenix incompleta: "
            + ", ".join(missing)
        )

    return settings


__all__ = [
    "PhoenixConfigurationError",
    "PhoenixSettings",
    "load_phoenix_settings",
]
