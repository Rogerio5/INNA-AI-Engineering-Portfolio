from __future__ import annotations

import inspect
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from importlib import import_module
from importlib.metadata import (
    PackageNotFoundError,
    version,
)
from types import MappingProxyType
from typing import Any

from inna_ai.evaluation.contracts import ConversationTurn, InnaEvaluationCase, PrivacyLevel
from inna_ai.evaluation.privacy import prepare_external_payload

DEEPEVAL_PACKAGE_NAME = "deepeval"

DEEPEVAL_ENABLED_ENV = "INNA_DEEPEVAL_ENABLED"
DEEPEVAL_LIVE_ENV = "INNA_DEEPEVAL_LIVE"
DEEPEVAL_EXTERNAL_ONLY_ENV = (
    "INNA_DEEPEVAL_EXTERNAL_ONLY"
)

_TRUE_VALUES = frozenset(
    {
        "1",
        "true",
        "yes",
        "sim",
        "on",
        "enabled",
    }
)

_FALSE_VALUES = frozenset(
    {
        "0",
        "false",
        "no",
        "nao",
        "não",
        "off",
        "disabled",
        "",
    }
)


class DeepEvalIntegrationError(RuntimeError):
    """Erro base da integração da INNA com DeepEval."""


class DeepEvalUnavailableError(
    DeepEvalIntegrationError
):
    """DeepEval não está disponível no ambiente."""


class DeepEvalPrivacyError(
    DeepEvalIntegrationError
):
    """Um caso não está autorizado para avaliação externa."""


class DeepEvalConfigurationError(
    DeepEvalIntegrationError
):
    """Configuração inválida da integração."""


@dataclass(frozen=True, slots=True)
class DeepEvalSettings:
    """
    Configuração segura da integração.

    A integração e as chamadas live permanecem desativadas
    até serem explicitamente habilitadas.
    """

    enabled: bool = False
    live_enabled: bool = False
    external_only: bool = True

    @classmethod
    def from_environment(
        cls,
        environment: Mapping[str, str] | None = None,
    ) -> DeepEvalSettings:
        values = (
            os.environ
            if environment is None
            else environment
        )

        return cls(
            enabled=_parse_environment_bool(
                values.get(DEEPEVAL_ENABLED_ENV),
                default=False,
                variable_name=DEEPEVAL_ENABLED_ENV,
            ),
            live_enabled=_parse_environment_bool(
                values.get(DEEPEVAL_LIVE_ENV),
                default=False,
                variable_name=DEEPEVAL_LIVE_ENV,
            ),
            external_only=_parse_environment_bool(
                values.get(
                    DEEPEVAL_EXTERNAL_ONLY_ENV
                ),
                default=True,
                variable_name=(
                    DEEPEVAL_EXTERNAL_ONLY_ENV
                ),
            ),
        )

    def require_enabled(self) -> None:
        if not self.enabled:
            raise DeepEvalConfigurationError(
                "A integração DeepEval está desativada. "
                f"Defina {DEEPEVAL_ENABLED_ENV}=1."
            )

    def require_live_enabled(self) -> None:
        self.require_enabled()

        if not self.live_enabled:
            raise DeepEvalConfigurationError(
                "Avaliações DeepEval live estão "
                "desativadas. Defina "
                f"{DEEPEVAL_LIVE_ENV}=1."
            )


@dataclass(frozen=True, slots=True)
class DeepEvalAvailability:
    installed: bool
    package_version: str | None
    llm_test_case_available: bool
    evaluate_available: bool
    error: str | None = None

    @property
    def ready(self) -> bool:
        return (
            self.installed
            and self.llm_test_case_available
            and self.evaluate_available
            and self.error is None
        )


@dataclass(frozen=True, slots=True)
class DeepEvalCasePayload:
    """
    Representação neutra anterior à criação do LLMTestCase.

    Permite testar toda a conversão sem executar métricas ou
    chamadas externas.
    """

    case_id: str
    input_text: str
    actual_output: str
    expected_output: str | None = None
    context: tuple[str, ...] = ()
    retrieval_context: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(
        default_factory=dict
    )

    def __post_init__(self) -> None:
        case_id = self.case_id.strip()
        input_text = self.input_text.strip()
        actual_output = self.actual_output.strip()

        if not case_id:
            raise ValueError(
                "DeepEvalCasePayload.case_id "
                "não pode ser vazio."
            )

        if not input_text:
            raise ValueError(
                "DeepEvalCasePayload.input_text "
                "não pode ser vazio."
            )

        if not actual_output:
            raise ValueError(
                "DeepEvalCasePayload.actual_output "
                "não pode ser vazio."
            )

        object.__setattr__(
            self,
            "case_id",
            case_id,
        )
        object.__setattr__(
            self,
            "input_text",
            input_text,
        )
        object.__setattr__(
            self,
            "actual_output",
            actual_output,
        )
        object.__setattr__(
            self,
            "expected_output",
            _optional_text(
                self.expected_output
            ),
        )
        object.__setattr__(
            self,
            "context",
            _normalize_text_sequence(
                self.context
            ),
        )
        object.__setattr__(
            self,
            "retrieval_context",
            _normalize_text_sequence(
                self.retrieval_context
            ),
        )
        object.__setattr__(
            self,
            "metadata",
            MappingProxyType(
                dict(self.metadata)
            ),
        )


@dataclass(frozen=True, slots=True)
class DeepEvalConversion:
    case_id: str
    payload: DeepEvalCasePayload
    llm_test_case: Any
    deepeval_version: str
    external_run: bool


def _parse_environment_bool(
    value: str | None,
    *,
    default: bool,
    variable_name: str,
) -> bool:
    if value is None:
        return default

    normalized = value.strip().casefold()

    if normalized in _TRUE_VALUES:
        return True

    if normalized in _FALSE_VALUES:
        return False

    raise DeepEvalConfigurationError(
        f"{variable_name} possui valor booleano "
        f"inválido: {value!r}."
    )


def _optional_text(
    value: Any,
) -> str | None:
    if value is None:
        return None

    normalized = str(value).strip()

    return normalized or None


def _normalize_text_sequence(
    values: Sequence[Any] | None,
) -> tuple[str, ...]:
    if values is None:
        return ()

    if isinstance(
        values,
        (
            str,
            bytes,
            bytearray,
        ),
    ):
        raise ValueError(
            "Era esperada uma sequência de textos, "
            "não uma string isolada."
        )

    normalized: list[str] = []

    for value in values:
        text = str(value).strip()

        if text and text not in normalized:
            normalized.append(text)

    return tuple(normalized)


def deepeval_availability() -> DeepEvalAvailability:
    try:
        package_version = version(
            DEEPEVAL_PACKAGE_NAME
        )
    except PackageNotFoundError:
        return DeepEvalAvailability(
            installed=False,
            package_version=None,
            llm_test_case_available=False,
            evaluate_available=False,
            error="Pacote deepeval não instalado.",
        )

    try:
        test_case_module = import_module(
            "deepeval.test_case"
        )
        deepeval_module = import_module(
            "deepeval"
        )

        llm_test_case_available = hasattr(
            test_case_module,
            "LLMTestCase",
        )
        evaluate_available = hasattr(
            deepeval_module,
            "evaluate",
        )

        error = None

        if not llm_test_case_available:
            error = (
                "deepeval.test_case.LLMTestCase "
                "não está disponível."
            )
        elif not evaluate_available:
            error = (
                "deepeval.evaluate não está disponível."
            )

        return DeepEvalAvailability(
            installed=True,
            package_version=package_version,
            llm_test_case_available=(
                llm_test_case_available
            ),
            evaluate_available=evaluate_available,
            error=error,
        )
    except Exception as exception:
        return DeepEvalAvailability(
            installed=True,
            package_version=package_version,
            llm_test_case_available=False,
            evaluate_available=False,
            error=(
                f"{type(exception).__name__}: "
                f"{exception}"
            ),
        )


def require_deepeval() -> DeepEvalAvailability:
    availability = deepeval_availability()

    if not availability.ready:
        raise DeepEvalUnavailableError(
            availability.error
            or "DeepEval não está disponível."
        )

    return availability


def _render_conversation_turn(
    turn: ConversationTurn,
) -> str:
    return (
        f"[{turn.turn_index}] "
        f"{turn.role}: {turn.content}"
    )


def render_case_input(
    case: InnaEvaluationCase,
) -> str:
    """
    Constrói a entrada usada no DeepEval.

    Quando o caso contém input_text, ele permanece como entrada
    principal. A conversa é utilizada como contexto adicional.
    """

    if case.input_text.strip():
        return case.input_text.strip()

    rendered = tuple(
        _render_conversation_turn(turn)
        for turn in case.conversation
    )

    if not rendered:
        raise ValueError(
            f"O caso {case.case_id!r} não possui "
            "input_text nem conversation."
        )

    return "\n".join(rendered)


def render_conversation_context(
    case: InnaEvaluationCase,
) -> tuple[str, ...]:
    return tuple(
        _render_conversation_turn(turn)
        for turn in case.conversation
    )


def ensure_external_case_allowed(
    case: InnaEvaluationCase,
) -> None:
    """
    Aplica uma política deny-by-default para provedores externos.
    """

    if not case.external_evaluation_allowed:
        raise DeepEvalPrivacyError(
            f"O caso {case.case_id!r} não está "
            "autorizado para avaliação externa."
        )

    if case.privacy_level is not PrivacyLevel.PUBLIC:
        raise DeepEvalPrivacyError(
            f"O caso {case.case_id!r} não possui "
            "nível de privacidade público."
        )

    if case.metadata.get("synthetic") is not True:
        raise DeepEvalPrivacyError(
            f"O caso {case.case_id!r} não está "
            "marcado como sintético."
        )

    if case.metadata.get("external_safe") is not True:
        raise DeepEvalPrivacyError(
            f"O caso {case.case_id!r} não está "
            "marcado como external_safe."
        )


def build_deepeval_payload(
    case: InnaEvaluationCase,
    *,
    actual_output: str,
    context: Sequence[str] | None = None,
    retrieval_context: Sequence[str] | None = None,
    metadata: Mapping[str, Any] | None = None,
    external_run: bool = False,
) -> DeepEvalCasePayload:
    if external_run:
        ensure_external_case_allowed(case)

    conversation_context = (
        render_conversation_context(case)
    )

    supplied_context = _normalize_text_sequence(
        context
    )

    combined_context = tuple(
        dict.fromkeys(
            (
                *conversation_context,
                *supplied_context,
            )
        )
    )

    supplied_metadata = dict(
        metadata or {}
    )

    case_metadata = {
        "case_id": case.case_id,
        "dataset_name": case.dataset_name,
        "dataset_version": case.dataset_version,
        "case_version": case.case_version,
        "category": case.category,
        "language": case.language,
        "currency": case.currency,
        "privacy_level": (
            case.privacy_level.value
        ),
        "synthetic": (
            case.metadata.get("synthetic")
            is True
        ),
        **supplied_metadata,
    }

    if external_run:
        sanitized_metadata = prepare_external_payload(
            case_metadata
        )

        if not isinstance(
            sanitized_metadata,
            Mapping,
        ):
            raise DeepEvalPrivacyError(
                "A sanitização externa não retornou "
                "um mapping válido."
            )

        case_metadata = dict(
            sanitized_metadata
        )

    return DeepEvalCasePayload(
        case_id=case.case_id,
        input_text=render_case_input(case),
        actual_output=actual_output,
        expected_output=case.expected_output,
        context=combined_context,
        retrieval_context=(
            _normalize_text_sequence(
                retrieval_context
            )
        ),
        metadata=case_metadata,
    )


def _supported_constructor_arguments(
    constructor: Any,
    values: Mapping[str, Any],
) -> dict[str, Any]:
    """
    Filtra argumentos conforme a assinatura instalada.

    Isso protege a INNA contra diferenças compatíveis entre
    versões do DeepEval.
    """

    signature = inspect.signature(
        constructor
    )

    parameters = signature.parameters

    supports_kwargs = any(
        parameter.kind
        is inspect.Parameter.VAR_KEYWORD
        for parameter in parameters.values()
    )

    if supports_kwargs:
        return dict(values)

    return {
        key: value
        for key, value in values.items()
        if key in parameters
    }


def create_llm_test_case(
    payload: DeepEvalCasePayload,
) -> Any:
    availability = require_deepeval()

    test_case_module = import_module(
        "deepeval.test_case"
    )

    llm_test_case_class = test_case_module.LLMTestCase

    candidate_arguments: dict[str, Any] = {
        "input": payload.input_text,
        "actual_output": payload.actual_output,
        "expected_output": (
            payload.expected_output
        ),
        "context": list(payload.context),
        "retrieval_context": list(
            payload.retrieval_context
        ),
        "additional_metadata": dict(
            payload.metadata
        ),
    }

    constructor_arguments = (
        _supported_constructor_arguments(
            llm_test_case_class,
            candidate_arguments,
        )
    )

    required_arguments = {
        "input",
        "actual_output",
    }

    missing_arguments = (
        required_arguments
        - set(constructor_arguments)
    )

    if missing_arguments:
        raise DeepEvalUnavailableError(
            "A versão instalada do DeepEval não "
            "aceita os argumentos obrigatórios: "
            f"{sorted(missing_arguments)}."
        )

    test_case = llm_test_case_class(
        **constructor_arguments
    )

    if availability.package_version is None:
        raise DeepEvalUnavailableError(
            "Não foi possível identificar a versão "
            "instalada do DeepEval."
        )

    return test_case


def convert_case_to_deepeval(
    case: InnaEvaluationCase,
    *,
    actual_output: str,
    context: Sequence[str] | None = None,
    retrieval_context: Sequence[str] | None = None,
    metadata: Mapping[str, Any] | None = None,
    external_run: bool = False,
) -> DeepEvalConversion:
    availability = require_deepeval()

    payload = build_deepeval_payload(
        case,
        actual_output=actual_output,
        context=context,
        retrieval_context=retrieval_context,
        metadata=metadata,
        external_run=external_run,
    )

    llm_test_case = create_llm_test_case(
        payload
    )

    if availability.package_version is None:
        raise DeepEvalUnavailableError(
            "Versão do DeepEval indisponível."
        )

    return DeepEvalConversion(
        case_id=case.case_id,
        payload=payload,
        llm_test_case=llm_test_case,
        deepeval_version=(
            availability.package_version
        ),
        external_run=external_run,
    )


__all__ = [
    "DEEPEVAL_ENABLED_ENV",
    "DEEPEVAL_EXTERNAL_ONLY_ENV",
    "DEEPEVAL_LIVE_ENV",
    "DeepEvalAvailability",
    "DeepEvalCasePayload",
    "DeepEvalConfigurationError",
    "DeepEvalConversion",
    "DeepEvalIntegrationError",
    "DeepEvalPrivacyError",
    "DeepEvalSettings",
    "DeepEvalUnavailableError",
    "build_deepeval_payload",
    "convert_case_to_deepeval",
    "create_llm_test_case",
    "deepeval_availability",
    "ensure_external_case_allowed",
    "render_case_input",
    "render_conversation_context",
    "require_deepeval",
]
