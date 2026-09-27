from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)


HumanReviewAction = Literal[
    "approve",
    "correct",
    "reject",
    "cancel",
]

HumanReviewStatus = Literal[
    "pending",
    "processing",
    "approved",
    "corrected",
    "rejected",
    "cancelled",
    "resume_failed",
]


class HumanReviewPendingRecord(
    BaseModel
):
    """
    Revisão humana pendente produzida pelo
    interrupt do LangGraph.
    """

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        validate_assignment=True,
    )

    review_id: str = Field(
        min_length=1,
        max_length=255,
    )

    thread_id: str = Field(
        min_length=1,
        max_length=255,
    )

    status: str = Field(
        default="pending",
        min_length=1,
        max_length=40,
    )

    requested_by: str = Field(
        default="",
        max_length=160,
    )

    reason: str = Field(
        default="",
        max_length=10_000,
    )

    trigger: str = Field(
        default="",
        max_length=160,
    )

    risk_level: str = Field(
        default="",
        max_length=40,
    )

    payload: dict[str, Any] = Field(
        default_factory=dict,
    )

    allowed_actions: list[
        HumanReviewAction
    ] = Field(
        default_factory=lambda: [
            "approve",
            "correct",
            "reject",
            "cancel",
        ],
    )

    created_at: datetime | None = None

    @field_validator(
        "status",
        mode="after",
    )
    @classmethod
    def normalizar_status(
        cls,
        value: str,
    ) -> str:
        return value.strip().lower()


class HumanReviewDecision(
    BaseModel
):
    """
    Decisão enviada por um revisor autenticado.

    O formato é compatível com
    Command(resume=...).
    """

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        validate_assignment=True,
    )

    action: HumanReviewAction

    reviewer_id: str = Field(
        min_length=1,
        max_length=160,
    )

    comment: str = Field(
        default="",
        max_length=10_000,
    )

    reason: str = Field(
        default="",
        max_length=10_000,
    )

    corrections: dict[str, Any] = Field(
        default_factory=dict,
    )

    @model_validator(
        mode="after",
    )
    def validar_campos_da_acao(
        self,
    ) -> "HumanReviewDecision":
        if (
            self.action == "correct"
            and not self.corrections
        ):
            raise ValueError(
                "A ação correct exige pelo menos "
                "uma correção."
            )

        if (
            self.action == "reject"
            and not self.reason
        ):
            raise ValueError(
                "A ação reject exige reason."
            )

        return self

    def to_resume_payload(
        self,
    ) -> dict[str, Any]:
        """
        Retorna exatamente o payload esperado pelo
        Human-in-the-Loop do LangGraph.
        """
        return {
            "action": self.action,
            "reviewer_id": self.reviewer_id,
            "comment": self.comment,
            "reason": self.reason,
            "corrections": dict(
                self.corrections
            ),
        }


class TrustedHumanReviewContext(
    BaseModel
):
    """
    Identidade autenticada da requisição interna.

    O reviewer_id confiável deve vir do contexto
    HMAC da API, e não diretamente do body.
    """

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        validate_assignment=True,
    )

    reviewer_id: str = Field(
        min_length=1,
        max_length=160,
    )

    request_id: str = Field(
        min_length=8,
        max_length=200,
    )


class HumanReviewResolutionCommand(
    BaseModel
):
    """
    Comando validado entregue ao service layer.
    """

    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
    )

    review_id: str = Field(
        min_length=1,
        max_length=255,
    )

    thread_id: str = Field(
        min_length=1,
        max_length=255,
    )

    context: TrustedHumanReviewContext
    decision: HumanReviewDecision

    @model_validator(
        mode="after",
    )
    def alinhar_identidade_confiavel(
        self,
    ) -> "HumanReviewResolutionCommand":
        if (
            self.decision.reviewer_id
            != self.context.reviewer_id
        ):
            raise ValueError(
                "reviewer_id não corresponde à "
                "identidade autenticada."
            )

        return self

    def to_resume_payload(
        self,
    ) -> dict[str, Any]:
        return (
            self.decision
            .to_resume_payload()
        )


class HumanReviewRecord(
    BaseModel
):
    """
    Representação de uma revisão persistida.
    """

    model_config = ConfigDict(
        extra="ignore",
        str_strip_whitespace=True,
    )

    id: int
    review_id: str
    thread_id: str
    status: str

    requested_by: str = ""
    reason: str = ""
    trigger: str = ""
    risk_level: str = ""

    payload: dict[str, Any] = Field(
        default_factory=dict,
    )

    decision_action: str = ""
    reviewer_id: str = ""
    reviewer_comment: str = ""
    rejection_reason: str = ""

    corrections: dict[str, Any] = Field(
        default_factory=dict,
    )

    resume_route: str = ""

    processing_request_id: str = ""
    processing_started_at: datetime | None = None
    failure_reason: str = ""

    created_at: datetime
    updated_at: datetime
    resolved_at: datetime | None = None


__all__ = [
    "HumanReviewAction",
    "HumanReviewDecision",
    "HumanReviewPendingRecord",
    "HumanReviewRecord",
    "HumanReviewResolutionCommand",
    "HumanReviewStatus",
    "TrustedHumanReviewContext",
]
