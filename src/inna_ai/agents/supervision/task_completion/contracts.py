"""
Contrato determinístico de conclusão de tarefas da INNA.

Este módulo avalia se uma solicitação foi concluída,
parcialmente concluída, bloqueada ou se ainda depende
de informações do usuário.
"""

from __future__ import annotations

from typing import Any, Literal, TypedDict


TaskStatus = Literal[
    "pending",
    "in_progress",
    "completed",
    "partially_completed",
    "needs_user_input",
    "blocked",
    "failed",
    "cancelled",
]


class TaskCompletionResult(TypedDict):
    task_status: TaskStatus
    task_requirements: list[str]
    completed_requirements: list[str]
    missing_requirements: list[str]
    task_block_reason: str
    task_completion_score: float
    task_completion_evidence: dict[str, Any]


def _normalize_requirements(
    values: list[str] | None,
) -> list[str]:
    normalized: list[str] = []

    for value in values or []:
        item = str(value).strip()

        if (
            item
            and item not in normalized
        ):
            normalized.append(item)

    return normalized


def evaluate_task_completion(
    *,
    requirements: list[str] | None,
    completed: list[str] | None,
    needs_user_input: bool = False,
    blocked: bool = False,
    failed: bool = False,
    cancelled: bool = False,
    block_reason: str = "",
    evidence: dict[str, Any] | None = None,
) -> TaskCompletionResult:
    """
    Avalia a conclusão de uma tarefa sem depender de LLM.

    A prioridade dos estados é:
    cancelled -> failed -> blocked -> needs_user_input
    -> completed -> partially_completed -> pending.
    """
    normalized_requirements = (
        _normalize_requirements(
            requirements
        )
    )

    normalized_completed = [
        item
        for item in _normalize_requirements(
            completed
        )
        if item in normalized_requirements
    ]

    missing = [
        requirement
        for requirement in normalized_requirements
        if requirement not in normalized_completed
    ]

    total = len(
        normalized_requirements
    )

    completion_score = (
        len(normalized_completed) / total
        if total
        else 0.0
    )

    if cancelled:
        status: TaskStatus = "cancelled"

    elif failed:
        status = "failed"

    elif blocked:
        status = "blocked"

    elif needs_user_input:
        status = "needs_user_input"

    elif (
        total > 0
        and not missing
    ):
        status = "completed"

    elif normalized_completed:
        status = "partially_completed"

    elif total:
        status = "pending"

    else:
        status = "completed"

    reason = str(
        block_reason or ""
    ).strip()

    if (
        status
        in {
            "blocked",
            "failed",
            "needs_user_input",
            "cancelled",
        }
        and not reason
    ):
        reason = (
            "A tarefa não pôde ser concluída "
            "no estado atual."
        )

    return {
        "task_status": status,
        "task_requirements": (
            normalized_requirements
        ),
        "completed_requirements": (
            normalized_completed
        ),
        "missing_requirements": missing,
        "task_block_reason": reason,
        "task_completion_score": round(
            completion_score,
            4,
        ),
        "task_completion_evidence": dict(
            evidence or {}
        ),
    }


__all__ = [
    "TaskCompletionResult",
    "TaskStatus",
    "evaluate_task_completion",
]
