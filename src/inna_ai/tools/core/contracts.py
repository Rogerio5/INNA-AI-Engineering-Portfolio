"""
Contratos formais do sistema de ferramentas da INNA.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ToolStatus(str, Enum):
    SUCCESS = "success"
    ERROR = "error"
    DENIED = "denied"
    VALIDATION_ERROR = "validation_error"
    TIMEOUT = "timeout"
    NOT_FOUND = "not_found"


class ToolExecutionContext(BaseModel):
    """
    Contexto controlado enviado à ferramenta.

    Dados privados não devem ser incluídos sem necessidade.
    """

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    requested_by: str = Field(
        min_length=1,
        max_length=100,
    )

    user_id: str | None = Field(
        default=None,
        max_length=200,
    )

    session_id: str | None = Field(
        default=None,
        max_length=200,
    )

    trace_id: str | None = Field(
        default=None,
        max_length=200,
    )

    metadata: dict[str, Any] = Field(
        default_factory=dict,
    )


class ToolCall(BaseModel):
    """
    Solicitação formal de execução de uma ferramenta.
    """

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    call_id: str = Field(
        default_factory=lambda: uuid4().hex,
        min_length=1,
        max_length=100,
    )

    tool_name: str = Field(
        min_length=1,
        max_length=120,
        pattern=r"^[a-z][a-z0-9_]*$",
    )

    arguments: dict[str, Any] = Field(
        default_factory=dict,
    )

    context: ToolExecutionContext


class ToolError(BaseModel):
    """
    Erro seguro retornado pelo executor.
    """

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    code: str = Field(
        min_length=1,
        max_length=100,
    )

    message: str = Field(
        min_length=1,
        max_length=500,
    )

    retryable: bool = False

    details: dict[str, Any] = Field(
        default_factory=dict,
    )


class ToolResult(BaseModel):
    """
    Resultado padronizado de uma ferramenta.
    """

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    call_id: str
    tool_name: str
    status: ToolStatus

    output: dict[str, Any] | None = None
    error: ToolError | None = None

    duration_ms: float = Field(
        ge=0,
    )

    started_at: datetime = Field(
        default_factory=utc_now,
    )

    finished_at: datetime = Field(
        default_factory=utc_now,
    )

    metadata: dict[str, Any] = Field(
        default_factory=dict,
    )

    @property
    def ok(self) -> bool:
        return self.status == ToolStatus.SUCCESS


__all__ = [
    "ToolCall",
    "ToolError",
    "ToolExecutionContext",
    "ToolResult",
    "ToolStatus",
    "utc_now",
]
