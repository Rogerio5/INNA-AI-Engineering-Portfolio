"""Auditoria privada e rastreável das chamadas MCP."""

from __future__ import annotations

import hashlib
import json
import os
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from inna_ai.observability.audit import record_event

_AUDIT_LOCK = threading.Lock()


def _boolean_environment(
    name: str,
    default: bool = False,
) -> bool:
    value = os.getenv(name)

    if value is None:
        return default

    return value.strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def hash_arguments(
    arguments: dict[str, Any],
) -> str:
    """Gera hash determinístico sem persistir os dados."""

    canonical = json.dumps(
        arguments,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )

    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def registrar_evento_mcp(
    *,
    call_id: str,
    trace_id: str,
    tool_name: str,
    status: str,
    duration_ms: float,
    arguments_hash: str,
    error_code: str | None = None,
    principal: str | None = None,
    event_type: str = "tool_call",
    server_name: str = "inna-mcp-level-2",
    server_version: str = "unknown",
) -> None:
    """Registra somente metadados seguros da execução."""

    event = {
        "timestamp": datetime.now(UTC).isoformat(),
        "server": server_name,
        "server_version": server_version,
        "call_id": call_id,
        "trace_id": trace_id,
        "tool_name": tool_name,
        "event_type": event_type,
        "principal": principal,
        "status": status,
        "duration_ms": round(
            float(duration_ms),
            3,
        ),
        "arguments_sha256": arguments_hash,
        "error_code": error_code,
        "raw_arguments_stored": False,
        "raw_output_stored": False,
    }

    audit_path = Path(
        os.getenv(
            "INNA_MCP_AUDIT_PATH",
            "artifacts/audits/mcp_calls.jsonl",
        )
    )

    audit_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    serialized = json.dumps(
        event,
        ensure_ascii=False,
        sort_keys=True,
    )

    with _AUDIT_LOCK:
        with audit_path.open(
            "a",
            encoding="utf-8",
        ) as file:
            file.write(serialized + "\n")

    if _boolean_environment(
        "INNA_MCP_DB_AUDIT_ENABLED",
        default=False,
    ):
        record_event(
            canal="mcp",
            status=status,
            tempo_resposta_segundos=(float(duration_ms) / 1000),
            metadata=event,
        )
