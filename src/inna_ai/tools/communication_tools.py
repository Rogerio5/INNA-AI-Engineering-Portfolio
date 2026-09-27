"""Ferramentas públicas de preparação de comunicação.

Nenhuma mensagem é enviada por este módulo.
O portfólio demonstra validação, Tool Calling e HITL
sem integrar canais comerciais reais.
"""

from __future__ import annotations

import re
from typing import Literal
from uuid import uuid4

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
)

from inna_ai.tools.core import (
    ToolDefinition,
    ToolExecutionContext,
)


PREPARE_FINANCIAL_EMAIL_TOOL_NAME = (
    "preparar_email_financeiro"
)

PREPARE_TELEGRAM_MESSAGE_TOOL_NAME = (
    "preparar_mensagem_telegram"
)

MAX_SUBJECT_LENGTH = 180
MAX_MESSAGE_LENGTH = 10_000

_EMAIL_PATTERN = re.compile(
    r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
)

_PENDING_REVIEWS: dict[
    str,
    dict[str, object],
] = {}


class CommunicationPreparationError(
    RuntimeError
):
    """Falha segura de preparação."""


class PrepararEmailFinanceiroInput(
    BaseModel
):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
    )

    destinatario: str = Field(
        min_length=5,
        max_length=320,
    )

    assunto: str = Field(
        min_length=1,
        max_length=MAX_SUBJECT_LENGTH,
    )

    corpo: str = Field(
        min_length=1,
        max_length=MAX_MESSAGE_LENGTH,
    )

    html_corpo: str | None = Field(
        default=None,
        max_length=MAX_MESSAGE_LENGTH,
    )

    idioma: str = Field(
        default="pt",
        min_length=2,
        max_length=12,
    )

    @field_validator(
        "destinatario"
    )
    @classmethod
    def validar_destinatario(
        cls,
        value: str,
    ) -> str:

        normalized = (
            value.strip().lower()
        )

        if not _EMAIL_PATTERN.fullmatch(
            normalized
        ):
            raise ValueError(
                "Endereço de e-mail inválido."
            )

        return normalized


class PrepararMensagemTelegramInput(
    BaseModel
):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
    )

    chat_id: str = Field(
        min_length=1,
        max_length=100,
    )

    mensagem: str = Field(
        min_length=1,
        max_length=4096,
    )

    idioma: str = Field(
        default="pt",
        min_length=2,
        max_length=12,
    )

    @field_validator(
        "chat_id"
    )
    @classmethod
    def validar_chat_id(
        cls,
        value: str,
    ) -> str:

        normalized = value.strip()

        if not re.fullmatch(
            r"-?[0-9]{1,30}",
            normalized,
        ):
            raise ValueError(
                "chat_id do Telegram inválido."
            )

        return normalized


class ComunicacaoPendenteOutput(
    BaseModel
):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    preparation_id: str
    review_id: str

    review_persisted: Literal[
        True
    ]

    channel: Literal[
        "email",
        "telegram",
    ]

    status: Literal[
        "pending_approval"
    ]

    requires_human_approval: Literal[
        True
    ]

    sent: Literal[
        False
    ]

    recipient_masked: str

    content_length: int = Field(
        ge=1
    )

    language: str

    trace_id: str | None = None
    requested_by: str


def _mask_email(
    email: str,
) -> str:

    local, domain = (
        email.split(
            "@",
            1,
        )
    )

    if len(local) <= 2:
        masked = (
            local[0]
            + "*"
        )
    else:
        masked = (
            local[0]
            + (
                "*"
                * min(
                    len(local) - 2,
                    8,
                )
            )
            + local[-1]
        )

    return (
        f"{masked}@{domain}"
    )


def _mask_chat_id(
    chat_id: str,
) -> str:

    prefix = (
        "-"
        if chat_id.startswith("-")
        else ""
    )

    digits = chat_id.lstrip(
        "-"
    )

    if len(digits) <= 4:
        return (
            prefix
            + "*" * len(digits)
        )

    return (
        prefix
        + "*" * (
            len(digits) - 4
        )
        + digits[-4:]
    )


def _register_demo_review(
    *,
    preparation_id: str,
    channel: str,
    recipient_masked: str,
    content_length: int,
    context: ToolExecutionContext,
) -> str:
    """
    Registra somente metadados em memória.

    O conteúdo bruto não é persistido.
    """
    _PENDING_REVIEWS[
        preparation_id
    ] = {
        "channel":
            channel,

        "recipient_masked":
            recipient_masked,

        "content_length":
            content_length,

        "requested_by":
            context.requested_by,

        "trace_id":
            context.trace_id,

        "status":
            "pending_approval",

        "storage":
            "portfolio_in_memory",
    }

    return preparation_id


def executar_preparacao_email_financeiro(
    payload: PrepararEmailFinanceiroInput,
    context: ToolExecutionContext,
) -> ComunicacaoPendenteOutput:

    preparation_id = (
        f"email-{uuid4().hex}"
    )

    masked = _mask_email(
        payload.destinatario
    )

    review_id = (
        _register_demo_review(
            preparation_id=preparation_id,
            channel="email",
            recipient_masked=masked,
            content_length=len(
                payload.corpo
            ),
            context=context,
        )
    )

    return (
        ComunicacaoPendenteOutput(
            preparation_id=preparation_id,
            review_id=review_id,
            review_persisted=True,
            channel="email",
            status="pending_approval",
            requires_human_approval=True,
            sent=False,
            recipient_masked=masked,
            content_length=len(
                payload.corpo
            ),
            language=payload.idioma,
            trace_id=context.trace_id,
            requested_by=(
                context.requested_by
            ),
        )
    )


def executar_preparacao_mensagem_telegram(
    payload: PrepararMensagemTelegramInput,
    context: ToolExecutionContext,
) -> ComunicacaoPendenteOutput:

    preparation_id = (
        f"telegram-{uuid4().hex}"
    )

    masked = _mask_chat_id(
        payload.chat_id
    )

    review_id = (
        _register_demo_review(
            preparation_id=preparation_id,
            channel="telegram",
            recipient_masked=masked,
            content_length=len(
                payload.mensagem
            ),
            context=context,
        )
    )

    return (
        ComunicacaoPendenteOutput(
            preparation_id=preparation_id,
            review_id=review_id,
            review_persisted=True,
            channel="telegram",
            status="pending_approval",
            requires_human_approval=True,
            sent=False,
            recipient_masked=masked,
            content_length=len(
                payload.mensagem
            ),
            language=payload.idioma,
            trace_id=context.trace_id,
            requested_by=(
                context.requested_by
            ),
        )
    )


def criar_definicao_preparar_email_financeiro(
    *,
    timeout_seconds: float = 2.0,
) -> ToolDefinition:

    return ToolDefinition(
        name=(
            PREPARE_FINANCIAL_EMAIL_TOOL_NAME
        ),
        description=(
            "Prepara um e-mail educacional "
            "para revisão humana. "
            "Não realiza envio."
        ),
        input_model=(
            PrepararEmailFinanceiroInput
        ),
        output_model=(
            ComunicacaoPendenteOutput
        ),
        handler=(
            executar_preparacao_email_financeiro
        ),
        allowed_agents=frozenset({
            "communication_agent",
            "report_agent",
        }),
        timeout_seconds=timeout_seconds,
        idempotent=False,
        sensitive_output=True,
        tags=frozenset({
            "portfolio",
            "communication",
            "human_approval",
            "no_direct_send",
        }),
    )


def criar_definicao_preparar_mensagem_telegram(
    *,
    timeout_seconds: float = 2.0,
) -> ToolDefinition:

    return ToolDefinition(
        name=(
            PREPARE_TELEGRAM_MESSAGE_TOOL_NAME
        ),
        description=(
            "Prepara uma mensagem demonstrativa "
            "para revisão humana. "
            "Não realiza envio."
        ),
        input_model=(
            PrepararMensagemTelegramInput
        ),
        output_model=(
            ComunicacaoPendenteOutput
        ),
        handler=(
            executar_preparacao_mensagem_telegram
        ),
        allowed_agents=frozenset({
            "communication_agent",
        }),
        timeout_seconds=timeout_seconds,
        idempotent=False,
        sensitive_output=True,
        tags=frozenset({
            "portfolio",
            "communication",
            "human_approval",
            "no_direct_send",
        }),
    )


__all__ = [
    "CommunicationPreparationError",
    "ComunicacaoPendenteOutput",
    "PREPARE_FINANCIAL_EMAIL_TOOL_NAME",
    "PREPARE_TELEGRAM_MESSAGE_TOOL_NAME",
    "PrepararEmailFinanceiroInput",
    "PrepararMensagemTelegramInput",
    "criar_definicao_preparar_email_financeiro",
    "criar_definicao_preparar_mensagem_telegram",
    "executar_preparacao_email_financeiro",
    "executar_preparacao_mensagem_telegram",
]
