from __future__ import annotations

import json
import os
import subprocess
from collections.abc import Mapping
from pathlib import Path
from typing import Any


class RagasBridgeError(RuntimeError):
    """Controlled failure while executing isolated RAGAS."""


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _default_ragas_python() -> Path:
    venv_root = _repo_root() / ".venv-ragas"
    candidates = (
        venv_root / "Scripts" / "python.exe",
        venv_root / "bin" / "python",
    )

    for candidate in candidates:
        if candidate.is_file():
            return candidate

    return candidates[0] if os.name == "nt" else candidates[1]


    return (
        _repo_root()
        / ".venv-ragas"
        / "Scripts"
        / "python.exe"
    )


def _runner_path() -> Path:
    return (
        _repo_root()
        / "scripts"
        / "run_ragas_isolated_metric.py"
    )


def _parse_result(stdout: str) -> dict[str, Any]:
    candidates = [
        stdout.strip(),
        *reversed(
            [
                line.strip()
                for line in stdout.splitlines()
                if line.strip()
            ]
        ),
    ]

    for candidate in candidates:
        if not candidate:
            continue

        try:
            result = json.loads(candidate)
        except json.JSONDecodeError:
            continue

        if isinstance(result, dict):
            return result

    raise RagasBridgeError(
        "isolated RAGAS returned invalid JSON"
    )


def _run_isolated(
    payload: Mapping[str, Any],
    *,
    timeout_seconds: float,
    ragas_python: Path | None,
    environment_overrides: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    python_path = (
        ragas_python
        or _default_ragas_python()
    )
    runner = _runner_path()

    if not python_path.is_file():
        raise RagasBridgeError(
            "isolated RAGAS Python executable not found"
        )

    if not runner.is_file():
        raise RagasBridgeError(
            "isolated RAGAS runner not found"
        )

    serialized = json.dumps(
        dict(payload),
        ensure_ascii=False,
        sort_keys=True,
    )

    environment = os.environ.copy()

    if environment_overrides:
        environment.update(environment_overrides)

    completed = subprocess.run(
        [str(python_path), str(runner)],
        input=serialized,
        text=True,
        capture_output=True,
        timeout=timeout_seconds,
        check=False,
        cwd=str(_repo_root()),
        env=environment,
    )

    if completed.returncode != 0:
        result = None

        try:
            result = _parse_result(
                completed.stdout
            )
        except RagasBridgeError:
            pass

        if result is not None:
            message = str(
                result.get("error")
                or result.get("error_type")
                or "isolated RAGAS execution failed"
            )
        else:
            message = (
                completed.stderr.strip()
                or "isolated RAGAS execution failed"
            )

        raise RagasBridgeError(message)

    return _parse_result(completed.stdout)


def run_ragas_non_llm(
    payload: Mapping[str, Any],
    *,
    timeout_seconds: float = 30.0,
    ragas_python: Path | None = None,
) -> dict[str, Any]:
    """Execute deterministic RAGAS metrics in the isolated venv."""
    runner_payload = dict(payload)
    runner_payload["execution_mode"] = "non_llm"

    return _run_isolated(
        runner_payload,
        timeout_seconds=timeout_seconds,
        ragas_python=ragas_python,
    )


def run_ragas_llm(
    payload: Mapping[str, Any],
    *,
    api_key: str | None = None,
    model: str | None = None,
    timeout_seconds: float = 120.0,
    ragas_python: Path | None = None,
    validate_only: bool = False,
) -> dict[str, Any]:
    """Execute Gemini-backed RAGAS metrics in the isolated venv."""
    resolved_api_key = (
        api_key
        or os.environ.get("GEMINI_API_KEY")
        or ""
    ).strip()
    resolved_model = (
        model
        or os.environ.get("INNA_DEEPEVAL_GEMINI_MODEL")
        or os.environ.get("GEMINI_MODEL")
        or ""
    ).strip()

    if not resolved_api_key:
        raise RagasBridgeError(
            "Gemini API key is required for RAGAS LLM metrics"
        )

    if not resolved_model:
        raise RagasBridgeError(
            "Gemini model is required for RAGAS LLM metrics"
        )

    runner_payload = dict(payload)
    runner_payload["execution_mode"] = (
        "llm_validate"
        if validate_only
        else "llm"
    )

    return _run_isolated(
        runner_payload,
        timeout_seconds=timeout_seconds,
        ragas_python=ragas_python,
        environment_overrides={
            "INNA_RAGAS_API_KEY": resolved_api_key,
            "INNA_RAGAS_MODEL": resolved_model,
        },
    )


def _normalize_agentic_payload(
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    response = str(
        payload.get("response") or ""
    )
    reference = str(
        payload.get("reference") or ""
    )
    user_input = str(
        payload.get("user_input") or ""
    )
    retrieved_contexts = (
        payload.get("retrieved_contexts")
        or ()
    )

    if isinstance(retrieved_contexts, str):
        retrieved_contexts = (
            retrieved_contexts,
        )

    contexts = [
        str(context).strip()
        for context in retrieved_contexts
        if str(context).strip()
    ]

    normalized: dict[str, Any] = {
        "user_input": user_input,
        "response": response,
        "retrieved_contexts": contexts,
    }

    if reference:
        normalized["reference"] = reference

    return normalized


def run_ragas_agentic_payload(
    payload: Mapping[str, Any],
    *,
    timeout_seconds: float = 30.0,
    ragas_python: Path | None = None,
) -> dict[str, Any]:
    """Adapt an INNA RAGAS payload to deterministic isolated metrics."""
    normalized = _normalize_agentic_payload(
        payload
    )

    reference = str(
        normalized.get("reference") or ""
    )
    contexts = normalized[
        "retrieved_contexts"
    ]

    runner_payload: dict[str, Any] = {
        "response": normalized["response"],
    }

    if reference:
        runner_payload["reference"] = reference

    if contexts:
        runner_payload["required_phrase"] = contexts[0]

    return run_ragas_non_llm(
        runner_payload,
        timeout_seconds=timeout_seconds,
        ragas_python=ragas_python,
    )


def run_ragas_agentic_payload_live(
    payload: Mapping[str, Any],
    *,
    api_key: str | None = None,
    model: str | None = None,
    timeout_seconds: float = 120.0,
    ragas_python: Path | None = None,
    validate_only: bool = False,
) -> dict[str, Any]:
    """Adapt an INNA RAGAS payload to isolated Gemini-backed metrics."""
    normalized = _normalize_agentic_payload(
        payload
    )

    return run_ragas_llm(
        normalized,
        api_key=api_key,
        model=model,
        timeout_seconds=timeout_seconds,
        ragas_python=ragas_python,
        validate_only=validate_only,
    )
