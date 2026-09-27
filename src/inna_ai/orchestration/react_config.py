"""Configuração operacional do ReAct governado da INNA."""

from __future__ import annotations

import os


REACT_FEATURE_FLAG = "INNA_REACT_ENABLED"


def react_enabled_from_environment() -> bool:
    """
    Feature flag global do ReAct.

    Segurança:
    - padrão OFF;
    - somente valores explicitamente verdadeiros habilitam;
    - não depende de entrada do usuário.
    """

    raw_value = str(
        os.getenv(
            REACT_FEATURE_FLAG,
            "false",
        )
        or "false"
    ).strip().lower()

    return raw_value in {
        "1",
        "true",
        "yes",
        "sim",
        "on",
        "enabled",
    }


__all__ = [
    "REACT_FEATURE_FLAG",
    "react_enabled_from_environment",
]
