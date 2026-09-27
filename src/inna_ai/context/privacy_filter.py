"""
Filtro de privacidade do contexto da INNA.

Mascara dados pessoais antes que o contexto seja enviado
para modelos de linguagem ou armazenado em telemetria.
"""

from __future__ import annotations

import re

from inna_ai.context.schemas import PrivacyReport


_EMAIL_PATTERN = re.compile(
    r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"
)

_PHONE_PATTERN = re.compile(
    r"(?<!\d)"
    r"(?:\+?55\s*)?"
    r"(?:\(?\d{2}\)?[\s.-]*)?"
    r"\d{4,5}[\s.-]?\d{4}"
    r"(?!\d)"
)

_CPF_PATTERN = re.compile(
    r"(?<!\d)"
    r"\d{3}\.?\d{3}\.?\d{3}-?\d{2}"
    r"(?!\d)"
)

_CARD_PATTERN = re.compile(
    r"(?<!\d)"
    r"(?:\d[\s-]?){13,19}"
    r"(?!\d)"
)


def _mask_value(
    match: re.Match[str],
    *,
    label: str,
) -> str:
    return f"[{label}_PROTEGIDO]"


def sanitize_sensitive_text(
    text: str,
) -> tuple[str, PrivacyReport]:
    """
    Mascara dados sensíveis presentes em um texto.
    """
    original = str(text or "")
    report = PrivacyReport()

    sanitized, count = _EMAIL_PATTERN.subn(
        lambda match: _mask_value(
            match,
            label="EMAIL",
        ),
        original,
    )

    report.email_addresses_masked = count

    sanitized, count = _CPF_PATTERN.subn(
        lambda match: _mask_value(
            match,
            label="CPF",
        ),
        sanitized,
    )

    report.cpf_numbers_masked = count

    sanitized, count = _PHONE_PATTERN.subn(
        lambda match: _mask_value(
            match,
            label="TELEFONE",
        ),
        sanitized,
    )

    report.phone_numbers_masked = count

    sanitized, count = _CARD_PATTERN.subn(
        lambda match: _mask_value(
            match,
            label="CARTAO",
        ),
        sanitized,
    )

    report.card_numbers_masked = count

    report.sensitive_items_found = (
        report.email_addresses_masked
        + report.phone_numbers_masked
        + report.cpf_numbers_masked
        + report.card_numbers_masked
    )

    return sanitized, report


def merge_privacy_reports(
    reports: list[PrivacyReport],
) -> PrivacyReport:
    merged = PrivacyReport()

    for report in reports:
        merged.sensitive_items_found += (
            report.sensitive_items_found
        )

        merged.email_addresses_masked += (
            report.email_addresses_masked
        )

        merged.phone_numbers_masked += (
            report.phone_numbers_masked
        )

        merged.cpf_numbers_masked += (
            report.cpf_numbers_masked
        )

        merged.card_numbers_masked += (
            report.card_numbers_masked
        )

    return merged


__all__ = [
    "sanitize_sensitive_text",
    "merge_privacy_reports",
]
