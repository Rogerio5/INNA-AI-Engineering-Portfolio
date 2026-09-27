from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Literal, TypedDict
from uuid import uuid4


HumanReviewStatus = Literal[
    "requested",
    "waiting",
    "approved",
    "corrected",
    "rejected",
    "cancelled",
    "expired",
    "failed",
]

HumanReviewAction = Literal[
    "approve",
    "correct",
    "reject",
    "cancel",
]

HumanReviewRiskLevel = Literal[
    "low",
    "medium",
    "high",
    "critical",
]


class HumanReviewDecision(TypedDict):
    action: HumanReviewAction
    reviewer_id: str
    comment: str
    corrections: dict[str, Any]
    decided_at: str


class HumanReviewRequest(TypedDict):
    review_id: str
    thread_id: str
    requested_by: str
    reason: str
    trigger: str
    risk_level: HumanReviewRiskLevel
    payload: dict[str, Any]
    status: HumanReviewStatus
    created_at: str
    updated_at: str
    resolved_at: str | None
    decision: HumanReviewDecision | None
    error: str
    metadata: dict[str, Any]


class HumanReviewError(ValueError):
    """
    Erro de domínio da máquina de estados de revisão humana.
    """


_ALLOWED_TRANSITIONS: dict[
    HumanReviewStatus,
    set[HumanReviewStatus],
] = {
    "requested": {
        "waiting",
        "approved",
        "corrected",
        "rejected",
        "cancelled",
        "expired",
        "failed",
    },
    "waiting": {
        "approved",
        "corrected",
        "rejected",
        "cancelled",
        "expired",
        "failed",
    },
    "approved": set(),
    "corrected": set(),
    "rejected": set(),
    "cancelled": set(),
    "expired": set(),
    "failed": set(),
}


_TERMINAL_STATUSES: set[
    HumanReviewStatus
] = {
    "approved",
    "corrected",
    "rejected",
    "cancelled",
    "expired",
    "failed",
}


def _utc_now() -> str:
    return datetime.now(
        timezone.utc
    ).isoformat()


def _required_text(
    value: Any,
    *,
    field_name: str,
) -> str:
    normalized = str(
        value or ""
    ).strip()

    if not normalized:
        raise HumanReviewError(
            f"{field_name} não pode ser vazio."
        )

    return normalized


def _optional_text(
    value: Any,
) -> str:
    return str(
        value or ""
    ).strip()


def _validate_status(
    status: Any,
) -> HumanReviewStatus:
    normalized = _required_text(
        status,
        field_name="status",
    )

    if normalized not in (
        _ALLOWED_TRANSITIONS
    ):
        raise HumanReviewError(
            "Status de revisão humana inválido: "
            f"{normalized!r}."
        )

    return normalized  # type: ignore[return-value]


def _validate_risk_level(
    risk_level: Any,
) -> HumanReviewRiskLevel:
    normalized = _required_text(
        risk_level,
        field_name="risk_level",
    ).lower()

    allowed = {
        "low",
        "medium",
        "high",
        "critical",
    }

    if normalized not in allowed:
        raise HumanReviewError(
            "Nível de risco inválido: "
            f"{normalized!r}."
        )

    return normalized  # type: ignore[return-value]


def is_terminal_human_review_status(
    status: Any,
) -> bool:
    return (
        _validate_status(status)
        in _TERMINAL_STATUSES
    )


def create_human_review_request(
    *,
    thread_id: str,
    requested_by: str,
    reason: str,
    trigger: str,
    risk_level: HumanReviewRiskLevel,
    payload: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
    review_id: str | None = None,
    timestamp: str | None = None,
) -> HumanReviewRequest:
    created_at = (
        _required_text(
            timestamp,
            field_name="timestamp",
        )
        if timestamp is not None
        else _utc_now()
    )

    normalized_review_id = (
        _required_text(
            review_id,
            field_name="review_id",
        )
        if review_id is not None
        else str(uuid4())
    )

    return {
        "review_id": normalized_review_id,
        "thread_id": _required_text(
            thread_id,
            field_name="thread_id",
        ),
        "requested_by": _required_text(
            requested_by,
            field_name="requested_by",
        ),
        "reason": _required_text(
            reason,
            field_name="reason",
        ),
        "trigger": _required_text(
            trigger,
            field_name="trigger",
        ),
        "risk_level": _validate_risk_level(
            risk_level
        ),
        "payload": deepcopy(
            payload or {}
        ),
        "status": "requested",
        "created_at": created_at,
        "updated_at": created_at,
        "resolved_at": None,
        "decision": None,
        "error": "",
        "metadata": deepcopy(
            metadata or {}
        ),
    }


def transition_human_review(
    review: HumanReviewRequest,
    *,
    status: HumanReviewStatus,
    decision: HumanReviewDecision | None = None,
    error: str = "",
    timestamp: str | None = None,
) -> HumanReviewRequest:
    current_status = _validate_status(
        review.get("status")
    )

    target_status = _validate_status(
        status
    )

    allowed = _ALLOWED_TRANSITIONS[
        current_status
    ]

    if target_status not in allowed:
        raise HumanReviewError(
            "Transição de revisão humana inválida: "
            f"{current_status} -> {target_status}."
        )

    updated_at = (
        _required_text(
            timestamp,
            field_name="timestamp",
        )
        if timestamp is not None
        else _utc_now()
    )

    updated: HumanReviewRequest = {
        **deepcopy(review),
        "status": target_status,
        "updated_at": updated_at,
        "error": _optional_text(error),
    }

    if decision is not None:
        updated["decision"] = deepcopy(
            decision
        )

    if target_status in _TERMINAL_STATUSES:
        updated["resolved_at"] = updated_at

    return updated


def mark_human_review_waiting(
    review: HumanReviewRequest,
    *,
    timestamp: str | None = None,
) -> HumanReviewRequest:
    return transition_human_review(
        review,
        status="waiting",
        timestamp=timestamp,
    )


def _create_decision(
    *,
    action: HumanReviewAction,
    reviewer_id: str,
    comment: str = "",
    corrections: dict[str, Any] | None = None,
    timestamp: str | None = None,
) -> HumanReviewDecision:
    decided_at = (
        _required_text(
            timestamp,
            field_name="timestamp",
        )
        if timestamp is not None
        else _utc_now()
    )

    return {
        "action": action,
        "reviewer_id": _required_text(
            reviewer_id,
            field_name="reviewer_id",
        ),
        "comment": _optional_text(
            comment
        ),
        "corrections": deepcopy(
            corrections or {}
        ),
        "decided_at": decided_at,
    }


def approve_human_review(
    review: HumanReviewRequest,
    *,
    reviewer_id: str,
    comment: str = "",
    timestamp: str | None = None,
) -> HumanReviewRequest:
    decision = _create_decision(
        action="approve",
        reviewer_id=reviewer_id,
        comment=comment,
        timestamp=timestamp,
    )

    return transition_human_review(
        review,
        status="approved",
        decision=decision,
        timestamp=decision["decided_at"],
    )


def correct_human_review(
    review: HumanReviewRequest,
    *,
    reviewer_id: str,
    corrections: dict[str, Any],
    comment: str = "",
    timestamp: str | None = None,
) -> HumanReviewRequest:
    if not isinstance(
        corrections,
        dict,
    ) or not corrections:
        raise HumanReviewError(
            "corrections deve conter pelo menos "
            "uma correção."
        )

    decision = _create_decision(
        action="correct",
        reviewer_id=reviewer_id,
        comment=comment,
        corrections=corrections,
        timestamp=timestamp,
    )

    return transition_human_review(
        review,
        status="corrected",
        decision=decision,
        timestamp=decision["decided_at"],
    )


def reject_human_review(
    review: HumanReviewRequest,
    *,
    reviewer_id: str,
    reason: str,
    timestamp: str | None = None,
) -> HumanReviewRequest:
    normalized_reason = _required_text(
        reason,
        field_name="reason",
    )

    decision = _create_decision(
        action="reject",
        reviewer_id=reviewer_id,
        comment=normalized_reason,
        timestamp=timestamp,
    )

    return transition_human_review(
        review,
        status="rejected",
        decision=decision,
        error=normalized_reason,
        timestamp=decision["decided_at"],
    )


def cancel_human_review(
    review: HumanReviewRequest,
    *,
    reviewer_id: str,
    reason: str = "",
    timestamp: str | None = None,
) -> HumanReviewRequest:
    decision = _create_decision(
        action="cancel",
        reviewer_id=reviewer_id,
        comment=reason,
        timestamp=timestamp,
    )

    return transition_human_review(
        review,
        status="cancelled",
        decision=decision,
        error=reason,
        timestamp=decision["decided_at"],
    )


def expire_human_review(
    review: HumanReviewRequest,
    *,
    reason: str = "Prazo da revisão expirado.",
    timestamp: str | None = None,
) -> HumanReviewRequest:
    return transition_human_review(
        review,
        status="expired",
        error=_required_text(
            reason,
            field_name="reason",
        ),
        timestamp=timestamp,
    )


def fail_human_review(
    review: HumanReviewRequest,
    *,
    error: str,
    timestamp: str | None = None,
) -> HumanReviewRequest:
    return transition_human_review(
        review,
        status="failed",
        error=_required_text(
            error,
            field_name="error",
        ),
        timestamp=timestamp,
    )


__all__ = [
    "HumanReviewAction",
    "HumanReviewDecision",
    "HumanReviewError",
    "HumanReviewRequest",
    "HumanReviewRiskLevel",
    "HumanReviewStatus",
    "approve_human_review",
    "cancel_human_review",
    "correct_human_review",
    "create_human_review_request",
    "expire_human_review",
    "fail_human_review",
    "is_terminal_human_review_status",
    "mark_human_review_waiting",
    "reject_human_review",
    "transition_human_review",
]