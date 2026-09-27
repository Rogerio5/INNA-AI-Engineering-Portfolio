from __future__ import annotations

import math
import unicodedata
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from inna_ai.governance.hitl.lifecycle import HumanReviewRiskLevel

DEFAULT_MINIMUM_CONFIDENCE = 0.60

_TERMINAL_REVIEW_STATUSES = {
    "approved",
    "corrected",
    "rejected",
    "cancelled",
    "expired",
    "failed",
}

_REVIEW_PENDING_STATUSES = {
    "requested",
    "waiting",
}


@dataclass(
    frozen=True,
    slots=True,
)
class HumanReviewPolicyDecision:
    requires_review: bool
    trigger: str
    reason: str
    risk_level: HumanReviewRiskLevel
    requested_by: str
    payload: dict[str, Any]
    metadata: dict[str, Any]

    def as_dict(
        self,
    ) -> dict[str, Any]:
        return {
            "requires_review": (
                self.requires_review
            ),
            "trigger": self.trigger,
            "reason": self.reason,
            "risk_level": self.risk_level,
            "requested_by": self.requested_by,
            "payload": deepcopy(
                self.payload
            ),
            "metadata": deepcopy(
                self.metadata
            ),
        }


class HumanReviewPolicyError(
    ValueError
):
    """
    Erro de configuração ou avaliação da política.
    """


def _normalize_text(
    value: Any,
) -> str:
    return str(
        value or ""
    ).strip()


def _normalize_token(
    value: Any,
) -> str:
    text = _normalize_text(
        value
    ).lower()

    normalized = unicodedata.normalize(
        "NFKD",
        text,
    )

    return "".join(
        character
        for character in normalized
        if not unicodedata.combining(
            character
        )
    ).replace(
        "-",
        "_",
    ).replace(
        " ",
        "_",
    )


def _normalize_bool(
    value: Any,
) -> bool:
    if isinstance(
        value,
        bool,
    ):
        return value

    if isinstance(
        value,
        int,
    ):
        return value != 0

    normalized = _normalize_token(
        value
    )

    return normalized in {
        "1",
        "true",
        "yes",
        "sim",
        "required",
        "necessario",
        "necessaria",
    }


def _safe_mapping(
    value: Any,
) -> Mapping[str, Any]:
    if isinstance(
        value,
        Mapping,
    ):
        return value

    return {}


def _first_non_empty(
    *values: Any,
) -> Any:
    for value in values:
        if value is None:
            continue

        if isinstance(
            value,
            str,
        ):
            if value.strip():
                return value

            continue

        return value

    return None


def _structured_response(
    state: Mapping[str, Any],
) -> Mapping[str, Any]:
    return _safe_mapping(
        state.get(
            "structured_response"
        )
    )


def _financial_data(
    state: Mapping[str, Any],
) -> Mapping[str, Any]:
    structured = _structured_response(
        state
    )

    for key in (
        "financial_data",
        "financial_diagnosis",
        "diagnosis",
        "diagnostico",
        "result",
    ):
        candidate = _safe_mapping(
            state.get(key)
        )

        if candidate:
            return candidate

        candidate = _safe_mapping(
            structured.get(key)
        )

        if candidate:
            return candidate

    return {}


def _resolve_current_agent(
    state: Mapping[str, Any],
) -> str:
    return _normalize_text(
        _first_non_empty(
            state.get(
                "current_agent"
            ),
            state.get(
                "last_agent"
            ),
            state.get(
                "next_node"
            ),
            "supervisor",
        )
    )


def _resolve_existing_review_status(
    state: Mapping[str, Any],
) -> str:
    current = _safe_mapping(
        state.get(
            "human_review_current"
        )
    )

    return _normalize_token(
        _first_non_empty(
            current.get(
                "status"
            ),
            state.get(
                "human_review_status"
            ),
        )
    )


def _resolve_risk_level(
    state: Mapping[str, Any],
) -> HumanReviewRiskLevel:
    """
    Resolve a maior severidade conhecida.

    O risco adaptativo da camada de roteamento passa
    a participar formalmente da política HITL.
    """

    structured = _structured_response(
        state
    )

    financial = _financial_data(
        state
    )

    aliases: dict[
        str,
        HumanReviewRiskLevel,
    ] = {
        "low": "low",
        "baixo": "low",
        "baixa": "low",
        "medium": "medium",
        "medio": "medium",
        "media": "medium",
        "moderate": "medium",
        "moderado": "medium",
        "moderada": "medium",
        "high": "high",
        "alto": "high",
        "alta": "high",
        "critical": "critical",
        "critico": "critical",
        "critica": "critical",
        "severe": "critical",
        "grave": "critical",
    }

    candidates = (
        state.get(
            "human_review_risk_level"
        ),
        state.get(
            "risk_level"
        ),
        state.get(
            "nivel_risco"
        ),
        state.get(
            "risk"
        ),

        # Semana 5 - Adaptive Gateway.
        state.get(
            "adaptive_risk"
        ),

        structured.get(
            "risk_level"
        ),
        structured.get(
            "nivel_risco"
        ),
        structured.get(
            "risk"
        ),
        financial.get(
            "risk_level"
        ),
        financial.get(
            "nivel_risco"
        ),
        financial.get(
            "risk"
        ),
    )

    severity_order = {
        "low": 0,
        "medium": 1,
        "high": 2,
        "critical": 3,
    }

    resolved: list[
        HumanReviewRiskLevel
    ] = []

    for candidate in candidates:
        normalized = _normalize_token(
            candidate
        )

        if not normalized:
            continue

        risk = aliases.get(
            normalized
        )

        if risk is not None:
            resolved.append(
                risk
            )

    if not resolved:
        return "low"

    return max(
        resolved,
        key=severity_order.__getitem__,
    )


def _resolve_confidence(
    state: Mapping[str, Any],
) -> float | None:
    structured = _structured_response(
        state
    )

    financial = _financial_data(
        state
    )

    raw = _first_non_empty(
        state.get(
            "confidence"
        ),
        state.get(
            "routing_confidence"
        ),
        state.get(
            "task_completion_score"
        ),
        structured.get(
            "confidence"
        ),
        structured.get(
            "confianca"
        ),
        financial.get(
            "confidence"
        ),
        financial.get(
            "confianca"
        ),
    )

    if raw is None:
        return None

    try:
        confidence = float(
            raw
        )
    except (
        TypeError,
        ValueError,
    ):
        return None

    if not math.isfinite(
        confidence
    ):
        return None

    if confidence > 1.0:
        if confidence <= 100.0:
            confidence /= 100.0
        else:
            return None

    return max(
        0.0,
        min(
            1.0,
            confidence,
        ),
    )


def _normalize_string_list(
    value: Any,
) -> list[str]:
    if isinstance(
        value,
        str,
    ):
        normalized = value.strip()

        return (
            [normalized]
            if normalized
            else []
        )

    if not isinstance(
        value,
        (
            list,
            tuple,
            set,
        ),
    ):
        return []

    result: list[str] = []

    for item in value:
        normalized = _normalize_text(
            item
        )

        if (
            normalized
            and normalized not in result
        ):
            result.append(
                normalized
            )

    return result


def _resolve_missing_requirements(
    state: Mapping[str, Any],
) -> list[str]:
    structured = _structured_response(
        state
    )

    values: list[str] = []

    for candidate in (
        state.get(
            "missing_requirements"
        ),
        state.get(
            "missing_fields"
        ),
        state.get(
            "required_missing_fields"
        ),
        structured.get(
            "missing_requirements"
        ),
        structured.get(
            "missing_fields"
        ),
    ):
        for item in _normalize_string_list(
            candidate
        ):
            if item not in values:
                values.append(
                    item
                )

    return values


def _resolve_inconsistencies(
    state: Mapping[str, Any],
) -> list[str]:
    structured = _structured_response(
        state
    )

    values: list[str] = []

    explicit_flag = any(
        _normalize_bool(
            candidate
        )
        for candidate in (
            state.get(
                "financial_data_inconsistent"
            ),
            state.get(
                "data_inconsistent"
            ),
            structured.get(
                "financial_data_inconsistent"
            ),
            structured.get(
                "data_inconsistent"
            ),
        )
    )

    for candidate in (
        state.get(
            "data_inconsistencies"
        ),
        state.get(
            "financial_inconsistencies"
        ),
        structured.get(
            "data_inconsistencies"
        ),
        structured.get(
            "financial_inconsistencies"
        ),
    ):
        for item in _normalize_string_list(
            candidate
        ):
            if item not in values:
                values.append(
                    item
                )

    if (
        explicit_flag
        and not values
    ):
        values.append(
            "Foi detectada inconsistência "
            "nos dados financeiros."
        )

    return values


def _external_confirmation_required(
    state: Mapping[str, Any],
) -> bool:
    structured = _structured_response(
        state
    )

    return any(
        _normalize_bool(
            candidate
        )
        for candidate in (
            state.get(
                "external_action_requires_confirmation"
            ),
            state.get(
                "tool_requires_confirmation"
            ),
            state.get(
                "approval_required"
            ),
            structured.get(
                "external_action_requires_confirmation"
            ),
            structured.get(
                "tool_requires_confirmation"
            ),
            structured.get(
                "approval_required"
            ),
        )
    )


def _force_review_required(
    state: Mapping[str, Any],
) -> bool:
    return any(
        _normalize_bool(
            state.get(key)
        )
        for key in (
            "human_review_force_required",
            "force_human_review",
            "manual_review_required",
        )
    )


def _review_disabled(
    state: Mapping[str, Any],
) -> bool:
    explicit = state.get(
        "human_review_enabled"
    )

    if explicit is None:
        return False

    return not _normalize_bool(
        explicit
    )


def _minimum_confidence(
    state: Mapping[str, Any],
) -> float:
    raw = state.get(
        "human_review_minimum_confidence",
        DEFAULT_MINIMUM_CONFIDENCE,
    )

    try:
        value = float(
            raw
        )
    except (
        TypeError,
        ValueError,
    ) as exc:
        raise HumanReviewPolicyError(
            "human_review_minimum_confidence "
            "deve ser numérico."
        ) from exc

    if not math.isfinite(
        value
    ):
        raise HumanReviewPolicyError(
            "human_review_minimum_confidence "
            "deve ser finito."
        )

    if not 0.0 <= value <= 1.0:
        raise HumanReviewPolicyError(
            "human_review_minimum_confidence "
            "deve estar entre 0 e 1."
        )

    return value


def _base_payload(
    state: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "thread_id": _normalize_text(
            state.get(
                "thread_id"
            )
        ),
        "user_id": _normalize_text(
            state.get(
                "user_id"
            )
        ),
        "intent": _normalize_text(
            state.get(
                "intent"
            )
        ),
        "current_agent": (
            _resolve_current_agent(
                state
            )
        ),
        "task_status": _normalize_text(
            state.get(
                "task_status"
            )
        ),
        "task_completion_score": (
            state.get(
                "task_completion_score"
            )
        ),
        "risk_level": (
            _resolve_risk_level(
                state
            )
        ),
        "confidence": (
            _resolve_confidence(
                state
            )
        ),
        "missing_requirements": (
            _resolve_missing_requirements(
                state
            )
        ),
        "data_inconsistencies": (
            _resolve_inconsistencies(
                state
            )
        ),
    }


def _decision(
    *,
    state: Mapping[str, Any],
    requires_review: bool,
    trigger: str,
    reason: str,
    risk_level: HumanReviewRiskLevel,
    metadata: Mapping[str, Any] | None = None,
) -> HumanReviewPolicyDecision:
    return HumanReviewPolicyDecision(
        requires_review=requires_review,
        trigger=trigger,
        reason=reason,
        risk_level=risk_level,
        requested_by=(
            _resolve_current_agent(
                state
            )
        ),
        payload=_base_payload(
            state
        ),
        metadata={
            "policy": (
                "default_financial_human_review"
            ),
            "policy_version": "1.1",
            **dict(
                metadata or {}
            ),
        },
    )


def evaluate_human_review_policy(
    state: Mapping[str, Any],
) -> HumanReviewPolicyDecision:
    """
    Avalia se o estado requer intervenção humana.

    A política é determinística e não possui efeitos
    colaterais. Isso permite executá-la com segurança
    antes de um interrupt do LangGraph.
    """
    if not isinstance(
        state,
        Mapping,
    ):
        raise HumanReviewPolicyError(
            "state deve implementar Mapping."
        )

    existing_status = (
        _resolve_existing_review_status(
            state
        )
    )

    if (
        existing_status
        in _REVIEW_PENDING_STATUSES
    ):
        return _decision(
            state=state,
            requires_review=False,
            trigger="review_already_pending",
            reason=(
                "Já existe uma revisão humana "
                "pendente para esta execução."
            ),
            risk_level=(
                _resolve_risk_level(
                    state
                )
            ),
            metadata={
                "existing_review_status": (
                    existing_status
                ),
            },
        )

    if (
        existing_status
        in _TERMINAL_REVIEW_STATUSES
    ):
        return _decision(
            state=state,
            requires_review=False,
            trigger="review_already_resolved",
            reason=(
                "A revisão humana atual já foi "
                "resolvida."
            ),
            risk_level=(
                _resolve_risk_level(
                    state
                )
            ),
            metadata={
                "existing_review_status": (
                    existing_status
                ),
            },
        )

    risk_level = _resolve_risk_level(
        state
    )

    if _force_review_required(
        state
    ):
        return _decision(
            state=state,
            requires_review=True,
            trigger="forced_review",
            reason=(
                "A revisão humana foi exigida "
                "explicitamente."
            ),
            risk_level=max(
                risk_level,
                "medium",
                key=(
                    "low",
                    "medium",
                    "high",
                    "critical",
                ).index,
            ),
        )

    if _external_confirmation_required(
        state
    ):
        return _decision(
            state=state,
            requires_review=True,
            trigger=(
                "external_action_confirmation"
            ),
            reason=(
                "Uma ferramenta ou ação externa "
                "exige confirmação humana."
            ),
            risk_level=max(
                risk_level,
                "high",
                key=(
                    "low",
                    "medium",
                    "high",
                    "critical",
                ).index,
            ),
        )

    # Risco crítico é uma barreira de segurança.
    # Uma flag operacional comum não pode removê-la.
    if risk_level == "critical":
        return _decision(
            state=state,
            requires_review=True,
            trigger="critical_financial_risk",
            reason=(
                "Foi identificado risco financeiro "
                "crítico."
            ),
            risk_level="critical",
            metadata={
                "mandatory_review": True,
            },
        )

    # A flag continua válida para fluxos que não
    # representam barreiras obrigatórias.
    if _review_disabled(
        state
    ):
        return _decision(
            state=state,
            requires_review=False,
            trigger="policy_disabled",
            reason=(
                "A política de revisão humana está "
                "desativada para esta execução."
            ),
            risk_level=risk_level,
        )

    if risk_level == "high":
        return _decision(
            state=state,
            requires_review=True,
            trigger="high_financial_risk",
            reason=(
                "Foi identificado risco financeiro "
                "elevado."
            ),
            risk_level="high",
        )

    inconsistencies = (
        _resolve_inconsistencies(
            state
        )
    )

    if inconsistencies:
        return _decision(
            state=state,
            requires_review=True,
            trigger=(
                "financial_data_inconsistency"
            ),
            reason=(
                "Os dados financeiros apresentam "
                "inconsistências que precisam ser "
                "confirmadas."
            ),
            risk_level=max(
                risk_level,
                "high",
                key=(
                    "low",
                    "medium",
                    "high",
                    "critical",
                ).index,
            ),
            metadata={
                "inconsistency_count": len(
                    inconsistencies
                ),
            },
        )

    missing_requirements = (
        _resolve_missing_requirements(
            state
        )
    )

    if missing_requirements:
        return _decision(
            state=state,
            requires_review=True,
            trigger=(
                "missing_required_financial_data"
            ),
            reason=(
                "Existem dados obrigatórios "
                "ausentes para concluir a análise."
            ),
            risk_level=max(
                risk_level,
                "medium",
                key=(
                    "low",
                    "medium",
                    "high",
                    "critical",
                ).index,
            ),
            metadata={
                "missing_requirement_count": len(
                    missing_requirements
                ),
            },
        )

    confidence = _resolve_confidence(
        state
    )

    minimum_confidence = (
        _minimum_confidence(
            state
        )
    )

    if (
        confidence is not None
        and confidence
        < minimum_confidence
    ):
        return _decision(
            state=state,
            requires_review=True,
            trigger="low_confidence",
            reason=(
                "A confiança da análise está abaixo "
                "do limite permitido."
            ),
            risk_level=max(
                risk_level,
                "medium",
                key=(
                    "low",
                    "medium",
                    "high",
                    "critical",
                ).index,
            ),
            metadata={
                "confidence": confidence,
                "minimum_confidence": (
                    minimum_confidence
                ),
            },
        )

    return _decision(
        state=state,
        requires_review=False,
        trigger="not_required",
        reason=(
            "Nenhuma condição da política exige "
            "revisão humana."
        ),
        risk_level=risk_level,
        metadata={
            "confidence": confidence,
            "minimum_confidence": (
                minimum_confidence
            ),
        },
    )


def human_review_required(
    state: Mapping[str, Any],
) -> bool:
    return (
        evaluate_human_review_policy(
            state
        ).requires_review
    )


__all__ = [
    "DEFAULT_MINIMUM_CONFIDENCE",
    "HumanReviewPolicyDecision",
    "HumanReviewPolicyError",
    "evaluate_human_review_policy",
    "human_review_required",
]
