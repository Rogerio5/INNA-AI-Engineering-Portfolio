"""
Seleção de histórico relevante para agentes da INNA.
"""

from __future__ import annotations

from typing import Any

from inna_ai.context.privacy_filter import merge_privacy_reports, sanitize_sensitive_text
from inna_ai.context.schemas import ContextMessage, PrivacyReport
from inna_ai.context.token_budget import estimate_tokens, truncate_text_to_token_budget


_ALLOWED_ROLES = {
    "user",
    "assistant",
    "system",
    "tool",
}


def _normalize_message(
    message: Any,
) -> dict[str, str] | None:
    if not isinstance(message, dict):
        return None

    role = str(
        message.get("role", "")
    ).strip().lower()

    content = str(
        message.get("content", "")
    ).strip()

    if role not in _ALLOWED_ROLES:
        return None

    if not content:
        return None

    return {
        "role": role,
        "content": content,
    }


def select_relevant_history(
    history: list[dict[str, Any]] | None,
    *,
    current_message: str = "",
    max_messages: int = 12,
    max_tokens: int = 1800,
    sanitize: bool = True,
) -> tuple[
    list[ContextMessage],
    PrivacyReport,
]:
    """
    Seleciona as mensagens mais recentes respeitando
    o orçamento definido.

    O histórico persistido não é alterado.
    """
    max_messages = max(
        1,
        min(int(max_messages), 50),
    )

    max_tokens = max(
        128,
        int(max_tokens),
    )

    normalized: list[dict[str, str]] = []

    for raw_message in history or []:
        message = _normalize_message(
            raw_message
        )

        if message is None:
            continue

        normalized.append(message)

    current_message = str(
        current_message or ""
    ).strip()

    # Evita repetir a mensagem atual no contexto selecionado.
    if (
        current_message
        and normalized
        and normalized[-1]["role"] == "user"
        and normalized[-1]["content"] == current_message
    ):
        normalized = normalized[:-1]

    candidates = normalized[-max_messages:]

    selected_reversed: list[ContextMessage] = []
    privacy_reports: list[PrivacyReport] = []

    tokens_used = 0

    for message in reversed(candidates):
        original_content = message["content"]

        if sanitize:
            content, privacy_report = (
                sanitize_sensitive_text(
                    original_content
                )
            )
        else:
            content = original_content
            privacy_report = PrivacyReport()

        remaining_tokens = (
            max_tokens - tokens_used
        )

        if remaining_tokens <= 0:
            break

        message_tokens = estimate_tokens(
            content
        )

        if message_tokens > remaining_tokens:
            content = (
                truncate_text_to_token_budget(
                    content,
                    max_tokens=remaining_tokens,
                )
            )

            message_tokens = estimate_tokens(
                content
            )

        if not content:
            continue

        selected_reversed.append(
            ContextMessage(
                role=message["role"],
                content=content,
                original_characters=len(
                    original_content
                ),
                sanitized=(
                    content != original_content
                ),
            )
        )

        privacy_reports.append(
            privacy_report
        )

        tokens_used += message_tokens

    selected = list(
        reversed(selected_reversed)
    )

    return (
        selected,
        merge_privacy_reports(
            privacy_reports
        ),
    )


__all__ = [
    "select_relevant_history",
]
