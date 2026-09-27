"""Tracing seguro das execuções LangGraph da INNA."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from typing import Any

from inna_ai.observability.phoenix.privacy import hash_identifier
from inna_ai.observability.phoenix.runtime import traced_operation


def _hash_optional(value: object | None) -> str | None:
    if value is None:
        return None

    normalized = str(value).strip()

    if not normalized:
        return None

    return hash_identifier(normalized)


def build_langgraph_attributes(
    *,
    execution_mode: str,
    thread_id: str | None = None,
    user_id: str | None = None,
    language: str | None = None,
    currency: str | None = None,
    human_review_enabled: bool | None = None,
) -> dict[str, Any]:
    """
    Monta apenas metadados técnicos seguros.

    Mensagem, histórico, resposta, contexto financeiro e decisão
    humana nunca são incluídos.
    """

    attributes: dict[str, Any] = {
        "agent.framework": "langgraph",
        "agent.application": "inna",
        "agent.execution_mode": execution_mode,
        "privacy.content_exported": False,
    }

    thread_hash = _hash_optional(thread_id)
    user_hash = _hash_optional(user_id)

    if thread_hash:
        attributes["inna.thread_id_hash"] = thread_hash

    if user_hash:
        attributes["enduser.id_hash"] = user_hash

    if language:
        attributes["inna.language"] = str(language)

    if currency:
        attributes["inna.currency"] = str(currency)

    if human_review_enabled is not None:
        attributes["inna.human_review_enabled"] = bool(
            human_review_enabled
        )

    return attributes


def add_langgraph_result_attributes(
    span: Any,
    result: Mapping[str, Any] | None,
) -> None:
    """Adiciona ao span somente resultados operacionais seguros."""

    if not isinstance(result, Mapping):
        span.set_attribute("agent.result_available", False)
        return

    span.set_attribute("agent.result_available", True)

    safe_fields = {
        "agent.execution_steps": result.get(
            "execution_steps",
            0,
        ),
        "agent.handoff_count": result.get(
            "handoff_count",
            0,
        ),
        "agent.human_review_count": result.get(
            "human_review_count",
            0,
        ),
        "agent.loop_detected": bool(
            result.get("loop_detected", False)
        ),
        "agent.execution_budget_exceeded": bool(
            result.get(
                "execution_budget_exceeded",
                False,
            )
        ),
        "agent.handoff_limit_exceeded": bool(
            result.get(
                "handoff_limit_exceeded",
                False,
            )
        ),
        "agent.human_review_required": bool(
            result.get(
                "human_review_required",
                False,
            )
        ),
    }

    # Semana 5 - métricas agregadas da arquitetura
    # multiagente. Somente valores operacionais seguros;
    # nenhum payload, mensagem, resposta ou decisão humana.
    week5_safe_fields = {
        "agent.a2a_message_count": result.get(
            "a2a_message_count",
            0,
        ),
        "agent.blackboard_entry_count": result.get(
            "shared_blackboard_count",
            0,
        ),
        "agent.supervisor_mesh_visited_count": result.get(
            "supervisor_mesh_visited_count",
            0,
        ),
        "agent.supervisor_mesh_active": bool(
            result.get(
                "supervisor_mesh_active",
                False,
            )
        ),
        "agent.human_review_limit_exceeded": bool(
            result.get(
                "human_review_limit_exceeded",
                False,
            )
        ),
        "agent.adaptive_multi_domain": bool(
            result.get(
                "adaptive_multi_domain",
                False,
            )
        ),
    }

    completion_score = result.get(
        "task_completion_score"
    )

    if isinstance(
        completion_score,
        (int, float),
    ) and not isinstance(
        completion_score,
        bool,
    ):
        week5_safe_fields[
            "agent.task_completion_score"
        ] = float(
            completion_score
        )

    for name, value in (
        (
            "agent.adaptive_risk",
            result.get(
                "adaptive_risk"
            ),
        ),
        (
            "agent.adaptive_route_type",
            result.get(
                "adaptive_route_type"
            )
            or result.get(
                "route_type"
            ),
        ),
        (
            "agent.supervisor_mesh_status",
            result.get(
                "supervisor_mesh_status"
            ),
        ),
        (
            "agent.human_review_status",
            result.get(
                "human_review_status"
            ),
        ),
        (
            "agent.task_status",
            result.get(
                "task_status"
            ),
        ),
    ):
        normalized = str(
            value or ""
        ).strip()

        if normalized:
            week5_safe_fields[
                name
            ] = normalized

    for field_name, state_field in (
        (
            "agent.a2a_history_count",
            "a2a_history",
        ),
        (
            "agent.blackboard_audit_count",
            "shared_blackboard_audit",
        ),
        (
            "agent.supervisor_mesh_history_count",
            "supervisor_mesh_history",
        ),
        (
            "agent.supervisor_mesh_visit_history_count",
            "supervisor_mesh_visit_history",
        ),
    ):
        items = result.get(
            state_field
        )

        if isinstance(
            items,
            list,
        ):
            week5_safe_fields[
                field_name
            ] = len(
                items
            )

    safe_fields.update(
        week5_safe_fields
    )

    route = str(
        result.get("next_node")
        or result.get("current_agent")
        or result.get("team_route")
        or ""
    ).strip()

    team = str(
        result.get("current_team")
        or result.get("team_supervisor")
        or ""
    ).strip()

    if route:
        safe_fields["agent.final_route"] = route

    if team:
        safe_fields["agent.final_team"] = team

    errors = result.get("errors")

    if isinstance(errors, list):
        safe_fields["agent.error_count"] = len(errors)

    route_history = result.get("route_history")

    if isinstance(route_history, list):
        safe_fields["agent.route_count"] = len(
            route_history
        )

    tool_results = result.get("tool_results")

    if isinstance(tool_results, list):
        safe_fields["agent.tool_result_count"] = len(
            tool_results
        )

    for name, value in safe_fields.items():
        if isinstance(value, (bool, int, float, str)):
            span.set_attribute(name, value)


def build_langgraph_node_attributes(
    *,
    node_name: str,
    state: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Monta atributos seguros de um nó LangGraph.

    Não exporta mensagem, resposta, contexto,
    payload A2A, Blackboard ou decisão humana.
    """

    normalized_node = str(
        node_name
    ).strip()

    if not normalized_node:
        raise ValueError(
            "node_name não pode ser vazio."
        )

    attributes: dict[str, Any] = {
        "agent.framework": "langgraph",
        "agent.application": "inna",
        "agent.node.name": normalized_node,
        "privacy.content_exported": False,
    }

    if not isinstance(
        state,
        Mapping,
    ):
        return attributes

    thread_hash = _hash_optional(
        state.get(
            "thread_id"
        )
    )

    user_hash = _hash_optional(
        state.get(
            "user_id"
        )
    )

    if thread_hash:
        attributes[
            "inna.thread_id_hash"
        ] = thread_hash

    if user_hash:
        attributes[
            "enduser.id_hash"
        ] = user_hash

    string_fields = (
        (
            "agent.current_agent",
            "current_agent",
        ),
        (
            "agent.current_team",
            "current_team",
        ),
        (
            "agent.adaptive_risk",
            "adaptive_risk",
        ),
        (
            "agent.adaptive_route_type",
            "adaptive_route_type",
        ),
        (
            "agent.supervisor_mesh_status",
            "supervisor_mesh_status",
        ),
        (
            "agent.task_status",
            "task_status",
        ),
        (
            "agent.human_review_status",
            "human_review_status",
        ),
    )

    for attribute_name, state_name in (
        string_fields
    ):
        value = str(
            state.get(
                state_name
            )
            or ""
        ).strip()

        if value:
            attributes[
                attribute_name
            ] = value

    count_fields = (
        (
            "agent.execution_steps",
            "execution_steps",
        ),
        (
            "agent.handoff_count",
            "handoff_count",
        ),
        (
            "agent.a2a_message_count",
            "a2a_message_count",
        ),
        (
            "agent.blackboard_entry_count",
            "shared_blackboard_count",
        ),
        (
            "agent.supervisor_mesh_visited_count",
            "supervisor_mesh_visited_count",
        ),
        (
            "agent.human_review_count",
            "human_review_count",
        ),
    )

    for attribute_name, state_name in (
        count_fields
    ):
        value = state.get(
            state_name
        )

        if (
            isinstance(
                value,
                int,
            )
            and not isinstance(
                value,
                bool,
            )
            and value >= 0
        ):
            attributes[
                attribute_name
            ] = value

    bool_fields = (
        (
            "agent.supervisor_mesh_active",
            "supervisor_mesh_active",
        ),
        (
            "agent.adaptive_multi_domain",
            "adaptive_multi_domain",
        ),
        (
            "agent.human_review_required",
            "human_review_required",
        ),
        (
            "agent.human_review_limit_exceeded",
            "human_review_limit_exceeded",
        ),
    )

    for attribute_name, state_name in (
        bool_fields
    ):
        value = state.get(
            state_name
        )

        if isinstance(
            value,
            bool,
        ):
            attributes[
                attribute_name
            ] = value

    return attributes


def add_langgraph_node_result_attributes(
    span: Any,
    result: Mapping[str, Any] | None,
) -> None:
    """
    Adiciona somente o resultado operacional
    seguro produzido por um nó.
    """

    if not isinstance(
        result,
        Mapping,
    ):
        span.set_attribute(
            "agent.node.result_available",
            False,
        )
        return

    span.set_attribute(
        "agent.node.result_available",
        True,
    )

    span.set_attribute(
        "agent.node.update_field_count",
        len(result),
    )

    string_fields = (
        (
            "agent.node.current_agent",
            "current_agent",
        ),
        (
            "agent.node.current_team",
            "current_team",
        ),
        (
            "agent.node.adaptive_risk",
            "adaptive_risk",
        ),
        (
            "agent.node.adaptive_route_type",
            "adaptive_route_type",
        ),
        (
            "agent.node.supervisor_mesh_status",
            "supervisor_mesh_status",
        ),
        (
            "agent.node.task_status",
            "task_status",
        ),
        (
            "agent.node.human_review_status",
            "human_review_status",
        ),
    )

    for attribute_name, result_name in (
        string_fields
    ):
        value = str(
            result.get(
                result_name
            )
            or ""
        ).strip()

        if value:
            span.set_attribute(
                attribute_name,
                value,
            )

    count_fields = (
        (
            "agent.node.execution_steps",
            "execution_steps",
        ),
        (
            "agent.node.handoff_count",
            "handoff_count",
        ),
        (
            "agent.node.a2a_message_count",
            "a2a_message_count",
        ),
        (
            "agent.node.blackboard_entry_count",
            "shared_blackboard_count",
        ),
        (
            "agent.node.supervisor_mesh_visited_count",
            "supervisor_mesh_visited_count",
        ),
        (
            "agent.node.human_review_count",
            "human_review_count",
        ),
    )

    for attribute_name, result_name in (
        count_fields
    ):
        value = result.get(
            result_name
        )

        if (
            isinstance(
                value,
                int,
            )
            and not isinstance(
                value,
                bool,
            )
            and value >= 0
        ):
            span.set_attribute(
                attribute_name,
                value,
            )

    bool_fields = (
        (
            "agent.node.supervisor_mesh_active",
            "supervisor_mesh_active",
        ),
        (
            "agent.node.adaptive_multi_domain",
            "adaptive_multi_domain",
        ),
        (
            "agent.node.human_review_required",
            "human_review_required",
        ),
        (
            "agent.node.human_review_limit_exceeded",
            "human_review_limit_exceeded",
        ),
        (
            "agent.node.handoff_limit_exceeded",
            "handoff_limit_exceeded",
        ),
    )

    for attribute_name, result_name in (
        bool_fields
    ):
        value = result.get(
            result_name
        )

        if isinstance(
            value,
            bool,
        ):
            span.set_attribute(
                attribute_name,
                value,
            )


@contextmanager
def traced_langgraph_node(
    *,
    node_name: str,
    state: Mapping[str, Any] | None = None,
) -> Iterator[Any]:
    """
    Cria um span seguro para uma etapa do grafo.

    Quando executado dentro de
    traced_langgraph_execution(), reutiliza o
    contexto OpenTelemetry já ativo.
    """

    normalized_node = str(
        node_name
    ).strip()

    attributes = (
        build_langgraph_node_attributes(
            node_name=normalized_node,
            state=state,
        )
    )

    with traced_operation(
        (
            "inna.langgraph.node."
            f"{normalized_node}"
        ),
        attributes=attributes,
        instrumentation_name=(
            "inna.agents.langgraph"
        ),
    ) as span:
        yield span


@contextmanager
def traced_langgraph_execution(
    *,
    execution_mode: str,
    thread_id: str | None = None,
    user_id: str | None = None,
    language: str | None = None,
    currency: str | None = None,
    human_review_enabled: bool | None = None,
) -> Iterator[Any]:
    """Cria o trace raiz de uma execução agentic da INNA."""

    attributes = build_langgraph_attributes(
        execution_mode=execution_mode,
        thread_id=thread_id,
        user_id=user_id,
        language=language,
        currency=currency,
        human_review_enabled=human_review_enabled,
    )

    with traced_operation(
        "inna.langgraph.execution",
        attributes=attributes,
        instrumentation_name="inna.agents.langgraph",
    ) as span:
        yield span


__all__ = [
    "add_langgraph_node_result_attributes",
    "add_langgraph_result_attributes",
    "build_langgraph_attributes",
    "build_langgraph_node_attributes",
    "traced_langgraph_execution",
    "traced_langgraph_node",
]
