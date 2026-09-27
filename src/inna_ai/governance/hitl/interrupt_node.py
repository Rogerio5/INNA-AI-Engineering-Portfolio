from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

from langgraph.types import interrupt

from inna_ai.governance.hitl.lifecycle import HumanReviewError, approve_human_review, cancel_human_review, correct_human_review, reject_human_review
from inna_ai.orchestration.state import InnaAgentState


_PENDING_STATUSES = {
    "requested",
    "waiting",
}

_TERMINAL_STATUSES = {
    "approved",
    "corrected",
    "rejected",
    "cancelled",
    "expired",
    "failed",
}

_ALLOWED_ACTIONS = {
    "approve",
    "correct",
    "reject",
    "cancel",
}


def _normalize_text(
    value: Any,
) -> str:
    return str(
        value or ""
    ).strip()


def _safe_mapping(
    value: Any,
) -> Mapping[str, Any]:
    if isinstance(
        value,
        Mapping,
    ):
        return value

    return {}


def _current_review(
    state: InnaAgentState,
) -> dict[str, Any]:
    current = state.get(
        "human_review_current",
        {},
    )

    if not isinstance(
        current,
        dict,
    ) or not current:
        raise HumanReviewError(
            "Não existe revisão humana atual."
        )

    return deepcopy(
        current
    )


def _review_history(
    state: InnaAgentState,
) -> list[dict[str, Any]]:
    history = state.get(
        "human_review_history",
        [],
    )

    if not isinstance(
        history,
        list,
    ):
        return []

    return [
        deepcopy(item)
        for item in history
        if isinstance(
            item,
            dict,
        )
    ]


def _append_trace(
    state: InnaAgentState,
    event: str,
) -> list[str]:
    trace = list(
        state.get(
            "trace",
            [],
        )
    )

    trace.append(
        event
    )

    return trace


def _replace_review_in_history(
    history: list[dict[str, Any]],
    resolved_review: dict[str, Any],
) -> list[dict[str, Any]]:
    review_id = _normalize_text(
        resolved_review.get(
            "review_id"
        )
    )

    updated: list[
        dict[str, Any]
    ] = []

    replaced = False

    for item in history:
        item_id = _normalize_text(
            item.get(
                "review_id"
            )
        )

        if (
            review_id
            and item_id == review_id
        ):
            updated.append(
                deepcopy(
                    resolved_review
                )
            )

            replaced = True
            continue

        updated.append(
            deepcopy(
                item
            )
        )

    if not replaced:
        updated.append(
            deepcopy(
                resolved_review
            )
        )

    return updated


def _interrupt_payload(
    state: InnaAgentState,
    review: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "type": "human_review",
        "version": "1.0",
        "review_id": _normalize_text(
            review.get(
                "review_id"
            )
        ),
        "thread_id": _normalize_text(
            review.get(
                "thread_id"
            )
            or state.get(
                "thread_id"
            )
        ),
        "status": _normalize_text(
            review.get(
                "status"
            )
        ),
        "requested_by": _normalize_text(
            review.get(
                "requested_by"
            )
        ),
        "reason": _normalize_text(
            review.get(
                "reason"
            )
        ),
        "trigger": _normalize_text(
            review.get(
                "trigger"
            )
        ),
        "risk_level": _normalize_text(
            review.get(
                "risk_level"
            )
        ),
        "payload": deepcopy(
            dict(
                _safe_mapping(
                    review.get(
                        "payload"
                    )
                )
            )
        ),
        "allowed_actions": [
            "approve",
            "correct",
            "reject",
            "cancel",
        ],
        "required_fields": {
            "approve": [
                "reviewer_id",
            ],
            "correct": [
                "reviewer_id",
                "corrections",
            ],
            "reject": [
                "reviewer_id",
                "reason",
            ],
            "cancel": [
                "reviewer_id",
            ],
        },
    }


def _normalize_resume_payload(
    value: Any,
) -> dict[str, Any]:
    if not isinstance(
        value,
        Mapping,
    ):
        raise HumanReviewError(
            "A retomada da revisão humana deve "
            "ser um objeto."
        )

    payload = deepcopy(
        dict(value)
    )

    action = _normalize_text(
        payload.get(
            "action"
        )
    ).lower()

    if action not in _ALLOWED_ACTIONS:
        raise HumanReviewError(
            "Ação de revisão humana inválida: "
            f"{action!r}."
        )

    reviewer_id = _normalize_text(
        payload.get(
            "reviewer_id"
        )
    )

    if not reviewer_id:
        raise HumanReviewError(
            "reviewer_id é obrigatório."
        )

    corrections = payload.get(
        "corrections",
        {},
    )

    if corrections is None:
        corrections = {}

    if not isinstance(
        corrections,
        dict,
    ):
        raise HumanReviewError(
            "corrections deve ser um objeto."
        )

    normalized = {
        "action": action,
        "reviewer_id": reviewer_id,
        "comment": _normalize_text(
            payload.get(
                "comment"
            )
        ),
        "reason": _normalize_text(
            payload.get(
                "reason"
            )
        ),
        "corrections": deepcopy(
            corrections
        ),
    }

    if (
        action == "correct"
        and not normalized[
            "corrections"
        ]
    ):
        raise HumanReviewError(
            "A ação correct exige pelo menos "
            "uma correção."
        )

    if (
        action == "reject"
        and not normalized[
            "reason"
        ]
    ):
        raise HumanReviewError(
            "A ação reject exige reason."
        )

    return normalized


def _resolve_review(
    review: dict[str, Any],
    resume_payload: dict[str, Any],
) -> dict[str, Any]:
    action = resume_payload[
        "action"
    ]

    reviewer_id = resume_payload[
        "reviewer_id"
    ]

    comment = resume_payload[
        "comment"
    ]

    if action == "approve":
        return approve_human_review(
            review,
            reviewer_id=reviewer_id,
            comment=comment,
        )

    if action == "correct":
        return correct_human_review(
            review,
            reviewer_id=reviewer_id,
            corrections=resume_payload[
                "corrections"
            ],
            comment=comment,
        )

    if action == "reject":
        return reject_human_review(
            review,
            reviewer_id=reviewer_id,
            reason=resume_payload[
                "reason"
            ],
        )

    if action == "cancel":
        return cancel_human_review(
            review,
            reviewer_id=reviewer_id,
            reason=(
                resume_payload[
                    "reason"
                ]
                or comment
            ),
        )

    raise HumanReviewError(
        "Ação de revisão humana não suportada: "
        f"{action!r}."
    )


def _resume_route(
    status: str,
) -> str:
    routes = {
        "approved": "handoff_coordinator",
        "corrected": "team_router",
        "rejected": "conversation_summary",
        "cancelled": "conversation_summary",
        "expired": "conversation_summary",
        "failed": "conversation_summary",
    }

    try:
        return routes[
            status
        ]
    except KeyError as exc:
        raise HumanReviewError(
            "Status terminal sem rota de retomada: "
            f"{status!r}."
        ) from exc


def _structured_response(
    state: InnaAgentState,
    *,
    resolved_review: Mapping[str, Any],
    resume_payload: Mapping[str, Any],
    route: str,
) -> dict[str, Any]:
    structured = state.get(
        "structured_response",
        {},
    )

    if not isinstance(
        structured,
        dict,
    ):
        structured = {}

    updated = deepcopy(
        structured
    )

    updated[
        "human_review_result"
    ] = {
        "review_id": _normalize_text(
            resolved_review.get(
                "review_id"
            )
        ),
        "status": _normalize_text(
            resolved_review.get(
                "status"
            )
        ),
        "decision": deepcopy(
            resolved_review.get(
                "decision"
            )
        ),
        "resume_payload": deepcopy(
            dict(
                resume_payload
            )
        ),
        "resume_route": route,
    }

    return updated


def human_review_interrupt_node(
    state: InnaAgentState,
) -> dict[str, Any]:
    """
    Interrompe o LangGraph e aguarda uma decisão.

    Nenhum efeito externo deve ser executado antes
    da chamada de interrupt().
    """
    review = _current_review(
        state
    )

    status = _normalize_text(
        review.get(
            "status"
        )
    )

    if status in _TERMINAL_STATUSES:
        route = _resume_route(
            status
        )

        return {
            "human_review_required": False,
            "human_review_status": status,
            "human_review_resume_route": route,
            "trace": _append_trace(
                state,
                (
                    "human_review_interrupt:"
                    "already_resolved:"
                    f"{review.get('review_id')}:{status}"
                ),
            ),
        }

    if status not in _PENDING_STATUSES:
        raise HumanReviewError(
            "Status inválido para interrupção: "
            f"{status!r}."
        )

    raw_resume_payload = interrupt(
        _interrupt_payload(
            state,
            review,
        )
    )

    resume_payload = (
        _normalize_resume_payload(
            raw_resume_payload
        )
    )

    resolved_review = _resolve_review(
        review,
        resume_payload,
    )

    resolved_status = _normalize_text(
        resolved_review.get(
            "status"
        )
    )

    route = _resume_route(
        resolved_status
    )

    history = _replace_review_in_history(
        _review_history(
            state
        ),
        resolved_review,
    )

    return {
        "human_review_required": False,
        "human_review_current": (
            resolved_review
        ),
        "human_review_history": history,
        "human_review_status": (
            resolved_status
        ),
        "human_review_resume_payload": (
            deepcopy(
                resume_payload
            )
        ),
        "human_review_decision_action": (
            resume_payload[
                "action"
            ]
        ),
        "human_review_corrections": (
            deepcopy(
                resume_payload[
                    "corrections"
                ]
            )
        ),
        "human_review_resume_route": route,
        "structured_response": (
            _structured_response(
                state,
                resolved_review=resolved_review,
                resume_payload=resume_payload,
                route=route,
            )
        ),
        "trace": _append_trace(
            state,
            (
                "human_review_interrupt:"
                f"resolved:{review.get('review_id')}:"
                f"{resolved_status}:"
                f"{route}"
            ),
        ),
    }


def select_route_after_human_review_interrupt(
    state: InnaAgentState,
) -> str:
    route = _normalize_text(
        state.get(
            "human_review_resume_route"
        )
    )

    allowed = {
        "handoff_coordinator",
        "team_router",
        "conversation_summary",
    }

    if route not in allowed:
        raise HumanReviewError(
            "Rota de retomada Human-in-the-Loop "
            f"inválida: {route!r}."
        )

    return route


__all__ = [
    "human_review_interrupt_node",
    "select_route_after_human_review_interrupt",
]
