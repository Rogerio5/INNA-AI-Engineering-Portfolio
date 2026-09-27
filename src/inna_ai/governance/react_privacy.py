"""
Política de privacidade do ReAct governado da INNA.

Princípios:
- nunca persistir senhas, tokens, secrets ou credenciais;
- nunca persistir valores financeiros/pagamentos brutos;
- minimizar dados pessoais;
- mascarar identificadores pessoais;
- reduzir outputs sensíveis a metadados seguros;
- nunca registrar chain-of-thought;
- nunca expor argumentos brutos das ferramentas.

Inspirado no modelo de autonomia controlada:
LLM interpreta, regras controlam e HITL assume casos sensíveis.
"""

from __future__ import annotations

import re
from copy import deepcopy
from typing import Any


SENSITIVE_KEYS = {
    "password",
    "senha",
    "passwd",
    "token",
    "access_token",
    "refresh_token",
    "api_key",
    "apikey",
    "secret",
    "client_secret",
    "authorization",
    "credential",
    "credentials",
    "cookie",
    "session",
    "session_id",

    "email",
    "e_mail",
    "phone",
    "telefone",
    "celular",

    "cpf",
    "cnpj",
    "document",
    "documento",
    "rg",

    "card_number",
    "numero_cartao",
    "credit_card",
    "cartao",
    "cvv",
    "cvc",
    "pin",

    "account_number",
    "numero_conta",
    "bank_account",
    "agency",
    "agencia",

    "pix",
    "pix_key",
    "chave_pix",
}


FINANCIAL_VALUE_KEYS = {
    "amount",
    "value",
    "valor",
    "payment",
    "pagamento",
    "payment_value",
    "valor_pagamento",
    "price",
    "preco",
    "cost",
    "custo",
    "balance",
    "saldo",
    "income",
    "renda",
    "salary",
    "salario",
    "expense",
    "despesa",
    "total",
    "subtotal",
}


EMAIL_PATTERN = re.compile(
    r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"
)

TOKEN_PATTERN = re.compile(
    r"\b(?:"
    r"sk-[A-Za-z0-9_-]{10,}"
    r"|gh[pousr]_[A-Za-z0-9_]{10,}"
    r"|Bearer\s+[A-Za-z0-9._~+/=-]{10,}"
    r"|AIza[A-Za-z0-9_-]{20,}"
    r")\b",
    flags=re.IGNORECASE,
)

CPF_PATTERN = re.compile(
    r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b"
)

CNPJ_PATTERN = re.compile(
    r"\b\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}\b"
)

CARD_PATTERN = re.compile(
    r"\b(?:\d[ -]*?){13,19}\b"
)


MONEY_PATTERN = re.compile(
    r"(?<!\w)"
    r"(?:R\$|US\$|\$|€|£)"
    r"\s*"
    r"\d+(?:[.,]\d{2})?"
    r"(?!\w)",
    flags=re.IGNORECASE,
)


def _normalize_key(value: Any) -> str:
    return str(value).strip().lower()


def _mask_text(value: str) -> str:
    text = str(value)

    text = EMAIL_PATTERN.sub(
        "[REDACTED_EMAIL]",
        text,
    )

    text = TOKEN_PATTERN.sub(
        "[REDACTED_SECRET]",
        text,
    )

    text = CPF_PATTERN.sub(
        "[REDACTED_DOCUMENT]",
        text,
    )

    text = CNPJ_PATTERN.sub(
        "[REDACTED_DOCUMENT]",
        text,
    )

    text = CARD_PATTERN.sub(
        "[REDACTED_CARD]",
        text,
    )

    text = MONEY_PATTERN.sub(
        "[REDACTED_FINANCIAL_TEXT]",
        text,
    )

    return text


def sanitize_react_value(
    value: Any,
) -> Any:
    """
    Sanitização recursiva genérica.

    Não preserva segredos nem valores financeiros brutos.
    """

    if value is None:
        return None

    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}

        for key, raw_value in value.items():
            normalized = _normalize_key(key)

            if normalized in SENSITIVE_KEYS:
                sanitized[str(key)] = "[REDACTED]"
                continue

            if normalized in FINANCIAL_VALUE_KEYS:
                sanitized[str(key)] = "[REDACTED_FINANCIAL]"
                continue

            sanitized[str(key)] = sanitize_react_value(
                raw_value
            )

        return sanitized

    if isinstance(value, list):
        return [
            sanitize_react_value(item)
            for item in value
        ]

    if isinstance(value, tuple):
        return [
            sanitize_react_value(item)
            for item in value
        ]

    if isinstance(value, str):
        return _mask_text(value)

    if isinstance(
        value,
        (
            int,
            float,
            bool,
        ),
    ):
        return value

    return _mask_text(
        str(value)
    )


def safe_tool_observation(
    *,
    output: dict[str, Any] | None,
    sensitive_output: bool,
) -> dict[str, Any]:
    """
    Gera observação segura para persistência.

    Ferramentas marcadas como sensitive_output nunca
    persistem o conteúdo bruto.
    """

    raw = deepcopy(
        output or {}
    )

    if sensitive_output:
        return {
            "content_redacted": True,
            "sensitive_output": True,
            "status": "available_but_not_persisted",
        }

    sanitized = sanitize_react_value(
        raw
    )

    if not isinstance(
        sanitized,
        dict,
    ):
        return {
            "content_redacted": True,
        }

    sanitized["content_redacted"] = False
    sanitized["sensitive_output"] = False

    return sanitized


def safe_error_record(
    exc: Exception,
) -> dict[str, str]:
    """
    Nunca persiste mensagem bruta da exceção.
    """

    return {
        "error_code": (
            "react_governance_error"
        ),
        "error_type": type(exc).__name__,
    }


__all__ = [
    "FINANCIAL_VALUE_KEYS",
    "SENSITIVE_KEYS",
    "safe_error_record",
    "safe_tool_observation",
    "sanitize_react_value",
]

