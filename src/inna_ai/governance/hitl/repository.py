from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal

from inna_ai.persistence.postgres import cursor_postgres

from inna_ai.governance.hitl.contracts import HumanReviewPendingRecord, HumanReviewRecord, HumanReviewResolutionCommand

from inna_ai.governance.hitl.exceptions import HumanReviewConflictError, HumanReviewNotFoundError, HumanReviewRepositoryError


FINAL_STATUSES = frozenset({
    "approved",
    "corrected",
    "rejected",
    "cancelled",
})


SQL_INSERT_PENDING = """
INSERT INTO public.human_reviews (
    review_id,
    thread_id,
    status,
    requested_by,
    reason,
    trigger,
    risk_level,
    payload,
    allowed_actions,
    created_at,
    updated_at
)
VALUES (
    %(review_id)s,
    %(thread_id)s,
    'pending',
    %(requested_by)s,
    %(reason)s,
    %(trigger)s,
    %(risk_level)s,
    %(payload)s::jsonb,
    %(allowed_actions)s::jsonb,
    COALESCE(
        %(created_at)s,
        NOW()
    ),
    NOW()
)
ON CONFLICT (review_id)
DO NOTHING
RETURNING *;
"""


SQL_SELECT_BY_REVIEW_ID = """
SELECT *
FROM public.human_reviews
WHERE review_id = %(review_id)s
LIMIT 1;
"""


SQL_LIST_PENDING = """
SELECT *
FROM public.human_reviews
WHERE status IN (
    'pending',
    'resume_failed'
)
ORDER BY
    created_at ASC,
    id ASC
LIMIT %(limit)s
OFFSET %(offset)s;
"""


SQL_CLAIM_REVIEW = """
UPDATE public.human_reviews
SET
    status = 'processing',
    reviewer_id = %(reviewer_id)s,
    processing_request_id =
        %(processing_request_id)s,
    processing_started_at = NOW(),
    failure_reason = '',
    updated_at = NOW()
WHERE
    review_id = %(review_id)s
    AND thread_id = %(thread_id)s
    AND status IN (
        'pending',
        'resume_failed'
    )
RETURNING *;
"""


SQL_FINALIZE_REVIEW = """
UPDATE public.human_reviews
SET
    status = %(status)s,
    decision_action = %(decision_action)s,
    reviewer_id = %(reviewer_id)s,
    reviewer_comment = %(reviewer_comment)s,
    rejection_reason = %(rejection_reason)s,
    corrections = %(corrections)s::jsonb,
    resume_route = %(resume_route)s,
    processing_request_id = '',
    processing_started_at = NULL,
    failure_reason = '',
    resolved_at = NOW(),
    updated_at = NOW()
WHERE
    review_id = %(review_id)s
    AND thread_id = %(thread_id)s
    AND status = 'processing'
    AND processing_request_id =
        %(processing_request_id)s
RETURNING *;
"""


SQL_MARK_RESUME_FAILURE = """
UPDATE public.human_reviews
SET
    status = 'resume_failed',
    failure_reason = %(failure_reason)s,
    processing_request_id = '',
    processing_started_at = NULL,
    updated_at = NOW()
WHERE
    review_id = %(review_id)s
    AND thread_id = %(thread_id)s
    AND status = 'processing'
    AND processing_request_id =
        %(processing_request_id)s
RETURNING *;
"""


SQL_RELEASE_STALE_CLAIMS = """
UPDATE public.human_reviews
SET
    status = 'resume_failed',
    failure_reason = (
        'Claim expirado antes da conclusão '
        'da retomada.'
    ),
    processing_request_id = '',
    processing_started_at = NULL,
    updated_at = NOW()
WHERE
    status = 'processing'
    AND processing_started_at <
        NOW() - (
            %(timeout_seconds)s
            * INTERVAL '1 second'
        )
RETURNING review_id;
"""


@dataclass(
    frozen=True,
    slots=True,
)
class HumanReviewWriteResult:
    record: HumanReviewRecord
    status: Literal[
        "created",
        "existing",
    ]

    @property
    def created(
        self,
    ) -> bool:
        return self.status == "created"

    def to_dict(
        self,
    ) -> dict[str, Any]:
        return {
            "status": self.status,
            "created": self.created,
            "review": self.record.model_dump(
                mode="json",
            ),
        }


def _json_dumps(
    value: object,
) -> str:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(
                ",",
                ":",
            ),
            allow_nan=False,
        )

    except (
        TypeError,
        ValueError,
    ) as exc:
        raise HumanReviewRepositoryError(
            "Não foi possível serializar os dados "
            "da revisão humana."
        ) from exc


def _mapping_to_dict(
    value: object,
) -> dict[str, Any]:
    if value is None:
        return {}

    if isinstance(
        value,
        Mapping,
    ):
        return dict(value)

    raise HumanReviewRepositoryError(
        "O banco retornou um objeto JSON inválido."
    )


def _record_from_row(
    row: Mapping[str, Any],
) -> HumanReviewRecord:
    if not isinstance(
        row,
        Mapping,
    ):
        raise HumanReviewRepositoryError(
            "O banco retornou uma revisão humana "
            "em formato inválido."
        )

    try:
        normalized = dict(row)

        normalized["payload"] = (
            _mapping_to_dict(
                normalized.get(
                    "payload"
                )
            )
        )

        normalized["corrections"] = (
            _mapping_to_dict(
                normalized.get(
                    "corrections"
                )
            )
        )

        return HumanReviewRecord(
            **normalized
        )

    except HumanReviewRepositoryError:
        raise

    except Exception as exc:
        raise HumanReviewRepositoryError(
            "O banco retornou uma revisão humana "
            "em formato inválido."
        ) from exc


def _pending_parameters(
    record: HumanReviewPendingRecord,
) -> dict[str, Any]:
    return {
        "review_id": record.review_id,
        "thread_id": record.thread_id,
        "requested_by": record.requested_by,
        "reason": record.reason,
        "trigger": record.trigger,
        "risk_level": record.risk_level,
        "payload": _json_dumps(
            record.payload
        ),
        "allowed_actions": _json_dumps(
            record.allowed_actions
        ),
        "created_at": record.created_at,
    }


def obter_revisao(
    review_id: str,
) -> HumanReviewRecord | None:
    normalized_review_id = str(
        review_id or ""
    ).strip()

    if not normalized_review_id:
        raise ValueError(
            "review_id é obrigatório."
        )

    if len(normalized_review_id) > 255:
        raise ValueError(
            "review_id deve possuir no máximo "
            "255 caracteres."
        )

    try:
        with cursor_postgres(
            dict_cursor=True,
            commit_automatico=False,
        ) as cursor:
            cursor.execute(
                SQL_SELECT_BY_REVIEW_ID,
                {
                    "review_id": (
                        normalized_review_id
                    ),
                },
            )

            row = cursor.fetchone()

    except Exception as exc:
        raise HumanReviewRepositoryError(
            "Não foi possível consultar a revisão "
            "humana."
        ) from exc

    if row is None:
        return None

    return _record_from_row(
        row
    )


def criar_revisao_pendente(
    record: HumanReviewPendingRecord,
) -> HumanReviewWriteResult:
    if not isinstance(
        record,
        HumanReviewPendingRecord,
    ):
        raise TypeError(
            "record deve ser uma instância de "
            "HumanReviewPendingRecord."
        )

    parameters = _pending_parameters(
        record
    )

    try:
        with cursor_postgres(
            dict_cursor=True,
            commit_automatico=True,
        ) as cursor:
            cursor.execute(
                "SET LOCAL lock_timeout "
                "= '3000ms';"
            )

            cursor.execute(
                "SET LOCAL statement_timeout "
                "= '5000ms';"
            )

            cursor.execute(
                SQL_INSERT_PENDING,
                parameters,
            )

            inserted = cursor.fetchone()

            if inserted is not None:
                return HumanReviewWriteResult(
                    record=_record_from_row(
                        inserted
                    ),
                    status="created",
                )

            cursor.execute(
                SQL_SELECT_BY_REVIEW_ID,
                {
                    "review_id": (
                        record.review_id
                    ),
                },
            )

            existing = cursor.fetchone()

            if existing is None:
                raise HumanReviewRepositoryError(
                    "A revisão não foi encontrada "
                    "após o conflito de criação."
                )

            existing_record = (
                _record_from_row(
                    existing
                )
            )

            if (
                existing_record.thread_id
                != record.thread_id
            ):
                raise HumanReviewConflictError(
                    "review_id já está associado "
                    "a outro thread_id."
                )

            return HumanReviewWriteResult(
                record=existing_record,
                status="existing",
            )

    except (
        HumanReviewConflictError,
        HumanReviewRepositoryError,
    ):
        raise

    except Exception as exc:
        raise HumanReviewRepositoryError(
            "Não foi possível criar a revisão "
            "humana pendente."
        ) from exc


def listar_revisoes_pendentes(
    *,
    limit: int = 50,
    offset: int = 0,
) -> list[HumanReviewRecord]:
    if not isinstance(
        limit,
        int,
    ):
        raise TypeError(
            "limit deve ser inteiro."
        )

    if not isinstance(
        offset,
        int,
    ):
        raise TypeError(
            "offset deve ser inteiro."
        )

    if not 1 <= limit <= 200:
        raise ValueError(
            "limit deve estar entre 1 e 200."
        )

    if offset < 0:
        raise ValueError(
            "offset não pode ser negativo."
        )

    try:
        with cursor_postgres(
            dict_cursor=True,
            commit_automatico=False,
        ) as cursor:
            cursor.execute(
                SQL_LIST_PENDING,
                {
                    "limit": limit,
                    "offset": offset,
                },
            )

            rows = cursor.fetchall()

    except Exception as exc:
        raise HumanReviewRepositoryError(
            "Não foi possível listar as revisões "
            "humanas pendentes."
        ) from exc

    return [
        _record_from_row(row)
        for row in rows
    ]


def reivindicar_revisao(
    command: HumanReviewResolutionCommand,
) -> HumanReviewRecord:
    if not isinstance(
        command,
        HumanReviewResolutionCommand,
    ):
        raise TypeError(
            "command deve ser uma instância de "
            "HumanReviewResolutionCommand."
        )

    parameters = {
        "review_id": command.review_id,
        "thread_id": command.thread_id,
        "reviewer_id": (
            command.context.reviewer_id
        ),
        "processing_request_id": (
            command.context.request_id
        ),
    }

    try:
        with cursor_postgres(
            dict_cursor=True,
            commit_automatico=True,
        ) as cursor:
            cursor.execute(
                "SET LOCAL lock_timeout "
                "= '3000ms';"
            )

            cursor.execute(
                "SET LOCAL statement_timeout "
                "= '5000ms';"
            )

            cursor.execute(
                SQL_CLAIM_REVIEW,
                parameters,
            )

            row = cursor.fetchone()

            if row is not None:
                return _record_from_row(
                    row
                )

            cursor.execute(
                SQL_SELECT_BY_REVIEW_ID,
                {
                    "review_id": (
                        command.review_id
                    ),
                },
            )

            existing = cursor.fetchone()

    except Exception as exc:
        raise HumanReviewRepositoryError(
            "Não foi possível reivindicar a revisão "
            "humana."
        ) from exc

    if existing is None:
        raise HumanReviewNotFoundError(
            "A revisão humana não foi encontrada."
        )

    existing_record = _record_from_row(
        existing
    )

    if (
        existing_record.thread_id
        != command.thread_id
    ):
        raise HumanReviewConflictError(
            "A revisão não pertence ao thread "
            "informado."
        )

    raise HumanReviewConflictError(
        "A revisão humana já está sendo processada "
        "ou já foi concluída."
    )


def finalizar_revisao(
    command: HumanReviewResolutionCommand,
    *,
    status: str,
    resume_route: str = "",
) -> HumanReviewRecord:
    if not isinstance(
        command,
        HumanReviewResolutionCommand,
    ):
        raise TypeError(
            "command deve ser uma instância de "
            "HumanReviewResolutionCommand."
        )

    normalized_status = str(
        status or ""
    ).strip().lower()

    if normalized_status not in FINAL_STATUSES:
        raise ValueError(
            "Status final de revisão inválido."
        )

    decision = command.decision

    parameters = {
        "review_id": command.review_id,
        "thread_id": command.thread_id,
        "status": normalized_status,
        "decision_action": decision.action,
        "reviewer_id": (
            command.context.reviewer_id
        ),
        "reviewer_comment": decision.comment,
        "rejection_reason": decision.reason,
        "corrections": _json_dumps(
            decision.corrections
        ),
        "resume_route": str(
            resume_route or ""
        ).strip(),
        "processing_request_id": (
            command.context.request_id
        ),
    }

    try:
        with cursor_postgres(
            dict_cursor=True,
            commit_automatico=True,
        ) as cursor:
            cursor.execute(
                SQL_FINALIZE_REVIEW,
                parameters,
            )

            row = cursor.fetchone()

    except Exception as exc:
        raise HumanReviewRepositoryError(
            "Não foi possível finalizar a revisão "
            "humana."
        ) from exc

    if row is None:
        raise HumanReviewConflictError(
            "O claim da revisão não está mais "
            "válido."
        )

    return _record_from_row(
        row
    )


def registrar_falha_retomada(
    command: HumanReviewResolutionCommand,
    *,
    failure_reason: str,
) -> HumanReviewRecord:
    if not isinstance(
        command,
        HumanReviewResolutionCommand,
    ):
        raise TypeError(
            "command deve ser uma instância de "
            "HumanReviewResolutionCommand."
        )

    sanitized_reason = str(
        failure_reason or ""
    ).strip()

    if not sanitized_reason:
        sanitized_reason = (
            "Falha não identificada durante "
            "a retomada."
        )

    sanitized_reason = (
        sanitized_reason[:2_000]
    )

    try:
        with cursor_postgres(
            dict_cursor=True,
            commit_automatico=True,
        ) as cursor:
            cursor.execute(
                SQL_MARK_RESUME_FAILURE,
                {
                    "review_id": (
                        command.review_id
                    ),
                    "thread_id": (
                        command.thread_id
                    ),
                    "processing_request_id": (
                        command
                        .context
                        .request_id
                    ),
                    "failure_reason": (
                        sanitized_reason
                    ),
                },
            )

            row = cursor.fetchone()

    except Exception as exc:
        raise HumanReviewRepositoryError(
            "Não foi possível registrar a falha "
            "de retomada."
        ) from exc

    if row is None:
        raise HumanReviewConflictError(
            "O claim da revisão não está mais "
            "válido."
        )

    return _record_from_row(
        row
    )


def liberar_claims_expirados(
    *,
    timeout_seconds: int = 300,
) -> list[str]:
    if not isinstance(
        timeout_seconds,
        int,
    ):
        raise TypeError(
            "timeout_seconds deve ser inteiro."
        )

    if not 30 <= timeout_seconds <= 86_400:
        raise ValueError(
            "timeout_seconds deve estar entre "
            "30 e 86400."
        )

    try:
        with cursor_postgres(
            dict_cursor=True,
            commit_automatico=True,
        ) as cursor:
            cursor.execute(
                SQL_RELEASE_STALE_CLAIMS,
                {
                    "timeout_seconds": (
                        timeout_seconds
                    ),
                },
            )

            rows = cursor.fetchall()

    except Exception as exc:
        raise HumanReviewRepositoryError(
            "Não foi possível liberar claims "
            "expirados."
        ) from exc

    return [
        str(row["review_id"])
        for row in rows
    ]


__all__ = [
    "FINAL_STATUSES",
    "HumanReviewWriteResult",
    "criar_revisao_pendente",
    "finalizar_revisao",
    "liberar_claims_expirados",
    "listar_revisoes_pendentes",
    "obter_revisao",
    "registrar_falha_retomada",
    "reivindicar_revisao",
]
