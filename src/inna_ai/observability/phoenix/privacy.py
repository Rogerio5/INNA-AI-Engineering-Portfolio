"""Sanitização de atributos enviados para telemetria externa."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from typing import Any

MAX_ATTRIBUTE_LENGTH = 256

_SENSITIVE_KEY_PATTERN = re.compile(
    r"(api[_-]?key|authorization|token|secret|password|senha|"
    r"prompt|response|resposta|pergunta|message|mensagem|"
    r"content|conteudo|conteúdo|email|phone|telefone|cpf|cnpj|"
    r"database[_-]?url|connection[_-]?string)",
    flags=re.IGNORECASE,
)

_ALLOWED_VALUE_TYPES = (
    bool,
    int,
    float,
    str,
)


def is_sensitive_attribute(name: str) -> bool:
    return bool(_SENSITIVE_KEY_PATTERN.search(str(name)))


def hash_identifier(value: object) -> str:
    """Gera identificador irreversível curto para correlação."""

    encoded = str(value).encode("utf-8", errors="replace")

    return hashlib.sha256(encoded).hexdigest()[:16]


def sanitize_attribute_value(value: Any) -> bool | int | float | str:
    if value is None:
        return "null"

    if not isinstance(value, _ALLOWED_VALUE_TYPES):
        return f"<{type(value).__name__}>"

    if isinstance(value, str):
        compact = " ".join(value.split())

        if len(compact) > MAX_ATTRIBUTE_LENGTH:
            return compact[:MAX_ATTRIBUTE_LENGTH] + "…"

        return compact

    return value


def sanitize_attributes(
    attributes: Mapping[str, Any] | None,
) -> dict[str, bool | int | float | str]:
    """
    Remove campos sensíveis e limita valores enviados ao Phoenix.

    Prompts, respostas, mensagens, chaves, tokens, credenciais e URLs
    de banco nunca são exportados.
    """

    sanitized: dict[str, bool | int | float | str] = {}

    for raw_name, value in (attributes or {}).items():
        name = str(raw_name).strip()

        if not name or is_sensitive_attribute(name):
            continue

        sanitized[name] = sanitize_attribute_value(value)

    sanitized["privacy.content_exported"] = False

    return sanitized


__all__ = [
    "MAX_ATTRIBUTE_LENGTH",
    "hash_identifier",
    "is_sensitive_attribute",
    "sanitize_attribute_value",
    "sanitize_attributes",
]
