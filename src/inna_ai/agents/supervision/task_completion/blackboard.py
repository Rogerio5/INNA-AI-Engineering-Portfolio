"""Publicação governada de Task Completion no Blackboard."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from inna_ai.agents.registry.agent_catalog import DEFAULT_AGENT_REGISTRY
from inna_ai.governance.blackboard.runtime import publish_shared_blackboard


def _normalize_text(
    value: Any,
) -> str:
    return str(
        value or ""
    ).strip()


def _safe_string_list(
    value: Any,
) -> list[str]:
    if not isinstance(
        value,
        (list, tuple),
    ):
        return []

    return [
        normalized
        for item in value
        if (
            normalized := _normalize_text(
                item
            )
        )
    ]


def _active_agent_team(
    agent_id: str,
) -> str | None:
    for definition in (
        DEFAULT_AGENT_REGISTRY.list_definitions(
            active_only=True
        )
    ):
        if (
            definition.agent_id
            == agent_id
            and definition.kind
            == "agent"
        ):
            return definition.team

    return None


def build_task_completion_blackboard_payload(
    completion: Mapping[str, Any],
) -> dict[str, Any]:
    """
    Constrói somente metadados derivados.

    Não copia response, user_message, errors,
    structured_response, tool_results ou context.
    """

    completed_requirements = (
        _safe_string_list(
            completion.get(
                "completed_requirements"
            )
        )
    )

    missing_requirements = (
        _safe_string_list(
            completion.get(
                "missing_requirements"
            )
        )
    )

    evidence = completion.get(
        "task_completion_evidence",
        {},
    )

    if not isinstance(
        evidence,
        Mapping,
    ):
        evidence = {}

    tool_results_count = (
        evidence.get(
            "tool_results_count",
            0,
        )
    )

    try:
        normalized_tool_results_count = max(
            0,
            int(
                tool_results_count
                or 0
            ),
        )
    except (
        TypeError,
        ValueError,
    ):
        normalized_tool_results_count = 0

    score = completion.get(
        "task_completion_score",
        0.0,
    )

    try:
        normalized_score = float(
            score
            or 0.0
        )
    except (
        TypeError,
        ValueError,
    ):
        normalized_score = 0.0

    return {
        "task_status": _normalize_text(
            completion.get(
                "task_status"
            )
        ),
        "task_completion_score": (
            normalized_score
        ),
        "completed_requirements": (
            completed_requirements
        ),
        "missing_requirements": (
            missing_requirements
        ),
        "response_generated": (
            "response_generation"
            in completed_requirements
        ),
        "tool_results_count": (
            normalized_tool_results_count
        ),
        "agent_resolution": (
            _normalize_text(
                evidence.get(
                    "agent_resolution"
                )
            )
            or "unresolved"
        ),
    }


def publish_task_completion_blackboard(
    state: Mapping[str, Any],
    completion: Mapping[str, Any],
) -> dict[str, Any]:
    """Publica o resultado operacional da conclusão."""

    current_agent = _normalize_text(
        completion.get(
            "current_agent"
        )
        or state.get(
            "current_agent"
        )
    )

    if not current_agent:
        return {}

    team = _active_agent_team(
        current_agent
    )

    if team is None:
        return {}

    # Fallback permanece isolado na própria equipe.
    if current_agent == "fallback_agent":
        visibility = "team"
        publish_team = team
    else:
        visibility = "workflow"
        publish_team = None

    merged_state = dict(
        state
    )

    merged_state.update(
        dict(
            completion
        )
    )

    update = publish_shared_blackboard(
        merged_state,
        principal=current_agent,
        kind="result",
        visibility=visibility,
        team=publish_team,
        payload=(
            build_task_completion_blackboard_payload(
                completion
            )
        ),
    )

    # O Task Completion continua sendo o último evento
    # semântico do trace deste nó. O Blackboard possui
    # auditoria própria.
    update.pop(
        "trace",
        None,
    )

    return update


__all__ = [
    "build_task_completion_blackboard_payload",
    "publish_task_completion_blackboard",
]
