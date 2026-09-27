"""Autenticação interna do servidor MCP da INNA."""

from __future__ import annotations

import hmac
import os

EXPECTED_TOKEN_ENV = "INNA_INTERNAL_OPERATIONS_TOKEN"
CLIENT_TOKEN_ENV = "INNA_MCP_CLIENT_TOKEN"


class MCPAuthenticationError(PermissionError):
    """Falha segura de autenticação MCP."""


def validar_autenticacao_interna() -> None:
    """Valida o cliente MCP usando comparação constante."""

    expected_token = os.getenv(
        EXPECTED_TOKEN_ENV,
        "",
    ).strip()

    client_token = os.getenv(
        CLIENT_TOKEN_ENV,
        "",
    ).strip()

    if not expected_token:
        raise MCPAuthenticationError("Token interno do servidor MCP não configurado.")

    if not client_token:
        raise MCPAuthenticationError("Token do cliente MCP não fornecido.")

    if not hmac.compare_digest(
        expected_token.encode("utf-8"),
        client_token.encode("utf-8"),
    ):
        raise MCPAuthenticationError("Cliente MCP não autorizado.")
