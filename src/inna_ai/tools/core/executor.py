"""
Executor seguro das ferramentas registradas.
"""

from __future__ import annotations

from concurrent.futures import (
    ThreadPoolExecutor,
    TimeoutError as FutureTimeoutError,
)
from datetime import datetime, timezone
import logging
from time import perf_counter
from typing import Any

from pydantic import (
    BaseModel,
    ValidationError,
)

from inna_ai.tools.core.contracts import ToolCall, ToolError, ToolResult, ToolStatus
from inna_ai.tools.core.permissions import ToolPermissionPolicy
from inna_ai.tools.core.registry import ToolDefinition, ToolNotFoundError, ToolRegistry


logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ToolExecutor:
    """
    Valida, autoriza e executa ferramentas registradas.

    Ferramentas de rede e banco também devem possuir
    timeout nativo no cliente utilizado.
    """

    def __init__(
        self,
        *,
        registry: ToolRegistry,
        permission_policy: (
            ToolPermissionPolicy | None
        ) = None,
        max_workers: int = 4,
    ) -> None:
        if max_workers <= 0:
            raise ValueError(
                "max_workers deve ser positivo."
            )

        self._registry = registry
        self._permission_policy = (
            permission_policy
            or ToolPermissionPolicy()
        )

        self._pool = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="inna-tool",
        )

        self._closed = False

    def execute(
        self,
        call: ToolCall,
    ) -> ToolResult:
        if self._closed:
            raise RuntimeError(
                "ToolExecutor já foi encerrado."
            )

        started_at = _utc_now()
        started_counter = perf_counter()

        try:
            definition = self._registry.get(
                call.tool_name
            )
        except ToolNotFoundError:
            return self._build_error_result(
                call=call,
                status=ToolStatus.NOT_FOUND,
                code="tool_not_found",
                message=(
                    "A ferramenta solicitada não "
                    "está registrada."
                ),
                started_at=started_at,
                started_counter=started_counter,
                retryable=False,
            )

        permission = (
            self._permission_policy.evaluate(
                agent_name=(
                    call.context.requested_by
                ),
                definition=definition,
            )
        )

        if not permission.allowed:
            return self._build_error_result(
                call=call,
                status=ToolStatus.DENIED,
                code="tool_permission_denied",
                message=(
                    "O agente não possui permissão "
                    "para executar esta ferramenta."
                ),
                started_at=started_at,
                started_counter=started_counter,
                retryable=False,
                details={
                    "reason": permission.reason,
                },
            )

        try:
            validated_input = (
                definition.input_model
                .model_validate(
                    call.arguments
                )
            )
        except ValidationError as exc:
            return self._build_error_result(
                call=call,
                status=(
                    ToolStatus.VALIDATION_ERROR
                ),
                code="tool_input_validation_error",
                message=(
                    "Os argumentos da ferramenta "
                    "são inválidos."
                ),
                started_at=started_at,
                started_counter=started_counter,
                retryable=False,
                details={
                    "errors": exc.errors(
                        include_url=False,
                    ),
                },
            )

        future = self._pool.submit(
            definition.handler,
            validated_input,
            call.context,
        )

        try:
            raw_output = future.result(
                timeout=(
                    definition.timeout_seconds
                )
            )
        except FutureTimeoutError:
            future.cancel()

            return self._build_error_result(
                call=call,
                status=ToolStatus.TIMEOUT,
                code="tool_timeout",
                message=(
                    "A ferramenta excedeu o tempo "
                    "máximo de execução."
                ),
                started_at=started_at,
                started_counter=started_counter,
                retryable=True,
                details={
                    "timeout_seconds": (
                        definition.timeout_seconds
                    ),
                },
            )
        except Exception as exc:
            logger.exception(
                "Falha ao executar ferramenta %s",
                call.tool_name,
            )

            return self._build_error_result(
                call=call,
                status=ToolStatus.ERROR,
                code="tool_execution_error",
                message=(
                    "A ferramenta falhou durante "
                    "a execução."
                ),
                started_at=started_at,
                started_counter=started_counter,
                retryable=False,
                details={
                    "exception_type": (
                        type(exc).__name__
                    ),
                },
            )

        try:
            validated_output = (
                definition.output_model
                .model_validate(raw_output)
            )
        except ValidationError as exc:
            return self._build_error_result(
                call=call,
                status=(
                    ToolStatus.VALIDATION_ERROR
                ),
                code="tool_output_validation_error",
                message=(
                    "A ferramenta produziu uma "
                    "saída incompatível."
                ),
                started_at=started_at,
                started_counter=started_counter,
                retryable=False,
                details={
                    "errors": exc.errors(
                        include_url=False,
                    ),
                },
            )

        finished_at = _utc_now()

        return ToolResult(
            call_id=call.call_id,
            tool_name=call.tool_name,
            status=ToolStatus.SUCCESS,
            output=validated_output.model_dump(
                mode="json"
            ),
            error=None,
            duration_ms=round(
                (
                    perf_counter()
                    - started_counter
                )
                * 1000,
                3,
            ),
            started_at=started_at,
            finished_at=finished_at,
            metadata={
                "requested_by": (
                    call.context.requested_by
                ),
                "trace_id": (
                    call.context.trace_id
                ),
                "idempotent": (
                    definition.idempotent
                ),
                "sensitive_output": (
                    definition.sensitive_output
                ),
            },
        )

    def _build_error_result(
        self,
        *,
        call: ToolCall,
        status: ToolStatus,
        code: str,
        message: str,
        started_at: datetime,
        started_counter: float,
        retryable: bool,
        details: dict[str, Any] | None = None,
    ) -> ToolResult:
        return ToolResult(
            call_id=call.call_id,
            tool_name=call.tool_name,
            status=status,
            output=None,
            error=ToolError(
                code=code,
                message=message,
                retryable=retryable,
                details=details or {},
            ),
            duration_ms=round(
                (
                    perf_counter()
                    - started_counter
                )
                * 1000,
                3,
            ),
            started_at=started_at,
            finished_at=_utc_now(),
            metadata={
                "requested_by": (
                    call.context.requested_by
                ),
                "trace_id": (
                    call.context.trace_id
                ),
            },
        )

    def close(
        self,
        *,
        wait: bool = True,
    ) -> None:
        if self._closed:
            return

        self._closed = True

        self._pool.shutdown(
            wait=wait,
            cancel_futures=True,
        )

    def __enter__(self) -> "ToolExecutor":
        return self

    def __exit__(
        self,
        exc_type,
        exc_value,
        traceback,
    ) -> None:
        self.close()


__all__ = [
    "ToolExecutor",
]
