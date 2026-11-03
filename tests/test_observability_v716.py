"""Testes locais de observabilidade da INNA V7.16.

Sem exportacao de rede, credenciais ou servicos externos.
"""

import pytest

from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)
from opentelemetry.trace import StatusCode

from inna_ai.observability.phoenix import runtime


@pytest.fixture
def spans_locais(monkeypatch):
    """Provedor isolado e exportador em memoria."""

    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))

    monkeypatch.setenv("PHOENIX_ENABLED", "false")

    monkeypatch.setattr(
        runtime,
        "get_inna_tracer",
        lambda instrumentation_name="inna.observability":
            provider.get_tracer(instrumentation_name),
    )

    try:
        yield exporter
    finally:
        provider.shutdown()


def test_tracing_sucesso_registra_status_e_duracao(spans_locais):
    with runtime.traced_operation(
        "inna.v716.test.success",
        attributes={"test.scenario": "success"},
    ):
        resultado = 10 + 20

    assert resultado == 30

    spans = spans_locais.get_finished_spans()
    assert len(spans) == 1

    span = spans[0]

    assert span.name == "inna.v716.test.success"
    assert span.status.status_code == StatusCode.OK
    assert span.attributes["test.scenario"] == "success"
    assert span.attributes["operation.duration_ms"] >= 0


def test_tracing_erro_propaga_excecao(spans_locais):
    with pytest.raises(ValueError):
        with runtime.traced_operation(
            "inna.v716.test.error",
            attributes={"test.scenario": "error"},
        ):
            raise ValueError("mensagem privada ficticia")

    spans = spans_locais.get_finished_spans()
    assert len(spans) == 1

    span = spans[0]

    assert span.status.status_code == StatusCode.ERROR
    assert span.attributes["operation.error_type"] == "ValueError"
    assert span.attributes["operation.duration_ms"] >= 0


def test_tracing_nao_expoe_mensagem_privada(spans_locais):
    segredo_ficticio = "mensagem privada ficticia"

    with pytest.raises(ValueError):
        with runtime.traced_operation(
            "inna.v716.test.privacy",
            attributes={"test.scenario": "privacy"},
        ):
            raise ValueError(segredo_ficticio)

    spans = spans_locais.get_finished_spans()
    assert len(spans) == 1

    span = spans[0]

    assert segredo_ficticio not in str(span.attributes)
    assert segredo_ficticio not in str(span.status.description)

    assert not any(
        event.name == "exception"
        for event in span.events
    )
