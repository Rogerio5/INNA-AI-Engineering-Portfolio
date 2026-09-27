from __future__ import annotations

import asyncio
import subprocess
from collections.abc import Iterator
from typing import Any

from inna_ai.resilience.contracts import FailureKind

_TIMEOUT_NAMES = {
    "timeouterror",
    "timeout",
    "readtimeout",
    "connecttimeout",
    "writeerror",
    "deadlineexceeded",
    "timeoutexpired",
}

_RATE_LIMIT_NAMES = {
    "ratelimiterror",
    "toomanyrequests",
    "resourceexhausted",
}

_NETWORK_NAMES = {
    "connectionerror",
    "connecterror",
    "networkerror",
    "connectionreseterror",
    "connectionabortederror",
    "remotedisconnected",
}

_UPSTREAM_NAMES = {
    "serviceunavailable",
    "badgateway",
    "gatewaytimeout",
    "internalservererror",
}


def _iter_exception_chain(
    exc: BaseException,
) -> Iterator[BaseException]:
    current: BaseException | None = exc
    visited: set[int] = set()

    for _ in range(8):
        if current is None:
            return

        identity = id(current)

        if identity in visited:
            return

        visited.add(identity)
        yield current

        current = (
            current.__cause__
            or current.__context__
        )


def _extract_status_code(
    exc: BaseException,
) -> int | None:
    candidates: list[Any] = [
        getattr(exc, "status_code", None),
        getattr(exc, "code", None),
        getattr(exc, "status", None),
        getattr(exc, "http_status", None),
    ]

    response = getattr(
        exc,
        "response",
        None,
    )

    if response is not None:
        candidates.extend(
            [
                getattr(
                    response,
                    "status_code",
                    None,
                ),
                getattr(
                    response,
                    "status",
                    None,
                ),
            ]
        )

    for candidate in candidates:
        try:
            if candidate is None:
                continue

            return int(candidate)
        except (
            TypeError,
            ValueError,
        ):
            continue

    return None


def _classify_single(
    exc: BaseException,
) -> FailureKind:
    declared_failure_kind = getattr(
        exc,
        "failure_kind",
        None,
    )

    if isinstance(
        declared_failure_kind,
        FailureKind,
    ):
        return declared_failure_kind

    if isinstance(
        exc,
        asyncio.CancelledError,
    ):
        return FailureKind.CANCELLED

    if isinstance(
        exc,
        (
            TimeoutError,
            subprocess.TimeoutExpired,
        ),
    ):
        return FailureKind.TIMEOUT

    if isinstance(
        exc,
        ConnectionError,
    ):
        return FailureKind.TRANSIENT_NETWORK

    name = type(exc).__name__.lower()

    if name in _TIMEOUT_NAMES:
        return FailureKind.TIMEOUT

    if name in _RATE_LIMIT_NAMES:
        return FailureKind.RATE_LIMIT

    if name in _NETWORK_NAMES:
        return FailureKind.TRANSIENT_NETWORK

    if name in _UPSTREAM_NAMES:
        return FailureKind.UPSTREAM_5XX

    status_code = _extract_status_code(
        exc
    )

    if status_code in {
        408,
        504,
    }:
        return FailureKind.TIMEOUT

    if status_code == 429:
        return FailureKind.RATE_LIMIT

    if (
        status_code is not None
        and 500 <= status_code <= 599
    ):
        return FailureKind.UPSTREAM_5XX

    if status_code in {
        401,
        407,
    }:
        return FailureKind.AUTHENTICATION

    if status_code == 403:
        return FailureKind.AUTHORIZATION

    if (
        status_code is not None
        and 400 <= status_code <= 499
    ):
        return FailureKind.INVALID_REQUEST

    if (
        "configuration" in name
        or "configerror" in name
    ):
        return FailureKind.CONFIGURATION

    if isinstance(
        exc,
        (
            TypeError,
            ValueError,
        ),
    ):
        return FailureKind.VALIDATION

    return FailureKind.UNKNOWN


def classify_failure(
    exc: BaseException,
) -> FailureKind:
    for candidate in _iter_exception_chain(
        exc
    ):
        kind = _classify_single(
            candidate
        )

        if kind is not FailureKind.UNKNOWN:
            return kind

    return FailureKind.UNKNOWN
