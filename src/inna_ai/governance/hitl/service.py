from __future__ import annotations

from collections.abc import (
    Callable,
    Mapping,
)
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from inna_ai.orchestration.graph import retomar_revisao_humana_persistente

from inna_ai.governance.hitl import repository
from inna_ai.governance.hitl.contracts import HumanReviewDecision, HumanReviewPendingRecord, HumanReviewRecord, HumanReviewResolutionCommand, TrustedHumanReviewContext
from inna_ai.governance.hitl.exceptions import HumanReviewConflictError, HumanReviewNotFoundError, HumanReviewRepositoryError, HumanReviewResumeError, HumanReviewServiceError, HumanReviewValidationError


TERMINAL_STATUSES = frozenset({
    "approved",
    "corrected",
    "rejected",
    "cancelled",
})

ACTION_TO_STATUS = {
    "approve": "approved",
    "correct": "corrected",
    "reject": "rejected",
    "cancel": "cancelled",
}


ResumeFunction = Callable[
    ...,
    Mapping[str, Any],
]


@dataclass(
    frozen=True,
    slots=True,
)
class HumanReviewResolutionOutcome:
    """
    Resultado sanitizado da resolução de uma revisão.
    """

    review: HumanReviewRecord
    graph_status: str
    resume_route: str

    def to_dict(
        self,
    ) -> dict[str, Any]:
        return {
            "review_id": self.review.review_id,
            "thread_id": self.review.thread_id,
            "status": self.review.status,
            "decision_action": (
                self.review.decision_action
            ),
            "reviewer_id": (
                self.review.reviewer_id
            ),
            "resume_route": self.resume_route,
            "resolved_at": (
                self.review.resolved_at.isoformat()
                if self.review.resolved_at
                else None
            ),
        }


def _normalize_mapping(
    value: object,
    *,
    field_name: str,
) -> dict[str, Any]:
    if not isinstance(
        value,
        Mapping,
    ):
        raise HumanReviewValidationError(
            f"{field_name} deve ser um objeto."
        )

    return dict(value)


def _normalize_identifier(
    value: object,
    *,
    field_name: str,
    max_length: int,
) -> str:
    if not isinstance(
        value,
        str,
    ):
        raise HumanReviewValidationError(
            f"{field_name} é inválido."
        )

    normalized = value.strip()

    if not normalized:
        raise HumanReviewValidationError(
            f"{field_name} é obrigatório."
        )

    if len(normalized) > max_length:
        raise HumanReviewValidationError(
            f"{field_name} deve possuir no máximo "
            f"{max_length} caracteres."
        )

    return normalized


def _normalize_pending_status(
    value: object,
) -> str:
    normalized = str(
        value or "pending"
    ).strip().lower()

    aliases = {
        "pending": "pending",
        "requested": "pending",
        "waiting": "pending",
    }

    try:
        return aliases[normalized]
    except KeyError as exc:
        raise HumanReviewValidationError(
            "Status inicial de revisão humana "
            "inválido."
        ) from exc


def registrar_revisao_pendente(
    interrupt_payload: Mapping[str, Any],
) -> repository.HumanReviewWriteResult:
    """
    Persiste o payload produzido pelo interrupt()
    do LangGraph.

    A operação é idempotente por review_id.
    """
    payload = _normalize_mapping(
        interrupt_payload,
        field_name="interrupt_payload",
    )

    payload_type = str(
        payload.get(
            "type",
            "",
        )
    ).strip().lower()

    if payload_type != "human_review":
        raise HumanReviewValidationError(
            "O payload não representa uma revisão "
            "humana."
        )

    allowed_actions = payload.get(
        "allowed_actions",
        [
            "approve",
            "correct",
            "reject",
            "cancel",
        ],
    )

    try:
        record = HumanReviewPendingRecord(
            review_id=payload.get(
                "review_id",
                "",
            ),
            thread_id=payload.get(
                "thread_id",
                "",
            ),
            status=_normalize_pending_status(
                payload.get(
                    "status",
                    "pending",
                )
            ),
            requested_by=payload.get(
                "requested_by",
                "",
            ),
            reason=payload.get(
                "reason",
                "",
            ),
            trigger=payload.get(
                "trigger",
                "",
            ),
            risk_level=payload.get(
                "risk_level",
                "",
            ),
            payload=payload.get(
                "payload",
                {},
            ),
            allowed_actions=allowed_actions,
            created_at=payload.get(
                "created_at",
            ),
        )

    except ValidationError as exc:
        raise HumanReviewValidationError(
            "O payload da revisão humana é "
            "inválido."
        ) from exc

    try:
        return repository.criar_revisao_pendente(
            record
        )

    except (
        HumanReviewConflictError,
        HumanReviewRepositoryError,
    ):
        raise

    except Exception as exc:
        raise HumanReviewServiceError(
            "Não foi possível registrar a revisão "
            "humana."
        ) from exc


def consultar_revisao(
    review_id: str,
) -> HumanReviewRecord:
    normalized_review_id = (
        _normalize_identifier(
            review_id,
            field_name="review_id",
            max_length=255,
        )
    )

    record = repository.obter_revisao(
        normalized_review_id
    )

    if record is None:
        raise HumanReviewNotFoundError(
            "A revisão humana não foi encontrada."
        )

    return record


def listar_revisoes_pendentes(
    *,
    limit: int = 50,
    offset: int = 0,
) -> list[HumanReviewRecord]:
    return (
        repository
        .listar_revisoes_pendentes(
            limit=limit,
            offset=offset,
        )
    )


def _build_resolution_command(
    *,
    review_id: str,
    thread_id: str,
    trusted_reviewer_id: str,
    request_id: str,
    decision_payload: Mapping[str, Any],
) -> HumanReviewResolutionCommand:
    normalized_decision = _normalize_mapping(
        decision_payload,
        field_name="decision_payload",
    )

    body_reviewer_id = str(
        normalized_decision.get(
            "reviewer_id",
            "",
        )
    ).strip()

    normalized_reviewer_id = (
        _normalize_identifier(
            trusted_reviewer_id,
            field_name="trusted_reviewer_id",
            max_length=160,
        )
    )

    if (
        body_reviewer_id
        and body_reviewer_id
        != normalized_reviewer_id
    ):
        raise HumanReviewValidationError(
            "reviewer_id não corresponde à "
            "identidade autenticada."
        )

    try:
        decision = HumanReviewDecision(
            action=normalized_decision.get(
                "action",
            ),
            reviewer_id=(
                normalized_reviewer_id
            ),
            comment=normalized_decision.get(
                "comment",
                "",
            ),
            reason=normalized_decision.get(
                "reason",
                "",
            ),
            corrections=normalized_decision.get(
                "corrections",
                {},
            ),
        )

        context = TrustedHumanReviewContext(
            reviewer_id=(
                normalized_reviewer_id
            ),
            request_id=request_id,
        )

        return HumanReviewResolutionCommand(
            review_id=review_id,
            thread_id=thread_id,
            context=context,
            decision=decision,
        )

    except ValidationError as exc:
        raise HumanReviewValidationError(
            "A decisão de revisão humana é "
            "inválida."
        ) from exc


def _extract_resolution(
    graph_state: Mapping[str, Any],
    *,
    expected_review_id: str,
    expected_thread_id: str,
    expected_action: str,
) -> tuple[str, str]:
    state = _normalize_mapping(
        graph_state,
        field_name="graph_state",
    )

    current_review = _normalize_mapping(
        state.get(
            "human_review_current",
            {},
        ),
        field_name="human_review_current",
    )

    returned_review_id = str(
        current_review.get(
            "review_id",
            "",
        )
    ).strip()

    returned_thread_id = str(
        current_review.get(
            "thread_id",
            "",
        )
    ).strip()

    if (
        returned_review_id
        and returned_review_id
        != expected_review_id
    ):
        raise HumanReviewResumeError(
            "O LangGraph retornou outra revisão."
        )

    if (
        returned_thread_id
        and returned_thread_id
        != expected_thread_id
    ):
        raise HumanReviewResumeError(
            "O LangGraph retornou outro thread."
        )

    status = str(
        current_review.get(
            "status",
        )
        or state.get(
            "human_review_status",
            "",
        )
    ).strip().lower()

    expected_status = ACTION_TO_STATUS[
        expected_action
    ]

    if status != expected_status:
        raise HumanReviewResumeError(
            "O status retornado pelo LangGraph "
            "não corresponde à decisão enviada."
        )

    if status not in TERMINAL_STATUSES:
        raise HumanReviewResumeError(
            "A revisão não chegou a um estado "
            "terminal."
        )

    resume_route = str(
        state.get(
            "human_review_resume_route",
            "",
        )
    ).strip()

    return (
        status,
        resume_route,
    )


def resolver_revisao_humana(
    *,
    review_id: str,
    thread_id: str,
    trusted_reviewer_id: str,
    request_id: str,
    decision_payload: Mapping[str, Any],
    resume_function: ResumeFunction = (
        retomar_revisao_humana_persistente
    ),
) -> HumanReviewResolutionOutcome:
    """
    Resolve uma revisão com claim concorrente.

    A identidade do revisor vem do contexto
    autenticado, e não do corpo da requisição.
    """
    normalized_review_id = (
        _normalize_identifier(
            review_id,
            field_name="review_id",
            max_length=255,
        )
    )

    normalized_thread_id = (
        _normalize_identifier(
            thread_id,
            field_name="thread_id",
            max_length=255,
        )
    )

    normalized_request_id = (
        _normalize_identifier(
            request_id,
            field_name="request_id",
            max_length=200,
        )
    )

    command = _build_resolution_command(
        review_id=normalized_review_id,
        thread_id=normalized_thread_id,
        trusted_reviewer_id=(
            trusted_reviewer_id
        ),
        request_id=normalized_request_id,
        decision_payload=decision_payload,
    )

    repository.reivindicar_revisao(
        command
    )

    try:
        graph_result = resume_function(
            thread_id=command.thread_id,
            decisao=(
                command.to_resume_payload()
            ),
        )

        final_status, resume_route = (
            _extract_resolution(
                graph_result,
                expected_review_id=(
                    command.review_id
                ),
                expected_thread_id=(
                    command.thread_id
                ),
                expected_action=(
                    command.decision.action
                ),
            )
        )

    except Exception as exc:
        sanitized_failure = (
            f"{type(exc).__name__}: "
            "falha durante a retomada do grafo."
        )

        try:
            repository.registrar_falha_retomada(
                command,
                failure_reason=(
                    sanitized_failure
                ),
            )
        except Exception:
            pass

        if isinstance(
            exc,
            HumanReviewResumeError,
        ):
            raise

        raise HumanReviewResumeError(
            "Não foi possível retomar a revisão "
            "humana no LangGraph."
        ) from exc

    finalized = repository.finalizar_revisao(
        command,
        status=final_status,
        resume_route=resume_route,
    )

    return HumanReviewResolutionOutcome(
        review=finalized,
        graph_status=final_status,
        resume_route=resume_route,
    )


def recuperar_claims_expirados(
    *,
    timeout_seconds: int = 300,
) -> list[str]:
    return repository.liberar_claims_expirados(
        timeout_seconds=timeout_seconds
    )


__all__ = [
    "ACTION_TO_STATUS",
    "HumanReviewResolutionOutcome",
    "TERMINAL_STATUSES",
    "consultar_revisao",
    "listar_revisoes_pendentes",
    "recuperar_claims_expirados",
    "registrar_revisao_pendente",
    "resolver_revisao_humana",
]
