from __future__ import annotations

from copy import deepcopy
from typing import Any

from inna_ai.governance.hitl.lifecycle import create_human_review_request
from inna_ai.governance.hitl.policy import HumanReviewPolicyDecision, evaluate_human_review_policy
from inna_ai.orchestration.state import InnaAgentState

DEFAULT_MAX_HUMAN_REVIEWS = 3


def _normalize_text(
    value: Any,
) -> str:
    return str(
        value or ""
    ).strip()


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
    ):
        return {}

    return deepcopy(
        current
    )


def _review_count(
    state: InnaAgentState,
) -> int:
    try:
        return max(
            0,
            int(
                state.get(
                    "human_review_count",
                    0,
                )
                or 0
            ),
        )
    except (
        TypeError,
        ValueError,
    ):
        return 0


def _max_reviews(
    state: InnaAgentState,
) -> int:
    try:
        value = int(
            state.get(
                "max_human_reviews",
                DEFAULT_MAX_HUMAN_REVIEWS,
            )
            or DEFAULT_MAX_HUMAN_REVIEWS
        )
    except (
        TypeError,
        ValueError,
    ):
        value = (
            DEFAULT_MAX_HUMAN_REVIEWS
        )

    return max(
        1,
        value,
    )


def _structured_response(
    state: InnaAgentState,
    *,
    decision: HumanReviewPolicyDecision,
    review: dict[str, Any] | None = None,
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
        "human_review_policy_decision"
    ] = decision.as_dict()

    if review:
        updated[
            "human_review_request"
        ] = deepcopy(
            review
        )

    return updated


def human_review_policy_node(
    state: InnaAgentState,
) -> dict[str, Any]:
    """
    Avalia a política e cria uma solicitação de
    revisão humana quando necessário.

    Este nó é determinístico e não interrompe o
    LangGraph. A interrupção será responsabilidade
    de um nó posterior.
    """
    decision = (
        evaluate_human_review_policy(
            state
        )
    )

    decision_dict = (
        decision.as_dict()
    )

    current_review = _current_review(
        state
    )

    current_status = _normalize_text(
        current_review.get(
            "status"
        )
    )

    if current_status in {
        "requested",
        "waiting",
    }:
        return {
            "human_review_required": True,
            "human_review_current": (
                current_review
            ),
            "human_review_status": (
                current_status
            ),
            "human_review_policy_decision": (
                decision_dict
            ),
            "structured_response": (
                _structured_response(
                    state,
                    decision=decision,
                    review=current_review,
                )
            ),
            "trace": _append_trace(
                state,
                (
                    "human_review_policy:"
                    "already_pending:"
                    f"{current_status}"
                ),
            ),
        }

    if not decision.requires_review:
        return {
            "human_review_required": False,
            "human_review_policy_decision": (
                decision_dict
            ),
            "human_review_status": (
                current_status
            ),
            "structured_response": (
                _structured_response(
                    state,
                    decision=decision,
                )
            ),
            "trace": _append_trace(
                state,
                (
                    "human_review_policy:"
                    f"{decision.trigger}:"
                    "not_required"
                ),
            ),
        }

    count = _review_count(
        state
    )

    maximum = _max_reviews(
        state
    )

    if count >= maximum:
        return {
            "human_review_required": False,
            "human_review_limit_exceeded": True,
            "human_review_policy_decision": (
                decision_dict
            ),
            "human_review_status": "failed",
            "structured_response": (
                _structured_response(
                    state,
                    decision=decision,
                )
            ),
            "trace": _append_trace(
                state,
                (
                    "human_review_policy:"
                    "limit_exceeded:"
                    f"{count}/{maximum}"
                ),
            ),
        }

    thread_id = _normalize_text(
        state.get(
            "thread_id"
        )
    )

    if not thread_id:
        raise ValueError(
            "thread_id é obrigatório para criar "
            "uma revisão humana."
        )

    review = create_human_review_request(
        thread_id=thread_id,
        requested_by=(
            decision.requested_by
        ),
        reason=decision.reason,
        trigger=decision.trigger,
        risk_level=(
            decision.risk_level
        ),
        payload=decision.payload,
        metadata={
            **decision.metadata,
            "review_number": count + 1,
            "max_human_reviews": maximum,
        },
    )

    history = _review_history(
        state
    )

    history.append(
        deepcopy(
            review
        )
    )

    return {
        "human_review_required": True,
        "human_review_current": review,
        "human_review_history": history,
        "human_review_policy_decision": (
            decision_dict
        ),
        "human_review_status": "requested",
        "human_review_count": count + 1,
        "human_review_limit_exceeded": False,
        "structured_response": (
            _structured_response(
                state,
                decision=decision,
                review=review,
            )
        ),
        "trace": _append_trace(
            state,
            (
                "human_review_policy:"
                f"requested:{review['review_id']}:"
                f"{decision.trigger}"
            ),
        ),
    }


def select_route_after_human_review_policy(
    state: InnaAgentState,
) -> str:
    """
    Seleciona a próxima rota sem executar interrupt.

    A rota human_review_interrupt será conectada
    em etapa posterior.
    """
    review_required = bool(
        state.get(
            "human_review_required",
            False,
        )
    )

    limit_exceeded = bool(
        state.get(
            "human_review_limit_exceeded",
            False,
        )
    )

    review_status = _normalize_text(
        state.get(
            "human_review_status"
        )
    ).lower()

    policy_decision = state.get(
        "human_review_policy_decision",
        {},
    )

    policy_requires_review = False

    if isinstance(
        policy_decision,
        dict,
    ):
        policy_requires_review = bool(
            policy_decision.get(
                "requires_review",
                False,
            )
        )

    # Fail closed:
    # uma revisão exigida que não pôde ser criada
    # jamais continua silenciosamente para handoff.
    if (
        limit_exceeded
        or review_status == "failed"
        or (
            policy_requires_review
            and not review_required
        )
    ):
        return "conversation_summary"

    if review_required:
        return "human_review_interrupt"

    return "handoff_coordinator"


__all__ = [
    "DEFAULT_MAX_HUMAN_REVIEWS",
    "human_review_policy_node",
    "select_route_after_human_review_policy",
]
