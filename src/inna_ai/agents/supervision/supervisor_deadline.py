"""
Hard deadline do Supervisor Gemini.

A chamada externa é executada em outro processo para que
possa ser encerrada quando ultrapassar o orçamento total.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from inna_ai.orchestration.contracts import SupervisorDecision
from inna_ai.agents.supervision.supervisor_config import get_supervisor_runtime_config
from inna_ai.agents.supervision.supervisor_llm import _obter_mensagem_protegida
from inna_ai.resilience.tracing import get_shared_resilience_runtime, traced_resilience_operation
from inna_ai.resilience import FailureKind
from inna_ai.resilience.deadline import DeadlineBudget
from inna_ai.resilience.policies import SUPERVISOR_GENERATION_POLICY

PROJECT_ROOT = (
    Path(__file__)
    .resolve()
    .parents[2]
)


class SupervisorDeadlineExceeded(
    TimeoutError
):
    """
    O Gemini ultrapassou o prazo total do Supervisor.
    """


class SupervisorWorkerError(
    RuntimeError
):
    """
    Falha estruturada e sanitizada recebida do worker.
    """

    def __init__(
        self,
        *,
        error_type: str,
        failure_kind: FailureKind,
    ) -> None:
        safe_error_type = "".join(
            character
            for character in str(
                error_type
                or "GeminiError"
            )
            if (
                character.isalnum()
                or character in "._-"
            )
        )[:120]

        if not safe_error_type:
            safe_error_type = (
                "GeminiError"
            )

        self.error_type = (
            safe_error_type
        )

        self.failure_kind = (
            failure_kind
        )

        super().__init__(
            "Supervisor Gemini worker failed: "
            f"{safe_error_type} "
            f"({failure_kind.value})."
        )


def _minimal_context(
    context: dict[str, Any] | None,
    protected_message: str,
) -> dict[str, str]:
    if not isinstance(context, dict):
        context = {}

    return {
        "current_message": protected_message,
        "rendered_prompt": str(
            context.get(
                "rendered_prompt",
                "",
            )
        ),
    }


def _parse_failure_kind(
    value: Any,
) -> FailureKind:
    try:
        return FailureKind(
            str(value)
        )
    except (
        TypeError,
        ValueError,
    ):
        return FailureKind.UNKNOWN


def _parse_worker_output(
    stdout: str,
) -> dict[str, Any]:
    lines = [
        line.strip()
        for line in str(stdout or "").splitlines()
        if line.strip()
    ]

    if not lines:
        raise RuntimeError(
            "O processo Gemini terminou sem resposta."
        )

    try:
        result = json.loads(
            lines[-1]
        )
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            "O processo Gemini retornou uma "
            "resposta inválida."
        ) from exc

    if not isinstance(result, dict):
        raise RuntimeError(
            "Formato de resposta do processo inválido."
        )

    return result


def classificar_com_gemini_com_deadline(
    *,
    mensagem: str,
    context: dict[str, Any] | None = None,
) -> SupervisorDecision:
    runtime_config = (
        get_supervisor_runtime_config()
    )

    protected_message = (
        _obter_mensagem_protegida(
            mensagem,
            context,
        )
    )

    payload = json.dumps(
        {
            "message": protected_message,
            "context": _minimal_context(
                context,
                protected_message,
            ),
        },
        ensure_ascii=False,
    )

    creation_flags = (
        subprocess.CREATE_NO_WINDOW
        if os.name == "nt"
        else 0
    )

    total_deadline_seconds = (
        runtime_config.total_deadline_ms
        / 1000.0
    )

    deadline_budget = DeadlineBudget(
        total_deadline_seconds,
        reserve_seconds=0.25,
    )

    resilience_runtime = (
        get_shared_resilience_runtime()
    )

    requested_timeout_ms = int(
        getattr(
            runtime_config,
            "timeout_ms",
            runtime_config.total_deadline_ms,
        )
    )

    requested_timeout_seconds = (
        requested_timeout_ms
        / 1000.0
    )

    def execute_worker() -> SupervisorDecision:
        attempt_timeout_seconds = (
            deadline_budget.clamp_timeout(
                requested_timeout_seconds
            )
        )

        worker_environment = (
            os.environ.copy()
        )

        # O processo pai é a autoridade de retry.
        # O SDK Gemini executa uma única tentativa
        # dentro de cada tentativa da INNA.
        worker_environment[
            "INNA_SUPERVISOR_RETRY_ATTEMPTS"
        ] = "1"

        try:
            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "src.agents.supervisor_worker",
                ],
                input=payload,
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
                cwd=str(PROJECT_ROOT),
                env=worker_environment,
                timeout=attempt_timeout_seconds,
                check=False,
                creationflags=creation_flags,
            )

        except subprocess.TimeoutExpired as exc:
            raise SupervisorDeadlineExceeded(
                "Gemini ultrapassou o orçamento "
                "da tentativa do Supervisor."
            ) from exc

        result = _parse_worker_output(
            completed.stdout
        )

        if not result.get("ok"):
            error_type = str(
                result.get(
                    "error_type",
                    "GeminiError",
                )
            )

            failure_kind = (
                _parse_failure_kind(
                    result.get(
                        "failure_kind"
                    )
                )
            )

            raise SupervisorWorkerError(
                error_type=error_type,
                failure_kind=failure_kind,
            )

        return SupervisorDecision.model_validate(
            result["decision"]
        )

    with traced_resilience_operation(
        SUPERVISOR_GENERATION_POLICY
    ):
        return resilience_runtime.execute(
            policy=(
                SUPERVISOR_GENERATION_POLICY
            ),
            operation=execute_worker,
            deadline_budget=deadline_budget,
            minimum_retry_attempt_seconds=0.25,
        )


__all__ = [
    "SupervisorDeadlineExceeded",
    "SupervisorWorkerError",
    "classificar_com_gemini_com_deadline",
]
