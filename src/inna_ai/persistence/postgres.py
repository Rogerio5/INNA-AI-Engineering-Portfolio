"""Adapter PostgreSQL mínimo do portfólio."""

from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Any, Iterator


class DatabaseConfigurationError(
    RuntimeError
):
    """Configuração PostgreSQL inválida."""


class DatabaseConnectionError(
    RuntimeError
):
    """Falha de conexão PostgreSQL."""


def _database_url() -> str:
    value = str(
        os.getenv(
            "DATABASE_URL",
            "",
        )
    ).strip()

    if not value:
        raise DatabaseConfigurationError(
            "DATABASE_URL não configurada."
        )

    return value


@contextmanager
def cursor_postgres(
    *,
    dict_cursor: bool = False,
    commit_automatico: bool = True,
) -> Iterator[Any]:
    """
    Entrega cursor PostgreSQL e garante fechamento,
    commit ou rollback.
    """
    try:
        import psycopg2
    except ImportError as exc:
        raise DatabaseConfigurationError(
            "psycopg2 não instalado."
        ) from exc

    cursor_factory = None

    if dict_cursor:
        from psycopg2.extras import (
            RealDictCursor,
        )

        cursor_factory = (
            RealDictCursor
        )

    try:
        connection = psycopg2.connect(
            _database_url(),
            connect_timeout=8,
            application_name=(
                "inna-ai-engineering-portfolio"
            ),
        )
    except Exception as exc:
        raise DatabaseConnectionError(
            "Não foi possível conectar "
            "ao PostgreSQL."
        ) from exc

    cursor = connection.cursor(
        cursor_factory=cursor_factory
    )

    try:
        yield cursor

        if commit_automatico:
            connection.commit()

    except Exception:
        connection.rollback()
        raise

    finally:
        cursor.close()
        connection.close()


__all__ = [
    "DatabaseConfigurationError",
    "DatabaseConnectionError",
    "cursor_postgres",
]
