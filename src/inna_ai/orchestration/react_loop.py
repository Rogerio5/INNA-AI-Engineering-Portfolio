"""Loop ReAct governado e observável da INNA.

Fluxo:
planner -> tool -> observation -> planner

Observabilidade:
- react.execution
- react.planner
- react.tool

Não registra:
- prompt;
- mensagem do usuário;
- resposta;
- argumentos de ferramenta;
- output bruto;
- chain-of-thought.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Callable

from inna_ai.observability.phoenix.runtime import traced_operation
from inna_ai.governance.react_privacy import safe_error_record, sanitize_react_value
from inna_ai.orchestration.react_agent import REACT_MAX_ITERATIONS, ReactAction, ReactGovernanceError, executar_acao_react
from inna_ai.orchestration.react_planner import ReactPlannerDecision, planejar_proxima_acao_react


PlannerCallable = Callable[..., ReactPlannerDecision]


def _safe_execution_attributes() -> dict[str, Any]:
    return {
        "inna.react.component": "execution",
        "inna.react.max_iterations": REACT_MAX_ITERATIONS,
        "privacy.content_exported": False,
    }


def _safe_planner_attributes(
    iteration: int,
) -> dict[str, Any]:
    return {
        "inna.react.component": "planner",
        "inna.react.iteration": iteration,
        "privacy.content_exported": False,
    }


def _safe_tool_attributes(
    *,
    iteration: int,
    tool_name: str,
) -> dict[str, Any]:
    return {
        "inna.react.component": "tool",
        "inna.react.iteration": iteration,
        "inna.react.tool_name": tool_name,
        "privacy.content_exported": False,
    }


def _finalizar_span(
    span: Any,
    *,
    status: str,
    iteration: int,
    tool_count: int,
    hitl_required: bool,
) -> None:
    span.set_attribute(
        "inna.react.status",
        str(status),
    )

    span.set_attribute(
        "inna.react.iterations",
        int(iteration),
    )

    span.set_attribute(
        "inna.react.tool_count",
        int(tool_count),
    )

    span.set_attribute(
        "inna.react.hitl_required",
        bool(hitl_required),
    )


def executar_loop_react(
    *,
    user_message: str,
    history: list[dict[str, Any]] | None = None,
    parent_trace_id: str | None = None,
    usuario_id: str | None = None,
    request_id: str | None = None,
    planner: PlannerCallable = planejar_proxima_acao_react,
) -> dict[str, Any]:
    """
    Executa o ciclo ReAct governado.

    Encerra em:
    - finish;
    - human_review;
    - bloqueio de governança;
    - limite máximo de iterações.
    """

    react_history = [
        sanitize_react_value(
            deepcopy(item)
        )
        for item in list(history or [])
        if isinstance(item, dict)
    ]

    tool_results: list[dict[str, Any]] = []

    with traced_operation(
        "inna.react.execution",
        attributes=_safe_execution_attributes(),
        instrumentation_name=(
            "inna.observability.react"
        ),
    ) as execution_span:

        for iteration in range(
            1,
            REACT_MAX_ITERATIONS + 1,
        ):

            # ==================================================
            # PLANNER
            # ==================================================

            with traced_operation(
                "inna.react.planner",
                attributes=_safe_planner_attributes(
                    iteration
                ),
                instrumentation_name=(
                    "inna.observability.react"
                ),
            ) as planner_span:

                decision = planner(
                    user_message=user_message,
                    iteration=iteration,
                    history=react_history,
                    usuario_id=usuario_id,
                    trace_id=parent_trace_id,
                    request_id=request_id,
                )

                planner_span.set_attribute(
                    "inna.react.action",
                    decision.action,
                )

                planner_span.set_attribute(
                    "inna.react.confidence",
                    float(decision.confidence),
                )

                planner_span.set_attribute(
                    "inna.react.reason_code",
                    decision.reason_code,
                )

                if decision.tool_name:
                    planner_span.set_attribute(
                        "inna.react.tool_name",
                        decision.tool_name,
                    )

            decision_record = {
                "iteration": iteration,
                "decision": decision.action,
                "tool_name": decision.tool_name,
                "reason_code": decision.reason_code,
                "confidence": decision.confidence,
            }

            # ==================================================
            # FINISH
            # ==================================================

            if decision.action == "finish":
                react_history.append(
                    {
                        **decision_record,
                        "status": "finished",
                    }
                )

                _finalizar_span(
                    execution_span,
                    status="finished",
                    iteration=iteration,
                    tool_count=len(tool_results),
                    hitl_required=False,
                )

                return {
                    "react_status": "finished",
                    "react_iteration": iteration,
                    "react_action": {},
                    "react_history": react_history,
                    "react_last_observation": {},
                    "current_agent": "react_agent",
                    "response": sanitize_react_value(
                        decision.final_response
                    ),
                    "tool_results": tool_results,
                    "confidence": (
                        decision.confidence
                    ),
                    "human_review_force_required": False,
                }

            # ==================================================
            # HITL
            # ==================================================

            if decision.action == "human_review":
                react_history.append(
                    {
                        **decision_record,
                        "status": (
                            "human_review_required"
                        ),
                    }
                )

                _finalizar_span(
                    execution_span,
                    status="human_review_required",
                    iteration=iteration,
                    tool_count=len(tool_results),
                    hitl_required=True,
                )

                return {
                    "react_status": (
                        "human_review_required"
                    ),
                    "react_iteration": iteration,
                    "react_action": {},
                    "react_history": react_history,
                    "react_last_observation": {},
                    "current_agent": "react_agent",
                    "tool_results": tool_results,
                    "confidence": (
                        decision.confidence
                    ),
                    "human_review_force_required": True,
                }

            # ==================================================
            # TOOL
            # ==================================================

            action = ReactAction(
                tool_name=decision.tool_name,
                arguments=dict(
                    decision.arguments
                ),
                iteration=iteration,
            )

            try:

                with traced_operation(
                    "inna.react.tool",
                    attributes=_safe_tool_attributes(
                        iteration=iteration,
                        tool_name=action.tool_name,
                    ),
                    instrumentation_name=(
                        "inna.observability.react"
                    ),
                ) as tool_span:

                    observation = (
                        executar_acao_react(
                            action,
                            parent_trace_id=(
                                parent_trace_id
                            ),
                            **(
                                {
                                    "user_id": usuario_id
                                }
                                if usuario_id
                                else {}
                            ),
                        )
                    )

                    tool_span.set_attribute(
                        "inna.react.tool_status",
                        observation.status,
                    )

                    tool_span.set_attribute(
                        "inna.react.tool_duration_ms",
                        float(
                            observation.duration_ms
                        ),
                    )

                    tool_span.set_attribute(
                        "inna.react.requested_by",
                        observation.requested_by,
                    )

            except ReactGovernanceError as exc:

                react_history.append(
                    {
                        **decision_record,
                        "status": "blocked",
                        **safe_error_record(exc),
                    }
                )

                _finalizar_span(
                    execution_span,
                    status="blocked",
                    iteration=iteration,
                    tool_count=len(tool_results),
                    hitl_required=True,
                )

                return {
                    "react_status": "blocked",
                    "react_iteration": iteration,
                    "react_action": {
                        "tool_name": action.tool_name,
                        "iteration": action.iteration,
                        "arguments_redacted": True,
                    },
                    "react_history": react_history,
                    "react_last_observation": {
                        **safe_error_record(exc),
                    },
                    "current_agent": "react_agent",
                    "tool_results": tool_results,
                    "human_review_force_required": True,
                }

            observation_dict = sanitize_react_value(
                observation.model_dump()
            )

            react_history.append(
                {
                    **decision_record,
                    **observation_dict,
                }
            )

            tool_results.append(
                {
                    "tool_name": (
                        observation.tool_name
                    ),
                    "status": observation.status,
                    "ok": observation.status
                    in {
                        "success",
                        "completed",
                        "ok",
                    },
                    "output": sanitize_react_value(
                        deepcopy(
                            observation.output
                        )
                    ),
                    "iteration": iteration,
                    "trace_id": (
                        observation.trace_id
                    ),
                    "duration_ms": (
                        observation.duration_ms
                    ),
                }
            )

        # ======================================================
        # LIMITE
        # ======================================================

        _finalizar_span(
            execution_span,
            status="iteration_limit",
            iteration=REACT_MAX_ITERATIONS,
            tool_count=len(tool_results),
            hitl_required=True,
        )

        return {
            "react_status": "iteration_limit",
            "react_iteration": REACT_MAX_ITERATIONS,
            "react_action": {},
            "react_history": react_history,
            "react_last_observation": {},
            "current_agent": "react_agent",
            "tool_results": tool_results,
            "human_review_force_required": True,
        }


__all__ = [
    "executar_loop_react",
]




