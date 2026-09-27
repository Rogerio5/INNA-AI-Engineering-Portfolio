"""Runtime governado do Shared Blackboard da INNA."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, cast

from inna_ai.governance.blackboard.permissions import evaluate_blackboard_publish, evaluate_blackboard_read
from inna_ai.governance.blackboard.models import BLACKBOARD_SCHEMA_VERSION, DEFAULT_MAX_BLACKBOARD_ENTRIES, BlackboardEntry, BlackboardEntryKind, BlackboardVisibility, publish_blackboard_entry


@dataclass(
    frozen=True,
    slots=True,
)
class BlackboardReadResult:
    """Resultado seguro de leitura do Blackboard."""

    entries: tuple[BlackboardEntry, ...]
    rejected_entries: int


def _normalize_text(
    value: Any,
) -> str:
    return str(
        value or ""
    ).strip()


def _entry_from_state(
    value: Any,
) -> BlackboardEntry | None:
    """
    Reconstrói e valida um registro serializado.

    O entry_id também é recalculado para detectar alteração
    do conteúdo armazenado no estado.
    """

    if not isinstance(
        value,
        Mapping,
    ):
        return None

    if (
        value.get(
            "schema_version"
        )
        != BLACKBOARD_SCHEMA_VERSION
    ):
        return None

    payload = value.get(
        "payload"
    )

    if not isinstance(
        payload,
        Mapping,
    ):
        return None

    kind = _normalize_text(
        value.get(
            "kind"
        )
    )

    visibility = _normalize_text(
        value.get(
            "visibility"
        )
    )

    producer = _normalize_text(
        value.get(
            "producer"
        )
    )

    team_value = _normalize_text(
        value.get(
            "team"
        )
    )

    team = (
        team_value
        or None
    )

    canonical = publish_blackboard_entry(
        current_entries=(),
        kind=cast(
            BlackboardEntryKind,
            kind,
        ),
        producer=producer,
        visibility=cast(
            BlackboardVisibility,
            visibility,
        ),
        team=team,
        payload=payload,
    )

    if (
        not canonical.accepted
        or canonical.entry is None
    ):
        return None

    stored_entry_id = _normalize_text(
        value.get(
            "entry_id"
        )
    )

    if (
        canonical.entry.entry_id
        != stored_entry_id
    ):
        return None

    return canonical.entry


def load_shared_blackboard(
    state: Mapping[str, Any],
) -> tuple[
    tuple[BlackboardEntry, ...],
    int,
]:
    """Carrega somente registros estruturalmente válidos."""

    raw_entries = state.get(
        "shared_blackboard_entries",
        [],
    )

    if not isinstance(
        raw_entries,
        Sequence,
    ) or isinstance(
        raw_entries,
        (
            str,
            bytes,
            bytearray,
        ),
    ):
        return (
            (),
            1,
        )

    valid: list[BlackboardEntry] = []
    rejected = 0

    for raw_entry in raw_entries:
        entry = _entry_from_state(
            raw_entry
        )

        if entry is None:
            rejected += 1
            continue

        valid.append(
            entry
        )

    return (
        tuple(valid),
        rejected,
    )


def _serialize_entries(
    entries: Sequence[BlackboardEntry],
) -> list[dict[str, Any]]:
    return [
        entry.model_dump()
        for entry in entries
    ]


def _max_entries_from_state(
    state: Mapping[str, Any],
) -> int:
    value = state.get(
        "max_shared_blackboard_entries",
        DEFAULT_MAX_BLACKBOARD_ENTRIES,
    )

    if isinstance(
        value,
        bool,
    ):
        return 0

    try:
        normalized = int(
            value
        )
    except (
        TypeError,
        ValueError,
    ):
        return 0

    return normalized


def _append_audit(
    state: Mapping[str, Any],
    *,
    principal: str,
    action: str,
    allowed: bool,
    reason: str,
    kind: str | None = None,
    visibility: str | None = None,
    team: str | None = None,
    entry_id: str | None = None,
) -> list[dict[str, Any]]:
    """
    Auditoria propositalmente não inclui payload,
    mensagem, resposta ou contexto.
    """

    existing = state.get(
        "shared_blackboard_audit",
        [],
    )

    audit = [
        dict(item)
        for item in existing
        if isinstance(
            item,
            Mapping,
        )
    ]

    audit.append(
        {
            "principal": principal,
            "action": action,
            "allowed": allowed,
            "reason": reason,
            "kind": kind,
            "visibility": visibility,
            "team": team,
            "entry_id": entry_id,
        }
    )

    # Evita crescimento indefinido do estado operacional.
    return audit[-128:]


def _trace(
    state: Mapping[str, Any],
    *,
    action: str,
    reason: str,
) -> list[str]:
    trace = [
        str(item)
        for item in state.get(
            "trace",
            [],
        )
    ]

    trace.append(
        
            "shared_blackboard:"
            f"{action}:"
            f"{reason}"
        
    )

    return trace


def publish_shared_blackboard(
    state: Mapping[str, Any],
    *,
    principal: str,
    kind: BlackboardEntryKind,
    visibility: BlackboardVisibility,
    payload: Mapping[str, Any],
    team: str | None = None,
) -> dict[str, Any]:
    """
    Publica após validar estado, ACL e contrato.

    Retorna somente campos que devem atualizar
    o InnaAgentState.
    """

    normalized_principal = (
        _normalize_text(
            principal
        )
    )

    entries, rejected = (
        load_shared_blackboard(
            state
        )
    )

    if rejected:
        reason = (
            "blackboard_existing_state_invalid"
        )

        decision = {
            "allowed": False,
            "reason": reason,
            "principal": normalized_principal,
            "action": "publish",
        }

        return {
            "shared_blackboard_last_decision": (
                decision
            ),
            "shared_blackboard_audit": (
                _append_audit(
                    state,
                    principal=normalized_principal,
                    action="publish",
                    allowed=False,
                    reason=reason,
                    kind=str(kind),
                    visibility=str(
                        visibility
                    ),
                    team=team,
                )
            ),
            "trace": _trace(
                state,
                action="publish",
                reason=reason,
            ),
        }

    permission = (
        evaluate_blackboard_publish(
            principal=normalized_principal,
            kind=kind,
            visibility=visibility,
            team=team,
        )
    )

    if not permission.allowed:
        decision = {
            "allowed": False,
            "reason": permission.reason,
            "principal": normalized_principal,
            "action": "publish",
        }

        return {
            "shared_blackboard_last_decision": (
                decision
            ),
            "shared_blackboard_audit": (
                _append_audit(
                    state,
                    principal=normalized_principal,
                    action="publish",
                    allowed=False,
                    reason=permission.reason,
                    kind=str(kind),
                    visibility=str(
                        visibility
                    ),
                    team=team,
                )
            ),
            "trace": _trace(
                state,
                action="publish",
                reason=permission.reason,
            ),
        }

    result = publish_blackboard_entry(
        current_entries=entries,
        kind=kind,
        producer=normalized_principal,
        visibility=visibility,
        team=team,
        payload=payload,
        max_entries=(
            _max_entries_from_state(
                state
            )
        ),
    )

    entry_id = (
        result.entry.entry_id
        if result.entry is not None
        else None
    )

    decision = {
        "allowed": result.accepted,
        "reason": result.reason,
        "principal": normalized_principal,
        "action": "publish",
        "entry_id": entry_id,
    }

    update: dict[str, Any] = {
        "shared_blackboard_last_decision": (
            decision
        ),
        "shared_blackboard_audit": (
            _append_audit(
                state,
                principal=normalized_principal,
                action="publish",
                allowed=result.accepted,
                reason=result.reason,
                kind=str(kind),
                visibility=str(
                    visibility
                ),
                team=team,
                entry_id=entry_id,
            )
        ),
        "trace": _trace(
            state,
            action="publish",
            reason=result.reason,
        ),
    }

    if result.accepted:
        update.update(
            {
                "shared_blackboard_entries": (
                    _serialize_entries(
                        result.entries
                    )
                ),
                "shared_blackboard_count": len(
                    result.entries
                ),
            }
        )

    return update


def read_shared_blackboard(
    state: Mapping[str, Any],
    *,
    principal: str,
    kinds: Sequence[
        BlackboardEntryKind
    ] | None = None,
) -> BlackboardReadResult:
    """Lê somente entradas autorizadas pela ACL."""

    entries, rejected = (
        load_shared_blackboard(
            state
        )
    )

    if rejected:
        return BlackboardReadResult(
            entries=(),
            rejected_entries=rejected,
        )

    allowed_kinds = (
        set(kinds)
        if kinds is not None
        else None
    )

    visible: list[BlackboardEntry] = []

    for entry in entries:
        if (
            allowed_kinds is not None
            and entry.kind
            not in allowed_kinds
        ):
            continue

        permission = evaluate_blackboard_read(
            principal=principal,
            entry=entry,
        )

        if permission.allowed:
            visible.append(
                entry
            )

    return BlackboardReadResult(
        entries=tuple(
            visible
        ),
        rejected_entries=0,
    )


__all__ = [
    "BlackboardReadResult",
    "load_shared_blackboard",
    "publish_shared_blackboard",
    "read_shared_blackboard",
]
