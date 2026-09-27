from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any


class TruLensBridgeError(RuntimeError):
    """Controlled failure while executing isolated TruLens."""


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _default_trulens_python() -> Path:
    venv_root = _repo_root() / ".venv-trulens"
    candidates = (
        venv_root / "Scripts" / "python.exe",
        venv_root / "bin" / "python",
    )

    for candidate in candidates:
        if candidate.is_file():
            return candidate

    return candidates[0] if os.name == "nt" else candidates[1]


    return (
        _repo_root()
        / ".venv-trulens"
        / "Scripts"
        / "python.exe"
    )


def _runner_path() -> Path:
    return (
        _repo_root()
        / "scripts"
        / "run_trulens_isolated_record.py"
    )


def _parse_result(
    stdout: str,
) -> dict[str, Any]:
    candidates = [
        stdout.strip(),
        *reversed(
            [
                line.strip()
                for line in stdout.splitlines()
                if line.strip()
            ]
        ),
    ]

    for candidate in candidates:
        if not candidate:
            continue

        try:
            result = json.loads(candidate)
        except json.JSONDecodeError:
            continue

        if isinstance(result, dict):
            return result

    raise TruLensBridgeError(
        "isolated TruLens returned invalid JSON"
    )


def run_trulens_record(
    payload: Mapping[str, Any],
    *,
    timeout_seconds: float = 60.0,
    trulens_python: Path | None = None,
    validate_only: bool = False,
) -> dict[str, Any]:
    """Persist an INNA evaluation trace in isolated TruLens."""
    python_path = (
        trulens_python
        or _default_trulens_python()
    )
    runner = _runner_path()

    if not python_path.is_file():
        raise TruLensBridgeError(
            "isolated TruLens Python executable not found"
        )

    if not runner.is_file():
        raise TruLensBridgeError(
            "isolated TruLens runner not found"
        )

    runner_payload = dict(payload)
    runner_payload["execution_mode"] = (
        "validate"
        if validate_only
        else "record"
    )

    serialized = json.dumps(
        runner_payload,
        ensure_ascii=False,
        sort_keys=True,
    )

    temp_directory: Path | None = None
    child_env = {
        **os.environ,
        "PYTHONNOUSERSITE": "1",
    }

    if not validate_only:
        temp_directory = Path(
            tempfile.mkdtemp(
                prefix="inna_trulens_bridge_"
            )
        )
        child_env["INNA_TRULENS_TEMP_DIR"] = str(
            temp_directory
        )

    try:
        completed = subprocess.run(
            [str(python_path), str(runner)],
            input=serialized,
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
            check=False,
            cwd=str(_repo_root()),
            env=child_env,
        )
    finally:
        if temp_directory is not None:
            shutil.rmtree(
                temp_directory,
                ignore_errors=False,
            )

    if completed.returncode != 0:
        result = None

        try:
            result = _parse_result(
                completed.stdout
            )
        except TruLensBridgeError:
            pass

        if result is not None:
            message = str(
                result.get("error")
                or result.get("error_type")
                or (
                    "isolated TruLens "
                    "execution failed"
                )
            )
        else:
            message = (
                completed.stderr.strip()
                or (
                    "isolated TruLens "
                    "execution failed"
                )
            )

        raise TruLensBridgeError(message)

    return _parse_result(
        completed.stdout
    )
