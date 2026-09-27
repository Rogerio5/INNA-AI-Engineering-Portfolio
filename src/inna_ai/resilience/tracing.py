from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from opentelemetry import trace

from inna_ai.observability.reliability import observe_production_reliability_event, observe_production_reliability_persistence_event
from inna_ai.resilience.contracts import OperationKind, ResiliencePolicy
from inna_ai.resilience.events import ResilienceEvent, ResilienceEventType
from inna_ai.resilience.runtime import ResilienceRuntime

from inna_ai.observability.phoenix.runtime import traced_operation

INSTRUMENTATION_NAME = "inna.resilience"


def build_resilience_operation_attributes(
    policy: ResiliencePolicy,
) -> dict[str, Any]:
    """
    Retorna somente metadados operacionais seguros.

    Nunca inclui prompt, resposta, mensagem,
    payload, credencial ou conteúdo financeiro.
    """
    retry_enabled = (
        policy.operation_kind
        is not OperationKind.SIDE_EFFECT
        and policy.max_attempts > 1
    )

    return {
        "resilience.operation": policy.name,
        "resilience.operation_kind": (
            policy.operation_kind.value
        ),
        "resilience.retry.enabled": retry_enabled,
        "resilience.max_attempts": (
            policy.max_attempts
        ),
        "resilience.retry.base_delay_seconds": (
            float(
                policy.base_delay_seconds
            )
        ),
        "resilience.retry.max_delay_seconds": (
            float(
                policy.max_delay_seconds
            )
        ),
        "resilience.retry.jitter_ratio": (
            float(
                policy.jitter_ratio
            )
        ),
        "resilience.circuit.failure_threshold": (
            policy.circuit_failure_threshold
        ),
        "resilience.circuit.recovery_seconds": (
            float(
                policy.circuit_recovery_seconds
            )
        ),
        "privacy.content_exported": False,
    }


def build_resilience_event_attributes(
    event: ResilienceEvent,
) -> dict[str, Any]:
    """
    Constrói uma allowlist de atributos OTEL.

    A mensagem da exceção deliberadamente não faz
    parte de ResilienceEvent nem destes atributos.
    """
    attributes: dict[str, Any] = {
        "resilience.operation": event.operation,
        "resilience.event_type": (
            event.event_type.value
        ),
        "resilience.attempt.number": (
            event.attempt_number
        ),
        "resilience.attempt.max": (
            event.max_attempts
        ),
        "privacy.content_exported": False,
    }

    if event.failure_kind is not None:
        attributes[
            "resilience.failure.kind"
        ] = event.failure_kind.value

    if event.error_type:
        attributes[
            "resilience.error.type"
        ] = str(
            event.error_type
        )[:120]

    if event.delay_seconds is not None:
        attributes[
            "resilience.retry.delay_seconds"
        ] = float(
            event.delay_seconds
        )

    if event.circuit_state:
        attributes[
            "resilience.circuit.state"
        ] = str(
            event.circuit_state
        )[:40]

    if event.elapsed_ms is not None:
        attributes[
            "resilience.elapsed_ms"
        ] = max(
            0.0,
            float(
                event.elapsed_ms
            ),
        )

    return attributes


def observe_resilience_event(
    event: ResilienceEvent,
) -> None:
    """
    Anexa o evento ao span OTEL atualmente ativo.

    Falhas de telemetria nunca alteram o caminho
    funcional da aplicação.
    """
    try:
        span = trace.get_current_span()

        if span is None:
            return

        if not span.is_recording():
            return

        attributes = (
            build_resilience_event_attributes(
                event
            )
        )

        span.add_event(
            (
                "inna.resilience."
                f"{event.event_type.value}"
            ),
            attributes=attributes,
        )

        if (
            event.event_type
            is ResilienceEventType.OPERATION_SUCCEEDED
        ):
            span.set_attribute(
                "resilience.success",
                True,
            )

            span.set_attribute(
                "resilience.final_attempt",
                event.attempt_number,
            )

        elif (
            event.event_type
            in {
                ResilienceEventType.OPERATION_FAILED,
                ResilienceEventType.CIRCUIT_REJECTED,
            }
        ):
            span.set_attribute(
                "resilience.success",
                False,
            )

            span.set_attribute(
                "resilience.final_attempt",
                event.attempt_number,
            )

        if (
            event.event_type
            is ResilienceEventType.CIRCUIT_REJECTED
        ):
            span.set_attribute(
                "resilience.circuit.rejected",
                True,
            )

    except Exception:
        # Observabilidade não pode quebrar
        # uma chamada funcional da aplicação.
        return


@contextmanager
def traced_resilience_operation(
    policy: ResiliencePolicy,
) -> Iterator[Any]:
    """
    Cria um único span para a operação resiliente.

    Retries e mudanças do circuit breaker aparecem
    como eventos dentro deste mesmo span.
    """
    attributes = (
        build_resilience_operation_attributes(
            policy
        )
    )

    with traced_operation(
        (
            "inna.resilience."
            f"{policy.name}"
        ),
        attributes=attributes,
        instrumentation_name=(
            INSTRUMENTATION_NAME
        ),
    ) as span:
        yield span


def observe_runtime_resilience_event(
    event: ResilienceEvent,
) -> None:
    """
    Observer real do runtime de produção.

    Reliability e OTEL são independentes:
    uma falha em qualquer observer nunca altera
    o caminho funcional da aplicação.
    """
    try:
        observe_production_reliability_event(
            event
        )
    except Exception:
        pass

    try:
        observe_production_reliability_persistence_event(
            event
        )
    except Exception:
        pass

    observe_resilience_event(
        event
    )


def create_observed_resilience_runtime(
    **runtime_kwargs: Any,
) -> ResilienceRuntime:
    """
    Cria runtime com observer OTEL seguro.

    Permite injeção de clock/sleeper/random_source
    para testes determinísticos.
    """
    if "observer" in runtime_kwargs:
        raise TypeError(
            "observer is managed by "
            "create_observed_resilience_runtime()."
        )

    return ResilienceRuntime(
        observer=observe_runtime_resilience_event,
        **runtime_kwargs,
    )


_SHARED_RESILIENCE_RUNTIME = (
    create_observed_resilience_runtime()
)


def get_shared_resilience_runtime(
) -> ResilienceRuntime:
    """
    Retorna runtime compartilhado.

    O registry interno mantém o estado dos circuitos
    entre chamadas do mesmo processo.
    """
    return _SHARED_RESILIENCE_RUNTIME


__all__ = [
    "INSTRUMENTATION_NAME",
    "build_resilience_event_attributes",
    "build_resilience_operation_attributes",
    "create_observed_resilience_runtime",
    "get_shared_resilience_runtime",
    "observe_resilience_event",
    "observe_runtime_resilience_event",
    "traced_resilience_operation",
]


def _governor_attribute_value(
    value: object,
) -> object:
    """
    Normaliza enums para valores OTEL simples.
    """
    return getattr(
        value,
        "value",
        value,
    )


def build_reliability_governor_attributes(
    decision,
) -> dict[str, object]:
    """
    Gera somente atributos agregados e privacy-safe.

    Nunca inclui prompt, resposta, usuário,
    conteúdo RAG, credenciais ou mensagens
    de exceção.
    """
    attributes: dict[str, object] = {
        "reliability.governor.operation": (
            str(decision.operation)
        ),
        "reliability.governor.action": (
            str(
                _governor_attribute_value(
                    decision.action
                )
            )
        ),
        "reliability.governor.reason_code": (
            str(decision.reason_code)
        ),
        "reliability.governor.advisory_only": (
            bool(decision.advisory_only)
        ),
        "reliability.governor.shared_data_used": (
            bool(decision.shared_data_used)
        ),
        "reliability.governor.cache_stale": (
            bool(decision.cache_stale)
        ),
        (
            "reliability.governor."
            "database_unavailable"
        ): bool(
            decision.database_unavailable
        ),
        (
            "reliability.governor."
            "current_max_attempts"
        ): int(
            decision.current_max_attempts
        ),
        (
            "reliability.governor."
            "recommended_max_attempts"
        ): int(
            decision.recommended_max_attempts
        ),
        "reliability.governor.prefer_fallback": (
            bool(decision.prefer_fallback)
        ),
        "reliability.governor.fail_open": False,
    }

    source = getattr(
        decision,
        "source",
        None,
    )

    if source is not None:
        attributes[
            "reliability.governor.source"
        ] = str(
            _governor_attribute_value(
                source
            )
        )

    state = getattr(
        decision,
        "state",
        None,
    )

    if state is not None:
        attributes[
            "reliability.governor.state"
        ] = str(
            _governor_attribute_value(
                state
            )
        )

    burn_rate = getattr(
        decision,
        "burn_rate",
        None,
    )

    if burn_rate is not None:
        attributes[
            "reliability.governor.burn_rate"
        ] = float(
            burn_rate
        )

    return attributes


def observe_reliability_governor_decision(
    decision,
) -> None:
    """
    Registra a decisão do Reliability Governor
    no pipeline OTEL/Phoenix já existente.

    Falhas de telemetria nunca interferem
    no comportamento funcional.
    """
    try:
        attributes = (
            build_reliability_governor_attributes(
                decision
            )
        )

        with traced_operation(
            "inna.reliability.governor",
            attributes=attributes,
            instrumentation_name=(
                INSTRUMENTATION_NAME
            ),
        ) as span:
            if span is None:
                return

            span.add_event(
                (
                    "inna.reliability."
                    "governor.decision"
                ),
                attributes=attributes,
            )

    except Exception:
        return


def observe_reliability_governor_fail_open(
    *,
    operation: str,
    current_max_attempts: int,
    error_type: str,
) -> None:
    """
    Registra fail-open de forma privacy-safe.

    Apenas o tipo da exceção é observado;
    a mensagem da exceção nunca é enviada.
    """
    try:
        attributes: dict[str, object] = {
            "reliability.governor.operation": (
                str(operation)
            ),
            "reliability.governor.action": (
                "fail_open"
            ),
            "reliability.governor.fail_open": (
                True
            ),
            (
                "reliability.governor."
                "fallback_to_base_policy"
            ): True,
            (
                "reliability.governor."
                "current_max_attempts"
            ): int(
                current_max_attempts
            ),
            (
                "reliability.governor."
                "error_type"
            ): str(
                error_type
            ),
        }

        with traced_operation(
            (
                "inna.reliability."
                "governor.fail_open"
            ),
            attributes=attributes,
            instrumentation_name=(
                INSTRUMENTATION_NAME
            ),
        ) as span:
            if span is None:
                return

            span.add_event(
                (
                    "inna.reliability."
                    "governor.fail_open"
                ),
                attributes=attributes,
            )

    except Exception:
        return
