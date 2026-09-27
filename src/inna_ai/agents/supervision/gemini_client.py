"""
Cliente Gemini compartilhado do Supervisor da INNA.
"""

from __future__ import annotations

from functools import lru_cache

from google import genai
from google.genai import types

from inna_ai.agents.supervision.supervisor_config import get_gemini_api_key, get_supervisor_runtime_config


_TRANSIENT_STATUS_CODES = [
    408,
    429,
    500,
    502,
    503,
    504,
]


@lru_cache(maxsize=1)
def get_supervisor_client() -> genai.Client:
    """
    Cria um único cliente por processo.

    O timeout limita cada tentativa HTTP e as retentativas
    ficam restritas a erros transitórios.
    """
    config = get_supervisor_runtime_config()

    retry_options = types.HttpRetryOptions(
        attempts=config.retry_attempts,
        initial_delay=1.0,
        max_delay=3.0,
        exp_base=2.0,
        jitter=0.2,
        http_status_codes=(
            _TRANSIENT_STATUS_CODES
        ),
    )

    http_options = types.HttpOptions(
        timeout=config.timeout_ms,
        retry_options=retry_options,
    )

    return genai.Client(
        api_key=get_gemini_api_key(),
        http_options=http_options,
    )


def reset_supervisor_client_cache() -> None:
    """
    Usado principalmente em testes e troca de configuração.
    """
    get_supervisor_client.cache_clear()


__all__ = [
    "get_supervisor_client",
    "reset_supervisor_client_cache",
]
