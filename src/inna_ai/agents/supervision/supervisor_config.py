"""
Configuração central do runtime LLM do Supervisor da INNA.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import os
from pathlib import Path

from dotenv import load_dotenv

from inna_ai.llm.model_registry import DEFAULT_TEXT_MODEL, LLMRole, get_model_for_role, reset_model_registry_cache


load_dotenv(
    dotenv_path=Path(".env"),
    override=False,
)


DEFAULT_SUPERVISOR_MODEL = (
    DEFAULT_TEXT_MODEL
)

DEFAULT_SUPERVISOR_TIMEOUT_MS = 15_000
DEFAULT_SUPERVISOR_TOTAL_DEADLINE_MS = 8_000
DEFAULT_SUPERVISOR_RETRY_ATTEMPTS = 2
DEFAULT_SUPERVISOR_MAX_OUTPUT_TOKENS = 220
DEFAULT_SUPERVISOR_MAX_CONTEXT_CHARS = 8_000


def _read_int_environment(
    name: str,
    default: int,
    *,
    minimum: int,
    maximum: int,
) -> int:
    raw_value = str(
        os.getenv(name, "")
    ).strip()

    if not raw_value:
        return default

    try:
        parsed = int(raw_value)
    except ValueError:
        return default

    return min(
        maximum,
        max(minimum, parsed),
    )


@dataclass(
    frozen=True,
    slots=True,
)
class SupervisorRuntimeConfig:
    model: str

    timeout_ms: int
    total_deadline_ms: int
    retry_attempts: int

    max_output_tokens: int
    max_context_characters: int


@lru_cache(maxsize=1)
def get_supervisor_runtime_config(
) -> SupervisorRuntimeConfig:
    model = get_model_for_role(
        LLMRole.SUPERVISOR
    )

    return SupervisorRuntimeConfig(
        model=model,
        timeout_ms=_read_int_environment(
            "INNA_SUPERVISOR_TIMEOUT_MS",
            DEFAULT_SUPERVISOR_TIMEOUT_MS,
            minimum=3_000,
            maximum=60_000,
        ),
        total_deadline_ms=_read_int_environment(
            "INNA_SUPERVISOR_TOTAL_DEADLINE_MS",
            DEFAULT_SUPERVISOR_TOTAL_DEADLINE_MS,
            minimum=1_000,
            maximum=30_000,
        ),
        retry_attempts=_read_int_environment(
            "INNA_SUPERVISOR_RETRY_ATTEMPTS",
            DEFAULT_SUPERVISOR_RETRY_ATTEMPTS,
            minimum=1,
            maximum=3,
        ),
        max_output_tokens=_read_int_environment(
            "INNA_SUPERVISOR_MAX_OUTPUT_TOKENS",
            DEFAULT_SUPERVISOR_MAX_OUTPUT_TOKENS,
            minimum=100,
            maximum=1_000,
        ),
        max_context_characters=(
            _read_int_environment(
                "INNA_SUPERVISOR_MAX_CONTEXT_CHARS",
                DEFAULT_SUPERVISOR_MAX_CONTEXT_CHARS,
                minimum=1_000,
                maximum=20_000,
            )
        ),
    )


def get_gemini_api_key() -> str:
    api_key = str(
        os.getenv("GEMINI_API_KEY")
        or os.getenv("GOOGLE_API_KEY")
        or ""
    ).strip()

    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY ou GOOGLE_API_KEY "
            "não configurada."
        )

    return api_key


def reset_supervisor_config_cache() -> None:
    get_supervisor_runtime_config.cache_clear()
    reset_model_registry_cache()


__all__ = [
    "DEFAULT_SUPERVISOR_MODEL",
    "DEFAULT_SUPERVISOR_TIMEOUT_MS",
    "DEFAULT_SUPERVISOR_TOTAL_DEADLINE_MS",
    "DEFAULT_SUPERVISOR_RETRY_ATTEMPTS",
    "DEFAULT_SUPERVISOR_MAX_OUTPUT_TOKENS",
    "DEFAULT_SUPERVISOR_MAX_CONTEXT_CHARS",
    "SupervisorRuntimeConfig",
    "get_supervisor_runtime_config",
    "get_gemini_api_key",
    "reset_supervisor_config_cache",
]
