from __future__ import annotations

import inspect
import os
import re
import time
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256
from typing import Any

from inna_ai.retrieval.agentic.planner import create_research_plan
from inna_ai.retrieval.agentic.research_agent import run_research_agent_with_runtime
from inna_ai.retrieval.agentic.synthesizer import synthesize_research_result
from inna_ai.orchestration.nodes import rag_agent_node as legacy_rag_agent_node
from inna_ai.orchestration.contracts import AgentResponse
from inna_ai.orchestration.state import InnaAgentState

AGENTIC_RAG_GATEWAY_VERSION = "7.0.0"

AGENTIC_RAG_MODE_ENV = "INNA_AGENTIC_RAG_MODE"

AGENTIC_RAG_OPERATIONAL_FALLBACK_ENV = "INNA_AGENTIC_RAG_OPERATIONAL_FALLBACK"

AGENTIC_RAG_QUALITY_FALLBACK_ENV = "INNA_AGENTIC_RAG_QUALITY_FALLBACK"

AGENTIC_RAG_SHADOW_SAMPLE_RATE_ENV = "INNA_AGENTIC_RAG_SHADOW_SAMPLE_RATE"

AGENTIC_RAG_ALLOW_PARTIAL_ENV = "INNA_AGENTIC_RAG_ALLOW_PARTIAL"

AGENTIC_RAG_MAX_QUESTION_CHARS_ENV = "INNA_AGENTIC_RAG_MAX_QUESTION_CHARS"


class AgenticRagMode(StrEnum):
    OFF = "off"
    SHADOW = "shadow"
    ACTIVE = "active"


class GatewayDecision(StrEnum):
    LEGACY_OFF = "legacy_off"
    LEGACY_EMPTY_QUESTION = "legacy_empty_question"
    LEGACY_SIMPLE_QUERY = "legacy_simple_query"
    SHADOW_NOT_SELECTED = "shadow_not_selected"
    SHADOW_EXECUTION = "shadow_execution"
    AGENTIC_EXECUTION = "agentic_execution"
    LEGACY_OPERATIONAL_FALLBACK = "legacy_operational_fallback"
    LEGACY_QUALITY_FALLBACK = "legacy_quality_fallback"
    SECURITY_BLOCK = "security_block"


class GatewayOutcome(StrEnum):
    LEGACY = "legacy"
    SHADOW_GROUNDED = "shadow_grounded"
    SHADOW_REJECTED = "shadow_rejected"
    SHADOW_FAILED = "shadow_failed"
    GROUNDED = "grounded"
    PARTIAL = "partial"
    FALLBACK = "fallback"
    BLOCKED = "blocked"


@dataclass(
    frozen=True,
    slots=True,
)
class AgenticRagGatewayConfig:
    mode: AgenticRagMode = AgenticRagMode.OFF

    allow_operational_fallback: bool = True
    allow_quality_fallback: bool = True
    allow_partial_active: bool = False

    shadow_sample_rate: float = 1.0

    max_question_chars: int = 4_000

    active_complexities: tuple[str, ...] = (
        "complex",
        "advanced",
        "multi_step",
        "high",
    )

    configuration_warning: str = ""

    def __post_init__(self) -> None:
        if not (0.0 <= self.shadow_sample_rate <= 1.0):
            raise ValueError("shadow_sample_rate deve ficar entre 0 e 1.")

        if not (100 <= self.max_question_chars <= 20_000):
            raise ValueError("max_question_chars fora do intervalo permitido.")


@dataclass(
    frozen=True,
    slots=True,
)
class AgenticRagGatewayTelemetry:
    gateway_version: str
    mode: str
    decision: str
    outcome: str

    planner_complexity: str = ""
    research_status: str = ""
    synthesis_status: str = ""

    fallback_used: bool = False
    legacy_response_used: bool = False
    shadow_execution: bool = False

    model_executor_used: bool = False

    evidence_count: int = 0
    citation_count: int = 0

    citation_coverage: float = 0.0
    groundedness_score: float = 0.0
    answer_relevance: float = 0.0

    duration_ms: int = 0

    error_code: str = ""
    configuration_warning: str = ""

    content_logged: bool = False
    identity_logged: bool = False
    references_logged: bool = False

    def to_dict(
        self,
    ) -> dict[str, Any]:
        return {
            "gateway_version": (self.gateway_version),
            "mode": self.mode,
            "decision": self.decision,
            "outcome": self.outcome,
            "planner_complexity": (self.planner_complexity),
            "research_status": (self.research_status),
            "synthesis_status": (self.synthesis_status),
            "fallback_used": (self.fallback_used),
            "legacy_response_used": (self.legacy_response_used),
            "shadow_execution": (self.shadow_execution),
            "model_executor_used": (self.model_executor_used),
            "evidence_count": (self.evidence_count),
            "citation_count": (self.citation_count),
            "citation_coverage": (self.citation_coverage),
            "groundedness_score": (self.groundedness_score),
            "answer_relevance": (self.answer_relevance),
            "duration_ms": self.duration_ms,
            "error_code": self.error_code,
            "configuration_warning": (self.configuration_warning),
            "content_logged": False,
            "identity_logged": False,
            "references_logged": False,
        }


@dataclass(
    frozen=True,
    slots=True,
)
class _PipelineExecution:
    success: bool
    fatal: bool
    partial: bool

    complexity: str
    research_status: str
    synthesis_status: str

    answer: str
    sources: tuple[str, ...]

    evidence_count: int
    citation_count: int

    citation_coverage: float
    groundedness_score: float
    answer_relevance: float

    model_executor_used: bool

    error_code: str


PlanFactory = Callable[..., Any]
ResearchRunner = Callable[..., Any]
SynthesisRunner = Callable[..., Any]
LegacyNode = Callable[
    [InnaAgentState],
    InnaAgentState,
]
Clock = Callable[[], float]


_TRUE_VALUES = frozenset(
    {
        "1",
        "true",
        "yes",
        "on",
        "sim",
        "enabled",
    }
)

_FALSE_VALUES = frozenset(
    {
        "0",
        "false",
        "no",
        "off",
        "nao",
        "não",
        "disabled",
    }
)


_FATAL_MARKERS = (
    "contract",
    "schema",
    "unauthorized",
    "forbidden",
    "permission",
    "security",
    "policy_violation",
    "unknown_citation",
    "without_reference",
    "prompt_injection",
)


def _enum_value(
    value: Any,
) -> str:
    raw_value = getattr(
        value,
        "value",
        value,
    )

    return str(raw_value or "").strip().lower()


def _optional_text(
    value: Any,
) -> str | None:
    normalized = str(value or "").strip()

    return normalized or None


def _safe_float(
    value: Any,
    *,
    default: float = 0.0,
) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default

    return max(
        0.0,
        min(
            1.0,
            parsed,
        ),
    )


def _safe_int(
    value: Any,
    *,
    default: int = 0,
) -> int:
    try:
        return max(
            0,
            int(value),
        )
    except (TypeError, ValueError):
        return default


def _parse_bool(
    value: Any,
    *,
    default: bool,
) -> bool:
    normalized = str(value or "").strip().lower()

    if not normalized:
        return default

    if normalized in _TRUE_VALUES:
        return True

    if normalized in _FALSE_VALUES:
        return False

    return default


def _parse_float(
    value: Any,
    *,
    default: float,
) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default

    return max(
        0.0,
        min(
            1.0,
            parsed,
        ),
    )


def _parse_int(
    value: Any,
    *,
    default: int,
    minimum: int,
    maximum: int,
) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default

    return max(
        minimum,
        min(
            maximum,
            parsed,
        ),
    )


def load_agentic_rag_gateway_config(
    environ: (Mapping[str, str] | None) = None,
) -> AgenticRagGatewayConfig:
    """
    Carrega feature flags apenas do ambiente confiável.

    Um modo inválido volta para OFF, impedindo ativação
    acidental do fluxo novo.
    """

    source = environ if environ is not None else os.environ

    raw_mode = (
        str(
            source.get(
                AGENTIC_RAG_MODE_ENV,
                AgenticRagMode.OFF.value,
            )
            or AgenticRagMode.OFF.value
        )
        .strip()
        .lower()
    )

    configuration_warning = ""

    try:
        mode = AgenticRagMode(raw_mode)
    except ValueError:
        mode = AgenticRagMode.OFF
        configuration_warning = "invalid_mode_fallback_to_off"

    return AgenticRagGatewayConfig(
        mode=mode,
        allow_operational_fallback=(
            _parse_bool(
                source.get(AGENTIC_RAG_OPERATIONAL_FALLBACK_ENV),
                default=True,
            )
        ),
        allow_quality_fallback=(
            _parse_bool(
                source.get(AGENTIC_RAG_QUALITY_FALLBACK_ENV),
                default=True,
            )
        ),
        allow_partial_active=(
            _parse_bool(
                source.get(AGENTIC_RAG_ALLOW_PARTIAL_ENV),
                default=False,
            )
        ),
        shadow_sample_rate=(
            _parse_float(
                source.get(AGENTIC_RAG_SHADOW_SAMPLE_RATE_ENV),
                default=1.0,
            )
        ),
        max_question_chars=(
            _parse_int(
                source.get(AGENTIC_RAG_MAX_QUESTION_CHARS_ENV),
                default=4_000,
                minimum=100,
                maximum=20_000,
            )
        ),
        configuration_warning=(configuration_warning),
    )


def _safe_error_code(
    value: Any,
) -> str:
    if isinstance(
        value,
        BaseException,
    ):
        raw_value = value.__class__.__name__
    else:
        raw_value = str(value or "")

    normalized = re.sub(
        r"(?<!^)(?=[A-Z])",
        "_",
        raw_value,
    ).lower()

    normalized = re.sub(
        r"[^a-z0-9_]+",
        "_",
        normalized,
    ).strip("_")

    return normalized[:100] or "unknown_error"


def _is_fatal_failure(
    value: Any,
) -> bool:
    if isinstance(
        value,
        BaseException,
    ):
        searchable = (value.__class__.__name__ + " " + str(value)).lower()
    else:
        searchable = str(value or "").lower()

    return any(marker in searchable for marker in _FATAL_MARKERS)


def _invoke_supported(
    target: Callable[..., Any],
    *positional: Any,
    **payload: Any,
) -> Any:
    """
    Injeta apenas argumentos aceitos pelo contrato.

    Erros de assinatura continuam visíveis para a
    classificação fail closed do gateway.
    """

    signature = inspect.signature(target)

    parameters = signature.parameters

    accepts_kwargs = any(
        parameter.kind == inspect.Parameter.VAR_KEYWORD
        for parameter in parameters.values()
    )

    if accepts_kwargs:
        accepted_payload = payload
    else:
        accepted_payload = {
            name: value for name, value in payload.items() if name in parameters
        }

    return target(
        *positional,
        **accepted_payload,
    )


def _question_from_state(
    state: Mapping[str, Any],
    *,
    maximum_chars: int,
) -> str:
    return str(
        state.get(
            "user_message",
            "",
        )
        or ""
    ).strip()[:maximum_chars]


def _trace_id_from_state(
    state: Mapping[str, Any],
) -> str:
    existing = _optional_text(state.get("trace_id"))

    if existing:
        return existing[:160]

    return "agentic-rag-" + uuid.uuid4().hex


def _complexity_from_plan(
    plan: Any,
) -> str:
    return _enum_value(
        getattr(
            plan,
            "complexity",
            "",
        )
    )


def _requires_agentic_execution(
    *,
    complexity: str,
    config: AgenticRagGatewayConfig,
) -> bool:
    normalized = str(complexity or "").strip().lower()

    return normalized in set(config.active_complexities)


def _shadow_selected(
    *,
    trace_id: str,
    rate: float,
) -> bool:
    if rate <= 0:
        return False

    if rate >= 1:
        return True

    digest = sha256(trace_id.encode("utf-8")).digest()

    sample = int.from_bytes(
        digest[:8],
        "big",
    ) / float(2**64 - 1)

    return sample < rate


def _validation_failure_codes(
    synthesis: Any,
) -> list[str]:
    validation = getattr(
        synthesis,
        "validation",
        None,
    )

    reasons = getattr(
        validation,
        "failure_reasons",
        [],
    )

    return [_enum_value(reason) for reason in reasons if _enum_value(reason)]


def _references_from_synthesis(
    synthesis: Any,
) -> tuple[str, ...]:
    references: list[str] = []

    for citation in getattr(
        synthesis,
        "citations",
        [],
    ):
        for reference in getattr(
            citation,
            "references",
            [],
        ):
            normalized = str(reference or "").strip()

            if normalized:
                references.append(normalized[:1_000])

    return tuple(dict.fromkeys(references))[:30]


def _pipeline_metrics(
    synthesis: Any,
) -> tuple[
    float,
    float,
    float,
]:
    validation = getattr(
        synthesis,
        "validation",
        None,
    )

    return (
        _safe_float(
            getattr(
                validation,
                "citation_coverage",
                0.0,
            )
        ),
        _safe_float(
            getattr(
                validation,
                "groundedness_score",
                0.0,
            )
        ),
        _safe_float(
            getattr(
                validation,
                "answer_relevance",
                0.0,
            )
        ),
    )


def _execute_pipeline_after_plan(
    *,
    state: Mapping[str, Any],
    plan: Any,
    complexity: str,
    trace_id: str,
    research_runner: ResearchRunner,
    synthesis_runner: SynthesisRunner,
    model_executor: Any,
    allow_partial: bool,
) -> _PipelineExecution:
    user_id = _optional_text(state.get("user_id") or state.get("usuario_id"))

    session_id = _optional_text(state.get("thread_id") or state.get("session_id"))

    try:
        research = _invoke_supported(
            research_runner,
            plan=plan,
            user_id=user_id,
            session_id=session_id,
            trace_id=trace_id,
        )

    except Exception as exc:
        return _PipelineExecution(
            success=False,
            fatal=_is_fatal_failure(exc),
            partial=False,
            complexity=complexity,
            research_status="exception",
            synthesis_status="not_started",
            answer="",
            sources=(),
            evidence_count=0,
            citation_count=0,
            citation_coverage=0.0,
            groundedness_score=0.0,
            answer_relevance=0.0,
            model_executor_used=False,
            error_code=_safe_error_code(exc),
        )

    research_status = _enum_value(
        getattr(
            research,
            "status",
            "",
        )
    )

    if research_status != "succeeded":
        stop_reason = str(
            getattr(
                research,
                "stop_reason",
                research_status,
            )
            or research_status
        )

        return _PipelineExecution(
            success=False,
            fatal=_is_fatal_failure(stop_reason),
            partial=False,
            complexity=complexity,
            research_status=(research_status or "failed"),
            synthesis_status="not_started",
            answer="",
            sources=(),
            evidence_count=_safe_int(
                getattr(
                    getattr(
                        research,
                        "assessment",
                        None,
                    ),
                    "evidence_count",
                    0,
                )
            ),
            citation_count=0,
            citation_coverage=0.0,
            groundedness_score=0.0,
            answer_relevance=0.0,
            model_executor_used=False,
            error_code=_safe_error_code(stop_reason),
        )

    try:
        synthesis = _invoke_supported(
            synthesis_runner,
            research_result=research,
            model_executor=(model_executor),
            trace_id=trace_id,
        )

    except Exception as exc:
        return _PipelineExecution(
            success=False,
            fatal=_is_fatal_failure(exc),
            partial=False,
            complexity=complexity,
            research_status=research_status,
            synthesis_status="exception",
            answer="",
            sources=(),
            evidence_count=_safe_int(
                getattr(
                    getattr(
                        research,
                        "assessment",
                        None,
                    ),
                    "evidence_count",
                    0,
                )
            ),
            citation_count=0,
            citation_coverage=0.0,
            groundedness_score=0.0,
            answer_relevance=0.0,
            model_executor_used=False,
            error_code=_safe_error_code(exc),
        )

    synthesis_status = _enum_value(
        getattr(
            synthesis,
            "status",
            "",
        )
    )

    validation = getattr(
        synthesis,
        "validation",
        None,
    )

    validation_valid = bool(
        getattr(
            validation,
            "valid",
            False,
        )
    )

    failure_codes = _validation_failure_codes(synthesis)

    fatal = any(_is_fatal_failure(code) for code in failure_codes)

    generated_answer_as_evidence = bool(
        getattr(
            synthesis,
            "metadata",
            {},
        ).get(
            "generated_answer_as_evidence",
            False,
        )
    )

    if generated_answer_as_evidence:
        fatal = True
        failure_codes.append("generated_answer_as_evidence")

    partial = synthesis_status == "partial"

    releasable_status = synthesis_status == "grounded" or (partial and allow_partial)

    answer = str(
        getattr(
            synthesis,
            "answer",
            "",
        )
        or ""
    ).strip()

    success = bool(releasable_status and validation_valid and answer and not fatal)

    (
        citation_coverage,
        groundedness_score,
        answer_relevance,
    ) = _pipeline_metrics(synthesis)

    citations = tuple(
        getattr(
            synthesis,
            "citations",
            [],
        )
    )

    error_code = ""

    if not success:
        error_code = (
            failure_codes[0]
            if failure_codes
            else (synthesis_status or "synthesis_rejected")
        )

    return _PipelineExecution(
        success=success,
        fatal=fatal,
        partial=partial,
        complexity=complexity,
        research_status=research_status,
        synthesis_status=(synthesis_status or "unknown"),
        answer=(answer if success else ""),
        sources=(_references_from_synthesis(synthesis) if success else ()),
        evidence_count=_safe_int(
            getattr(
                synthesis,
                "evidence_count",
                0,
            )
        ),
        citation_count=len(citations),
        citation_coverage=(citation_coverage),
        groundedness_score=(groundedness_score),
        answer_relevance=(answer_relevance),
        model_executor_used=bool(
            getattr(
                synthesis,
                "model_executor_used",
                False,
            )
        ),
        error_code=_safe_error_code(error_code),
    )


def _telemetry(
    *,
    config: AgenticRagGatewayConfig,
    decision: GatewayDecision,
    outcome: GatewayOutcome,
    duration_ms: int,
    pipeline: (_PipelineExecution | None) = None,
    fallback_used: bool = False,
    legacy_response_used: bool = False,
    shadow_execution: bool = False,
    error_code: str = "",
    complexity: str = "",
) -> AgenticRagGatewayTelemetry:
    return AgenticRagGatewayTelemetry(
        gateway_version=(AGENTIC_RAG_GATEWAY_VERSION),
        mode=config.mode.value,
        decision=decision.value,
        outcome=outcome.value,
        planner_complexity=(
            pipeline.complexity if pipeline is not None else complexity
        ),
        research_status=(pipeline.research_status if pipeline is not None else ""),
        synthesis_status=(pipeline.synthesis_status if pipeline is not None else ""),
        fallback_used=fallback_used,
        legacy_response_used=(legacy_response_used),
        shadow_execution=(shadow_execution),
        model_executor_used=(
            pipeline.model_executor_used if pipeline is not None else False
        ),
        evidence_count=(pipeline.evidence_count if pipeline is not None else 0),
        citation_count=(pipeline.citation_count if pipeline is not None else 0),
        citation_coverage=(pipeline.citation_coverage if pipeline is not None else 0.0),
        groundedness_score=(
            pipeline.groundedness_score if pipeline is not None else 0.0
        ),
        answer_relevance=(pipeline.answer_relevance if pipeline is not None else 0.0),
        duration_ms=max(
            0,
            duration_ms,
        ),
        error_code=(
            error_code or (pipeline.error_code if pipeline is not None else "")
        ),
        configuration_warning=(config.configuration_warning),
    )


def _merge_telemetry_into_legacy(
    *,
    state: Mapping[str, Any],
    legacy_node: LegacyNode,
    telemetry: (AgenticRagGatewayTelemetry),
    trace_event: str,
) -> InnaAgentState:
    legacy_result = legacy_node(dict(state))

    structured_response = dict(
        legacy_result.get(
            "structured_response",
            {},
        )
    )

    structured_response["agentic_rag_execution"] = telemetry.to_dict()

    trace = list(
        legacy_result.get(
            "trace",
            [],
        )
    )

    trace.append(trace_event)

    return {
        **legacy_result,
        "agentic_rag_mode": (telemetry.mode),
        "agentic_rag_execution": (telemetry.to_dict()),
        "agentic_rag_fallback_used": (telemetry.fallback_used),
        "structured_response": (structured_response),
        "trace": trace,
    }


def _active_success_state(
    *,
    state: Mapping[str, Any],
    pipeline: _PipelineExecution,
    telemetry: (AgenticRagGatewayTelemetry),
    trace_id: str,
) -> InnaAgentState:
    structured_response = dict(
        state.get(
            "structured_response",
            {},
        )
    )

    tool_results = list(
        state.get(
            "tool_results",
            [],
        )
    )

    compact_result = {
        "call_id": ("agentic-rag-" + uuid.uuid4().hex[:16]),
        "tool": ("agentic_rag_pipeline"),
        "status": "success",
        "ok": True,
        "duration_ms": (telemetry.duration_ms),
        "evidence_count": (pipeline.evidence_count),
        "citation_count": (pipeline.citation_count),
    }

    tool_results.append(compact_result)

    confidence = max(
        0.0,
        min(
            1.0,
            (pipeline.groundedness_score + pipeline.citation_coverage) / 2.0,
        ),
    )

    response_model = AgentResponse(
        agent="rag_agent",
        intent=state.get(
            "intent",
            "consulta_rag",
        ),
        summary=pipeline.answer,
        recommendations=[],
        next_steps=[],
        sources=list(pipeline.sources),
        confidence=confidence,
    )

    structured_response["agentic_rag_execution"] = telemetry.to_dict()

    structured_response["rag_execution"] = {
        "ok": True,
        "mode": "agentic_rag",
        "duration_ms": (telemetry.duration_ms),
        "retrieved_documents": (pipeline.evidence_count),
        "citation_count": (pipeline.citation_count),
        "sources": list(pipeline.sources),
    }

    structured_response["agent_response"] = response_model.model_dump()

    trace = list(
        state.get(
            "trace",
            [],
        )
    )

    trace.extend(
        [
            "agentic_rag:active:grounded",
            "agent:rag_agent",
        ]
    )

    return {
        **state,
        "trace_id": trace_id,
        "current_agent": "rag_agent",
        "response": pipeline.answer,
        "conversation_history": [
            {
                "role": "assistant",
                "content": pipeline.answer,
            }
        ],
        "structured_response": (structured_response),
        "tool_results": tool_results,
        "errors": list(
            state.get(
                "errors",
                [],
            )
        ),
        "trace": trace,
        "agentic_rag_mode": (AgenticRagMode.ACTIVE.value),
        "agentic_rag_execution": (telemetry.to_dict()),
        "agentic_rag_fallback_used": (False),
    }


def _blocked_state(
    *,
    state: Mapping[str, Any],
    telemetry: (AgenticRagGatewayTelemetry),
    trace_id: str,
) -> InnaAgentState:
    safe_answer = "Não foi possível concluir esta consulta com segurança neste momento."

    safe_error_code = telemetry.error_code or "agentic_rag_security_blocked"

    structured_response = dict(
        state.get(
            "structured_response",
            {},
        )
    )

    response_model = AgentResponse(
        agent="rag_agent",
        intent=state.get(
            "intent",
            "consulta_rag",
        ),
        summary=safe_answer,
        recommendations=[("Reformule a pergunta ou tente novamente mais tarde.")],
        next_steps=[],
        sources=[],
        confidence=0.0,
    )

    structured_response["agentic_rag_execution"] = telemetry.to_dict()

    structured_response["agent_response"] = response_model.model_dump()

    tool_results = list(
        state.get(
            "tool_results",
            [],
        )
    )

    tool_results.append(
        {
            "call_id": ("agentic-rag-blocked-" + uuid.uuid4().hex[:12]),
            "tool": ("agentic_rag_pipeline"),
            "status": "error",
            "ok": False,
            "error_code": (safe_error_code),
            "retryable": False,
            "duration_ms": (telemetry.duration_ms),
        }
    )

    errors = list(
        state.get(
            "errors",
            [],
        )
    )

    errors.append(safe_error_code)

    trace = list(
        state.get(
            "trace",
            [],
        )
    )

    trace.extend(
        [
            "agentic_rag:active:blocked",
            "agent:rag_agent:error",
        ]
    )

    return {
        **state,
        "trace_id": trace_id,
        "current_agent": "rag_agent",
        "response": safe_answer,
        "conversation_history": [
            {
                "role": "assistant",
                "content": safe_answer,
            }
        ],
        "structured_response": (structured_response),
        "tool_results": tool_results,
        "errors": errors,
        "trace": trace,
        "agentic_rag_mode": (AgenticRagMode.ACTIVE.value),
        "agentic_rag_execution": (telemetry.to_dict()),
        "agentic_rag_fallback_used": (False),
    }


def run_agentic_rag_gateway(
    state: InnaAgentState,
    *,
    config: (AgenticRagGatewayConfig | None) = None,
    legacy_node: LegacyNode = (legacy_rag_agent_node),
    plan_factory: PlanFactory = (create_research_plan),
    research_runner: ResearchRunner = (run_research_agent_with_runtime),
    synthesis_runner: SynthesisRunner = (synthesize_research_result),
    model_executor: Any = None,
    monotonic_clock: Clock = (time.monotonic),
) -> InnaAgentState:
    """
    Gateway compatível com o nó rag_agent existente.

    OFF:
        retorna exatamente o resultado legado.

    SHADOW:
        mantém a resposta legada e executa o pipeline
        novo apenas para métricas.

    ACTIVE:
        consultas simples continuam no legado;
        consultas complexas usam o Agentic RAG.

    Falhas de contrato, autorização ou segurança não
    podem contornar a governança usando o RAG legado.
    """

    effective_config = config or load_agentic_rag_gateway_config()

    if effective_config.mode == AgenticRagMode.OFF:
        return legacy_node(dict(state))

    started = monotonic_clock()

    def elapsed_ms() -> int:
        return max(
            0,
            int(round((monotonic_clock() - started) * 1_000)),
        )

    question = _question_from_state(
        state,
        maximum_chars=(effective_config.max_question_chars),
    )

    trace_id = _trace_id_from_state(state)

    if not question:
        telemetry = _telemetry(
            config=effective_config,
            decision=(GatewayDecision.LEGACY_EMPTY_QUESTION),
            outcome=(GatewayOutcome.LEGACY),
            duration_ms=elapsed_ms(),
            legacy_response_used=True,
        )

        return _merge_telemetry_into_legacy(
            state=state,
            legacy_node=legacy_node,
            telemetry=telemetry,
            trace_event=(
                f"agentic_rag:{effective_config.mode.value}:empty_question_legacy"
            ),
        )

    if effective_config.mode == AgenticRagMode.SHADOW and not _shadow_selected(
        trace_id=trace_id,
        rate=(effective_config.shadow_sample_rate),
    ):
        telemetry = _telemetry(
            config=effective_config,
            decision=(GatewayDecision.SHADOW_NOT_SELECTED),
            outcome=(GatewayOutcome.LEGACY),
            duration_ms=elapsed_ms(),
            legacy_response_used=True,
            shadow_execution=False,
        )

        return _merge_telemetry_into_legacy(
            state=state,
            legacy_node=legacy_node,
            telemetry=telemetry,
            trace_event=("agentic_rag:shadow:not_selected"),
        )

    language = str(
        state.get(
            "language",
            "pt",
        )
        or "pt"
    ).strip()

    user_id = _optional_text(
        state.get("user_id")
        or state.get("usuario_id")
    )

    intent = str(
        state.get(
            "intent",
            "consulta_rag",
        )
        or "consulta_rag"
    ).strip()

    try:
        plan = _invoke_supported(
            plan_factory,
            question,
            language=language,
            user_id=user_id,
            intent=intent,
            trace_id=trace_id,
        )

    except Exception as exc:
        fatal = _is_fatal_failure(exc)

        telemetry = _telemetry(
            config=effective_config,
            decision=(
                GatewayDecision.SECURITY_BLOCK
                if fatal
                else (GatewayDecision.LEGACY_OPERATIONAL_FALLBACK)
            ),
            outcome=(GatewayOutcome.BLOCKED if fatal else GatewayOutcome.FALLBACK),
            duration_ms=elapsed_ms(),
            fallback_used=not fatal,
            legacy_response_used=not fatal,
            shadow_execution=(effective_config.mode == AgenticRagMode.SHADOW),
            error_code=(_safe_error_code(exc)),
        )

        if effective_config.mode == AgenticRagMode.SHADOW:
            return _merge_telemetry_into_legacy(
                state=state,
                legacy_node=legacy_node,
                telemetry=telemetry,
                trace_event=("agentic_rag:shadow:planner_failed"),
            )

        if fatal:
            return _blocked_state(
                state=state,
                telemetry=telemetry,
                trace_id=trace_id,
            )

        if effective_config.allow_operational_fallback:
            return _merge_telemetry_into_legacy(
                state=state,
                legacy_node=legacy_node,
                telemetry=telemetry,
                trace_event=("agentic_rag:active:planner_fallback"),
            )

        blocked_telemetry = _telemetry(
            config=effective_config,
            decision=(GatewayDecision.SECURITY_BLOCK),
            outcome=(GatewayOutcome.BLOCKED),
            duration_ms=elapsed_ms(),
            error_code=("operational_fallback_disabled"),
        )

        return _blocked_state(
            state=state,
            telemetry=blocked_telemetry,
            trace_id=trace_id,
        )

    complexity = _complexity_from_plan(plan)

    if (
        effective_config.mode == AgenticRagMode.ACTIVE
        and not _requires_agentic_execution(
            complexity=complexity,
            config=effective_config,
        )
    ):
        telemetry = _telemetry(
            config=effective_config,
            decision=(GatewayDecision.LEGACY_SIMPLE_QUERY),
            outcome=(GatewayOutcome.LEGACY),
            duration_ms=elapsed_ms(),
            legacy_response_used=True,
            complexity=complexity,
        )

        return _merge_telemetry_into_legacy(
            state=state,
            legacy_node=legacy_node,
            telemetry=telemetry,
            trace_event=("agentic_rag:active:simple_query_legacy"),
        )

    pipeline = _execute_pipeline_after_plan(
        state=state,
        plan=plan,
        complexity=complexity,
        trace_id=trace_id,
        research_runner=(research_runner),
        synthesis_runner=(synthesis_runner),
        model_executor=(model_executor),
        allow_partial=(effective_config.allow_partial_active),
    )

    if effective_config.mode == AgenticRagMode.SHADOW:
        shadow_outcome = (
            GatewayOutcome.SHADOW_GROUNDED
            if pipeline.success
            else (
                GatewayOutcome.SHADOW_FAILED
                if (
                    pipeline.research_status
                    in {
                        "exception",
                        "failed",
                        "exhausted",
                    }
                    or pipeline.fatal
                )
                else (GatewayOutcome.SHADOW_REJECTED)
            )
        )

        telemetry = _telemetry(
            config=effective_config,
            decision=(GatewayDecision.SHADOW_EXECUTION),
            outcome=shadow_outcome,
            duration_ms=elapsed_ms(),
            pipeline=pipeline,
            legacy_response_used=True,
            shadow_execution=True,
        )

        return _merge_telemetry_into_legacy(
            state=state,
            legacy_node=legacy_node,
            telemetry=telemetry,
            trace_event=(f"agentic_rag:shadow:{shadow_outcome.value}"),
        )

    if pipeline.success:
        outcome = (
            GatewayOutcome.PARTIAL if pipeline.partial else GatewayOutcome.GROUNDED
        )

        telemetry = _telemetry(
            config=effective_config,
            decision=(GatewayDecision.AGENTIC_EXECUTION),
            outcome=outcome,
            duration_ms=elapsed_ms(),
            pipeline=pipeline,
        )

        return _active_success_state(
            state=state,
            pipeline=pipeline,
            telemetry=telemetry,
            trace_id=trace_id,
        )

    if pipeline.fatal:
        telemetry = _telemetry(
            config=effective_config,
            decision=(GatewayDecision.SECURITY_BLOCK),
            outcome=(GatewayOutcome.BLOCKED),
            duration_ms=elapsed_ms(),
            pipeline=pipeline,
            error_code=(pipeline.error_code),
        )

        return _blocked_state(
            state=state,
            telemetry=telemetry,
            trace_id=trace_id,
        )

    quality_failure = pipeline.synthesis_status not in {
        "",
        "not_started",
        "exception",
    }

    fallback_allowed = (
        effective_config.allow_quality_fallback
        if quality_failure
        else (effective_config.allow_operational_fallback)
    )

    if fallback_allowed:
        decision = (
            GatewayDecision.LEGACY_QUALITY_FALLBACK
            if quality_failure
            else (GatewayDecision.LEGACY_OPERATIONAL_FALLBACK)
        )

        telemetry = _telemetry(
            config=effective_config,
            decision=decision,
            outcome=(GatewayOutcome.FALLBACK),
            duration_ms=elapsed_ms(),
            pipeline=pipeline,
            fallback_used=True,
            legacy_response_used=True,
        )

        return _merge_telemetry_into_legacy(
            state=state,
            legacy_node=legacy_node,
            telemetry=telemetry,
            trace_event=(f"agentic_rag:active:{decision.value}"),
        )

    telemetry = _telemetry(
        config=effective_config,
        decision=(GatewayDecision.SECURITY_BLOCK),
        outcome=(GatewayOutcome.BLOCKED),
        duration_ms=elapsed_ms(),
        pipeline=pipeline,
        error_code=(pipeline.error_code or "fallback_disabled"),
    )

    return _blocked_state(
        state=state,
        telemetry=telemetry,
        trace_id=trace_id,
    )


def agentic_rag_gateway_node(
    state: InnaAgentState,
) -> InnaAgentState:
    """
    Nó registrado no LangGraph de produção.

    A configuração é carregada em cada execução,
    permitindo alterar a feature flag após reinício
    do serviço sem recompilar o grafo.
    """

    return run_agentic_rag_gateway(state)


def agentic_rag_gateway_audit_payload(
    state: Mapping[str, Any],
) -> dict[str, Any]:
    """
    Retorna somente telemetria sanitizada.

    Não inclui pergunta, resposta, evidências,
    referências, user_id, session_id ou thread_id.
    """

    execution = state.get(
        "agentic_rag_execution",
        {},
    )

    if not isinstance(
        execution,
        Mapping,
    ):
        execution = {}

    allowed_keys = (
        "gateway_version",
        "mode",
        "decision",
        "outcome",
        "planner_complexity",
        "research_status",
        "synthesis_status",
        "fallback_used",
        "legacy_response_used",
        "shadow_execution",
        "model_executor_used",
        "evidence_count",
        "citation_count",
        "citation_coverage",
        "groundedness_score",
        "answer_relevance",
        "duration_ms",
        "error_code",
        "configuration_warning",
        "content_logged",
        "identity_logged",
        "references_logged",
    )

    return {
        "event": ("agentic_rag_gateway_completed"),
        **{key: execution.get(key) for key in allowed_keys if key in execution},
        "question_logged": False,
        "answer_logged": False,
        "evidence_logged": False,
        "references_logged": False,
        "identity_logged": False,
    }



# Compatibilidade publica:
# o node historicamente foi exposto por
# src.agentic_rag.langgraph_integration.
# Alguns consumidores usam __module__ como
# parte do contrato de introspeccao.
agentic_rag_gateway_node.__module__ = (
    "src.agentic_rag.langgraph_integration"
)


__all__ = [
    "AGENTIC_RAG_GATEWAY_VERSION",
    "AGENTIC_RAG_MODE_ENV",
    "AgenticRagGatewayConfig",
    "AgenticRagGatewayTelemetry",
    "AgenticRagMode",
    "GatewayDecision",
    "GatewayOutcome",
    "agentic_rag_gateway_audit_payload",
    "agentic_rag_gateway_node",
    "load_agentic_rag_gateway_config",
    "run_agentic_rag_gateway",
]
