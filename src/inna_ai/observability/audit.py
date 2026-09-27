"""Auditoria técnica segura do portfólio público."""

from __future__ import annotations

import logging
from typing import Any


logger = logging.getLogger(
    "inna_ai.audit"
)


def record_event(
    canal: str,
    usuario: str | None = None,
    idioma: str | None = None,
    moeda: str | None = None,
    status: str = "success",
    diagnostico_id: int | None = None,
    pergunta: str | None = None,
    resposta: str | None = None,
    metadata: dict[str, Any] | None = None,
    usuario_id: str | None = None,
    tempo_resposta_segundos: float = 0,
) -> None:
    """
    Registra somente metadados técnicos seguros.

    Conteúdo de pergunta, resposta, usuário e identificadores
    pessoais não é exportado pelo adapter público.
    """
    safe_metadata_keys = sorted(
        str(key)
        for key
        in (metadata or {}).keys()
    )

    logger.info(
        "channel=%s status=%s language=%s currency=%s "
        "duration_seconds=%s metadata_keys=%s",
        str(canal),
        str(status),
        str(idioma or ""),
        str(moeda or ""),
        float(
            tempo_resposta_segundos
            or 0
        ),
        safe_metadata_keys,
    )


__all__ = [
    "record_event",
]
