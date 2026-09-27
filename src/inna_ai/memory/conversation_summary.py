"""
Resumo conversacional incremental da INNA.

O resumo representa memória compacta da thread atual.
Ele não substitui:
- o histórico cronológico;
- a memória permanente do usuário;
- o perfil financeiro consolidado.

Princípios:
- somente mensagens do usuário geram fatos pessoais;
- mensagens do assistente podem registrar ações da conversa;
- informações recentes sobrescrevem informações antigas;
- dados sensíveis são sanitizados;
- o tamanho final é limitado.
"""

from __future__ import annotations

import re
from typing import Any, Mapping, Sequence

from inna_ai.context.privacy_filter import sanitize_sensitive_text
from inna_ai.context.token_budget import truncate_text_to_token_budget
from inna_ai.memory.extractor import extrair_memoria_da_mensagem_inna


_MAX_FACT_LENGTH = 240

_FINANCIAL_LABELS = {
    "renda_mensal": "Renda mensal",
    "gastos_mensais": "Gastos mensais",
    "valor_reserva": "Reserva ou capacidade de guardar",
    "possui_dividas": "Possui dívidas",
    "uso_cartao_credito": "Utiliza cartão de crédito",
    "ultima_meta": "Meta financeira",
    "objetivo_principal": "Objetivo principal",
    "ultimo_score": "Último score",
    "ultimo_risco": "Último nível de risco",
}

_IGNORED_MEMORY_FIELDS = {
    "resumo_contexto",
    "nivel_confianca",
    "tags",
    "preferencia_linguagem",
    "memoria_json",
}


_MONEY_PATTERN = (
    r"(?:r\$\s*)?"
    r"(\d{1,3}(?:\.\d{3})+(?:,\d{1,2})?"
    r"|\d+(?:,\d{1,2})?"
    r"|\d+(?:\.\d{1,2})?)"
    r"(?!\d)"
)

_INCOME_UPDATE_PATTERN = re.compile(
    r"(?:minha\s+)?renda(?:\s+mensal)?"
    r"(?:\s+agora|\s+atualmente)?"
    r"\s*(?:é|e|era|:|de)?\s*"
    + _MONEY_PATTERN,
    flags=re.IGNORECASE,
)


def _to_mapping(
    value: Any,
) -> dict[str, Any] | None:
    if isinstance(value, Mapping):
        return dict(value)

    model_dump = getattr(
        value,
        "model_dump",
        None,
    )

    if callable(model_dump):
        dumped = model_dump()

        if isinstance(dumped, Mapping):
            return dict(dumped)

    return None


def _normalize_history(
    history: Any,
) -> list[dict[str, str]]:
    if (
        not isinstance(history, Sequence)
        or isinstance(
            history,
            (str, bytes, bytearray),
        )
    ):
        return []

    normalized: list[dict[str, str]] = []

    for raw_message in history:
        message = _to_mapping(
            raw_message
        )

        if message is None:
            continue

        role = str(
            message.get("role", "")
        ).strip().lower()

        content = str(
            message.get("content", "")
        ).strip()

        if (
            role not in {
                "user",
                "assistant",
                "system",
                "tool",
            }
            or not content
        ):
            continue

        normalized.append({
            "role": role,
            "content": content,
        })

    return normalized


def _clean_text(
    value: Any,
    *,
    max_characters: int = _MAX_FACT_LENGTH,
) -> str:
    text = re.sub(
        r"\s+",
        " ",
        str(value or "").strip(),
    )

    sanitized, _ = sanitize_sensitive_text(
        text
    )

    return sanitized[:max_characters].strip()


def _extract_existing_facts(
    summary: str,
) -> dict[str, str]:
    facts: dict[str, str] = {}

    for line in str(
        summary or ""
    ).splitlines():
        normalized = line.strip()

        if not normalized.startswith("- "):
            continue

        body = normalized[2:].strip()

        if ":" not in body:
            continue

        label, value = body.split(
            ":",
            1,
        )

        label = label.strip()
        value = value.strip()

        if (
            label == "Última ação da INNA"
        ):
            continue

        if label and value:
            facts[label] = value

    return facts


def _format_value(
    field: str,
    value: Any,
) -> str:
    if isinstance(value, bool):
        return "sim" if value else "não"

    if field in {
        "renda_mensal",
        "gastos_mensais",
        "valor_reserva",
    }:
        try:
            number = float(value)

            formatted = (
                f"{number:,.2f}"
                .replace(",", "_")
                .replace(".", ",")
                .replace("_", ".")
            )

            return f"R$ {formatted}"
        except (TypeError, ValueError):
            pass

    return _clean_text(value)


def _parse_money_value(
    value: str,
) -> float | None:
    text = re.sub(
        r"[^0-9,.]",
        "",
        str(value or ""),
    )

    if not text:
        return None

    if "," in text and "." in text:
        text = (
            text.replace(".", "")
            .replace(",", ".")
        )

    elif "," in text:
        text = text.replace(",", ".")

    try:
        return float(text)
    except ValueError:
        return None


def _extract_deterministic_user_facts(
    content: str,
) -> dict[str, str]:
    facts: dict[str, str] = {}

    match = _INCOME_UPDATE_PATTERN.search(
        str(content or "")
    )

    if match is not None:
        income = _parse_money_value(
            match.group(1)
        )

        if income is not None:
            facts["Renda mensal"] = (
                _format_value(
                    "renda_mensal",
                    income,
                )
            )

    return facts


def _extract_user_facts(
    content: str,
) -> dict[str, str]:
    facts = (
        _extract_deterministic_user_facts(
            content
        )
    )

    try:
        extracted = (
            extrair_memoria_da_mensagem_inna(
                content
            )
        )
    except Exception:
        return facts

    if not isinstance(extracted, Mapping):
        return facts

    data = extracted.get("dados")

    if not isinstance(data, Mapping):
        return facts

    for field, value in data.items():
        if (
            field in _IGNORED_MEMORY_FIELDS
            or value is None
        ):
            continue

        label = _FINANCIAL_LABELS.get(
            field
        )

        if not label:
            continue

        formatted = _format_value(
            field,
            value,
        )

        if formatted:
            facts.setdefault(
                label,
                formatted,
            )

    return facts


def _extract_conversation_action(
    role: str,
    content: str,
) -> str | None:
    if role != "assistant":
        return None

    normalized = _clean_text(
        content,
        max_characters=180,
    )

    if not normalized:
        return None

    action_terms = (
        "diagnóstico",
        "saldo",
        "score",
        "risco",
        "relatório",
        "histórico",
        "reserva",
    )

    if not any(
        term in normalized.lower()
        for term in action_terms
    ):
        return None

    return normalized


def build_conversation_summary(
    *,
    previous_summary: str = "",
    conversation_history: (
        list[dict[str, Any]] | None
    ) = None,
    max_history_messages: int = 20,
    max_summary_tokens: int = 500,
) -> str:
    """
    Gera ou atualiza um resumo incremental da thread.

    Fatos recentes do usuário sobrescrevem fatos anteriores
    com o mesmo significado.
    """
    max_history_messages = max(
        1,
        min(
            int(max_history_messages),
            100,
        ),
    )

    history = _normalize_history(
        conversation_history
    )[-max_history_messages:]

    facts = _extract_existing_facts(
        previous_summary
    )

    latest_action: str | None = None

    for message in history:
        role = message["role"]
        content = message["content"]

        if role == "user":
            extracted_facts = (
                _extract_user_facts(
                    content
                )
            )

            facts.update(
                extracted_facts
            )

        action = (
            _extract_conversation_action(
                role,
                content,
            )
        )

        if action:
            latest_action = action

    if not facts and not latest_action:
        return _clean_text(
            previous_summary,
            max_characters=2000,
        )

    lines = [
        "Resumo incremental da conversa:",
    ]

    for label in sorted(facts):
        lines.append(
            f"- {label}: {facts[label]}"
        )

    if latest_action:
        lines.append(
            "- Última ação da INNA: "
            + latest_action
        )

    rendered = "\n".join(lines)

    sanitized, _ = sanitize_sensitive_text(
        rendered
    )

    return truncate_text_to_token_budget(
        sanitized,
        max_tokens=max_summary_tokens,
    ).strip()


def update_conversation_summary_state(
    state: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """
    Retorna uma atualização parcial compatível com LangGraph.
    """
    safe_state = (
        dict(state)
        if isinstance(state, Mapping)
        else {}
    )

    previous_summary = str(
        safe_state.get(
            "conversation_summary",
            "",
        )
        or ""
    )

    updated_summary = (
        build_conversation_summary(
            previous_summary=previous_summary,
            conversation_history=safe_state.get(
                "conversation_history",
                [],
            ),
        )
    )

    trace = list(
        safe_state.get("trace", [])
    )

    trace.append(
        "conversation_summary:"
        + (
            "updated"
            if updated_summary != previous_summary
            else "unchanged"
        )
    )

    return {
        "conversation_summary": (
            updated_summary
        ),
        "trace": trace,
    }


__all__ = [
    "build_conversation_summary",
    "update_conversation_summary_state",
]
