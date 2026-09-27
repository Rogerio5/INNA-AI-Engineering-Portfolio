"""Shared Blackboard governado da arquitetura multiagente INNA."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from typing import Any, Literal

BLACKBOARD_SCHEMA_VERSION = "1.0.0"

DEFAULT_MAX_BLACKBOARD_ENTRIES = 64
DEFAULT_MAX_BLACKBOARD_PAYLOAD_BYTES = 8192

BlackboardEntryKind = Literal[
    "fact",
    "result",
    "decision",
    "evidence",
]

BlackboardVisibility = Literal[
    "workflow",
    "team",
]

_ALLOWED_ENTRY_KINDS = frozenset(
    {
        "fact",
        "result",
        "decision",
        "evidence",
    }
)

_ALLOWED_VISIBILITIES = frozenset(
    {
        "workflow",
        "team",
    }
)

_BLOCKED_STATE_FIELDS = frozenset(
    {
        "user_message",
        "conversation_history",
        "conversation_summary",
        "rendered_prompt",
        "raw_prompt",
        "prompt",
        "api_key",
        "password",
        "secret",
        "token",
        "authorization",
        "cookie",
        "response",
    }
)


@dataclass(
    frozen=True,
    slots=True,
)
class BlackboardEntry:
    """Registro imutável compartilhado pelo workflow."""

    schema_version: str
    entry_id: str
    kind: BlackboardEntryKind
    producer: str
    visibility: BlackboardVisibility
    team: str | None
    payload: dict[str, Any]

    def model_dump(
        self,
    ) -> dict[str, Any]:
        return asdict(self)


@dataclass(
    frozen=True,
    slots=True,
)
class BlackboardPublishResult:
    """Resultado de uma tentativa governada de publicação."""

    accepted: bool
    reason: str
    entry: BlackboardEntry | None
    entries: tuple[BlackboardEntry, ...]


def _normalize_text(
    value: Any,
) -> str:
    return str(
        value or ""
    ).strip()


def _normalize_field_name(
    value: Any,
) -> str:
    return (
        _normalize_text(
            value
        )
        .lower()
        .replace(
            "-",
            "_",
        )
        .replace(
            " ",
            "_",
        )
    )


def _contains_blocked_field(
    value: Any,
) -> bool:
    if isinstance(
        value,
        Mapping,
    ):
        for key, nested in value.items():
            if (
                _normalize_field_name(
                    key
                )
                in _BLOCKED_STATE_FIELDS
            ):
                return True

            if _contains_blocked_field(
                nested
            ):
                return True

        return False

    if isinstance(
        value,
        Sequence,
    ) and not isinstance(
        value,
        (
            str,
            bytes,
            bytearray,
        ),
    ):
        return any(
            _contains_blocked_field(
                item
            )
            for item in value
        )

    return False


def _normalize_payload(
    payload: Mapping[str, Any],
) -> tuple[
    dict[str, Any] | None,
    str | None,
]:
    if _contains_blocked_field(
        payload
    ):
        return (
            None,
            "blackboard_payload_contains_blocked_field",
        )

    try:
        serialized = json.dumps(
            dict(payload),
            ensure_ascii=False,
            sort_keys=True,
            separators=(
                ",",
                ":",
            ),
            allow_nan=False,
        )
    except (
        TypeError,
        ValueError,
    ):
        return (
            None,
            "blackboard_payload_not_json_serializable",
        )

    size = len(
        serialized.encode(
            "utf-8"
        )
    )

    if (
        size
        > DEFAULT_MAX_BLACKBOARD_PAYLOAD_BYTES
    ):
        return (
            None,
            "blackboard_payload_too_large",
        )

    normalized = json.loads(
        serialized
    )

    if not isinstance(
        normalized,
        dict,
    ):
        return (
            None,
            "blackboard_payload_invalid",
        )

    return (
        normalized,
        None,
    )


def _build_entry_id(
    *,
    kind: BlackboardEntryKind,
    producer: str,
    visibility: BlackboardVisibility,
    team: str | None,
    payload: dict[str, Any],
) -> str:
    canonical = json.dumps(
        {
            "schema_version": (
                BLACKBOARD_SCHEMA_VERSION
            ),
            "kind": kind,
            "producer": producer,
            "visibility": visibility,
            "team": team,
            "payload": payload,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(
            ",",
            ":",
        ),
        allow_nan=False,
    )

    digest = hashlib.sha256(
        canonical.encode(
            "utf-8"
        )
    ).hexdigest()

    return (
        "bb_"
        + digest[:24]
    )


def publish_blackboard_entry(
    *,
    current_entries: Sequence[BlackboardEntry],
    kind: BlackboardEntryKind,
    producer: str,
    visibility: BlackboardVisibility,
    payload: Mapping[str, Any],
    team: str | None = None,
    max_entries: int = DEFAULT_MAX_BLACKBOARD_ENTRIES,
) -> BlackboardPublishResult:
    """
    Publica informação operacional no Blackboard.

    O contrato não copia o InnaAgentState. O produtor deve
    fornecer somente o payload operacional necessário.
    """

    if kind not in _ALLOWED_ENTRY_KINDS:
        return BlackboardPublishResult(
            accepted=False,
            reason="blackboard_invalid_entry_kind",
            entry=None,
            entries=tuple(
                current_entries
            ),
        )

    if visibility not in _ALLOWED_VISIBILITIES:
        return BlackboardPublishResult(
            accepted=False,
            reason="blackboard_invalid_visibility",
            entry=None,
            entries=tuple(
                current_entries
            ),
        )

    normalized_producer = (
        _normalize_text(
            producer
        )
    )

    normalized_team = (
        _normalize_text(
            team
        )
        or None
    )

    if not normalized_producer:
        return BlackboardPublishResult(
            accepted=False,
            reason="blackboard_producer_required",
            entry=None,
            entries=tuple(
                current_entries
            ),
        )

    if (
        visibility == "team"
        and normalized_team is None
    ):
        return BlackboardPublishResult(
            accepted=False,
            reason="blackboard_team_required",
            entry=None,
            entries=tuple(
                current_entries
            ),
        )

    if isinstance(
        max_entries,
        bool,
    ):
        return BlackboardPublishResult(
            accepted=False,
            reason="blackboard_invalid_entry_budget",
            entry=None,
            entries=tuple(
                current_entries
            ),
        )

    try:
        normalized_max_entries = int(
            max_entries
        )
    except (
        TypeError,
        ValueError,
    ):
        normalized_max_entries = 0

    if normalized_max_entries < 1:
        return BlackboardPublishResult(
            accepted=False,
            reason="blackboard_invalid_entry_budget",
            entry=None,
            entries=tuple(
                current_entries
            ),
        )

    normalized_payload, error = (
        _normalize_payload(
            payload
        )
    )

    if (
        error is not None
        or normalized_payload is None
    ):
        return BlackboardPublishResult(
            accepted=False,
            reason=(
                error
                or "blackboard_payload_invalid"
            ),
            entry=None,
            entries=tuple(
                current_entries
            ),
        )

    entry = BlackboardEntry(
        schema_version=(
            BLACKBOARD_SCHEMA_VERSION
        ),
        entry_id=_build_entry_id(
            kind=kind,
            producer=normalized_producer,
            visibility=visibility,
            team=normalized_team,
            payload=normalized_payload,
        ),
        kind=kind,
        producer=normalized_producer,
        visibility=visibility,
        team=normalized_team,
        payload=normalized_payload,
    )

    existing = tuple(
        current_entries
    )

    for current in existing:
        if (
            current.entry_id
            == entry.entry_id
        ):
            return BlackboardPublishResult(
                accepted=True,
                reason=(
                    "blackboard_entry_deduplicated"
                ),
                entry=current,
                entries=existing,
            )

    if (
        len(existing)
        >= normalized_max_entries
    ):
        return BlackboardPublishResult(
            accepted=False,
            reason=(
                "blackboard_entry_budget_exceeded"
            ),
            entry=None,
            entries=existing,
        )

    return BlackboardPublishResult(
        accepted=True,
        reason="blackboard_entry_published",
        entry=entry,
        entries=(
            *existing,
            entry,
        ),
    )


def can_read_blackboard_entry(
    entry: BlackboardEntry,
    *,
    consumer_team: str | None,
) -> bool:
    """Aplica a visibilidade mínima do registro."""

    if (
        entry.visibility
        not in _ALLOWED_VISIBILITIES
    ):
        return False

    if (
        entry.visibility
        == "workflow"
    ):
        return True

    normalized_consumer_team = (
        _normalize_text(
            consumer_team
        )
    )

    return bool(
        normalized_consumer_team
        and entry.team
        == normalized_consumer_team
    )


def read_blackboard_entries(
    entries: Sequence[BlackboardEntry],
    *,
    consumer_team: str | None,
    kinds: Sequence[BlackboardEntryKind]
    | None = None,
) -> tuple[BlackboardEntry, ...]:
    """Retorna somente registros visíveis ao consumidor."""

    allowed_kinds = (
        set(kinds)
        if kinds is not None
        else None
    )

    return tuple(
        entry
        for entry in entries
        if (
            can_read_blackboard_entry(
                entry,
                consumer_team=consumer_team,
            )
            and (
                allowed_kinds is None
                or entry.kind
                in allowed_kinds
            )
        )
    )


__all__ = [
    "BLACKBOARD_SCHEMA_VERSION",
    "DEFAULT_MAX_BLACKBOARD_ENTRIES",
    "DEFAULT_MAX_BLACKBOARD_PAYLOAD_BYTES",
    "BlackboardEntry",
    "BlackboardEntryKind",
    "BlackboardPublishResult",
    "BlackboardVisibility",
    "can_read_blackboard_entry",
    "publish_blackboard_entry",
    "read_blackboard_entries",
]
