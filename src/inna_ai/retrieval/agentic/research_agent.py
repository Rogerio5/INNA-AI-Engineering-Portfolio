"""
Research Agent iterativo e governado da INNA.

Arquitetura:
- rodadas semânticas definidas pelo Query Planner;
- tentativas técnicas dentro da mesma rodada;
- classificação de erros retryable/non-retryable/fatal;
- orçamento de chamadas e duração;
- retry seletivo por lacuna;
- integração somente pelo Router e runtime governado;
- auditoria sanitizada.

O módulo não acessa Gemini, banco, rede ou RAG diretamente.
"""

from __future__ import annotations

import inspect
import re
import time
import uuid
from collections import defaultdict
from collections.abc import Callable
from enum import StrEnum
from typing import Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    model_validator,
)

from inna_ai.retrieval.agentic.collector import EvidenceCollectionError, collect_evidence_from_tool_result
from inna_ai.retrieval.agentic.contracts import EvidenceCollectionResult, EvidenceCollectionStatus, EvidenceGapType, EvidenceItem, ResearchPlan, ResearchSource, ResearchSubquery, SufficiencyAssessment
from inna_ai.retrieval.agentic.evidence import content_sha256
from inna_ai.retrieval.agentic.router import ResearchRoute, route_research_plan
from inna_ai.retrieval.agentic.sufficiency import assess_evidence_sufficiency, assessment_to_audit_payload

RESEARCH_AGENT_VERSION = "5.1.0"


class ResearchAgentStatus(StrEnum):
    SUCCEEDED = "succeeded"
    EXHAUSTED = "exhausted"
    FAILED = "failed"


class ResearchStopReason(StrEnum):
    SUFFICIENT = "sufficient"
    MAX_ROUNDS_REACHED = "max_rounds_reached"
    NO_RETRYABLE_GAPS = "no_retryable_gaps"

    TOOL_CALL_BUDGET_EXHAUSTED = "tool_call_budget_exhausted"

    DURATION_BUDGET_EXHAUSTED = "duration_budget_exhausted"

    ATTEMPT_LIMIT_REACHED = "attempt_limit_reached"

    CONSECUTIVE_FAILURE_LIMIT_REACHED = "consecutive_failure_limit_reached"

    ROUTING_CONTRACT_ERROR = "routing_contract_error"

    EXECUTOR_CONTRACT_ERROR = "executor_contract_error"

    INTERNAL_ERROR = "internal_error"


class RetryDisposition(StrEnum):
    RETRYABLE = "retryable"
    NON_RETRYABLE = "non_retryable"
    FATAL = "fatal"


class ResearchExecutionError(RuntimeError):
    """Erro seguro durante a orquestração."""


class ResearchRoutingContractError(ResearchExecutionError):
    """O Router retornou estrutura incompatível."""


class ResearchExecutorContractError(ResearchExecutionError):
    """O executor não segue o contrato esperado."""


class ToolRuntimeReportedError(ResearchExecutionError):
    """
    O runtime informou falha sem saída utilizável.
    """

    def __init__(
        self,
        safe_code: str,
    ) -> None:
        self.safe_code = _normalize_code(
            safe_code,
            fallback="tool_runtime_error",
        )

        super().__init__(self.safe_code)


class ResearchExecutionPolicy(BaseModel):
    """
    Teto operacional da pesquisa.

    plan.max_rounds:
        profundidade semântica recomendada.

    max_rounds:
        limite operacional máximo permitido.

    max_attempts_per_step:
        tentativas técnicas dentro da mesma rodada.
    """

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    max_rounds: int = Field(
        default=3,
        ge=1,
        le=3,
    )

    max_tool_calls: int = Field(
        default=24,
        ge=1,
        le=100,
    )

    max_attempts_per_step: int = Field(
        default=2,
        ge=1,
        le=5,
    )

    max_total_duration_ms: int = Field(
        default=120_000,
        ge=1,
        le=900_000,
    )

    max_consecutive_failures: int = Field(
        default=6,
        ge=1,
        le=30,
    )

    retry_unknown_runtime_errors: bool = True

    retry_required_steps_only: bool = True

    continue_after_nonretryable_tool_failure: bool = True

    stop_on_contract_error: bool = True

    retry_backoff_ms: int = Field(
        default=0,
        ge=0,
        le=30_000,
    )

    retry_backoff_multiplier: float = Field(
        default=2.0,
        ge=1.0,
        le=5.0,
    )

    max_retry_backoff_ms: int = Field(
        default=5_000,
        ge=0,
        le=60_000,
    )

    @model_validator(mode="after")
    def validate_policy(
        self,
    ) -> ResearchExecutionPolicy:
        if self.max_retry_backoff_ms < self.retry_backoff_ms:
            raise ValueError(
                "max_retry_backoff_ms não pode ser menor que retry_backoff_ms."
            )

        return self


class TechnicalRetryEvent(BaseModel):
    """
    Evento sanitizado de tentativa técnica.

    Não guarda mensagem de erro, argumentos,
    evidências ou identidade.
    """

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    round_number: int = Field(
        ge=1,
        le=3,
    )

    step_id: str = Field(
        min_length=1,
        max_length=120,
    )

    attempt_number: int = Field(
        ge=1,
        le=5,
    )

    total_step_attempt: int = Field(
        ge=1,
        le=100,
    )

    error_code: str = Field(
        min_length=1,
        max_length=120,
    )

    disposition: RetryDisposition

    retry_scheduled: bool

    backoff_ms: int = Field(
        ge=0,
        le=60_000,
    )


class ResearchRoundSummary(BaseModel):
    """
    Resumo sanitizado de uma rodada semântica.
    """

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    round_number: int = Field(
        ge=1,
        le=3,
    )

    planned_step_ids: list[str] = Field(
        default_factory=list,
        max_length=20,
    )

    executed_step_ids: list[str] = Field(
        default_factory=list,
        max_length=20,
    )

    successful_step_ids: list[str] = Field(
        default_factory=list,
        max_length=20,
    )

    rejected_step_ids: list[str] = Field(
        default_factory=list,
        max_length=20,
    )

    semantic_retry_step_ids: list[str] = Field(
        default_factory=list,
        max_length=20,
    )

    evidence_count: int = Field(
        ge=0,
    )

    tool_call_count: int = Field(
        ge=0,
    )

    technical_retry_count: int = Field(
        ge=0,
    )

    sufficiency_score: float = Field(
        ge=0.0,
        le=1.0,
    )

    sufficient: bool


class ResearchAgentResult(BaseModel):
    """
    Resultado integral do Research Agent.

    Logs devem utilizar somente
    research_result_to_audit_payload().
    """

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    status: ResearchAgentStatus

    stop_reason: ResearchStopReason

    trace_id: str = Field(
        min_length=8,
        max_length=160,
    )

    plan: ResearchPlan

    collections: list[EvidenceCollectionResult] = Field(
        default_factory=list,
        max_length=100,
    )

    assessment: SufficiencyAssessment

    rounds: list[ResearchRoundSummary] = Field(
        default_factory=list,
        max_length=3,
    )

    retry_events: list[TechnicalRetryEvent] = Field(
        default_factory=list,
        max_length=100,
    )

    total_tool_calls: int = Field(
        ge=0,
        le=100,
    )

    technical_retry_count: int = Field(
        ge=0,
        le=100,
    )

    duration_ms: float = Field(
        ge=0.0,
    )

    attempted_steps: dict[str, int] = Field(
        default_factory=dict,
        max_length=30,
    )

    error_codes: list[str] = Field(
        default_factory=list,
        max_length=30,
    )

    runtime_executor_used: bool = False

    metadata: dict[str, Any] = Field(
        default_factory=dict,
        max_length=40,
    )

    @model_validator(mode="after")
    def validate_final_state(
        self,
    ) -> ResearchAgentResult:
        if (
            self.status == ResearchAgentStatus.SUCCEEDED
            and not self.assessment.sufficient
        ):
            raise ValueError("Resultado succeeded exige avaliação suficiente.")

        if (
            self.assessment.sufficient
            and self.stop_reason != ResearchStopReason.SUFFICIENT
        ):
            raise ValueError(
                "Pesquisa suficiente deve encerrar com stop_reason=sufficient."
            )

        configured_budget = int(
            self.metadata.get(
                "max_tool_calls",
                self.total_tool_calls,
            )
        )

        if self.total_tool_calls > configured_budget:
            raise ValueError("O número de chamadas superou o orçamento configurado.")

        scheduled_retries = sum(event.retry_scheduled for event in self.retry_events)

        if self.technical_retry_count != scheduled_retries:
            raise ValueError(
                "technical_retry_count está inconsistente com retry_events."
            )

        return self


RouteExecutor = Callable[..., Any]
SleepFunction = Callable[[float], None]
ClockFunction = Callable[[], float]


_RETRYABLE_TOKENS = frozenset(
    {
        "timeout",
        "timed_out",
        "connection",
        "temporar",
        "transient",
        "rate_limit",
        "resource_exhausted",
        "service_unavailable",
        "unavailable",
        "overloaded",
        "gateway",
        "network",
        "retry",
    }
)


_NON_RETRYABLE_TOKENS = frozenset(
    {
        "permission",
        "unauthorized",
        "forbidden",
        "validation",
        "contract",
        "schema",
        "invalid_argument",
        "invalid_input",
        "not_allowed",
        "policy_denied",
        "authentication",
    }
)


def _normalize_code(
    value: Any,
    *,
    fallback: str = "unknown_error",
) -> str:
    normalized = re.sub(
        r"(?<!^)(?=[A-Z])",
        "_",
        str(value or ""),
    ).lower()

    normalized = re.sub(
        r"[^a-z0-9_]+",
        "_",
        normalized,
    ).strip("_")

    return normalized[:120] or fallback


def _safe_error_code(
    error: BaseException,
) -> str:
    explicit_code = getattr(
        error,
        "safe_code",
        None,
    )

    if explicit_code:
        return _normalize_code(explicit_code)

    return _normalize_code(error.__class__.__name__)


def _trace_id(
    value: str | None,
) -> str:
    normalized = str(value or "").strip()

    if normalized:
        return normalized[:160]

    return "research-" + uuid.uuid4().hex


def _elapsed_ms(
    *,
    started_at: float,
    clock: ClockFunction,
) -> float:
    return max(
        0.0,
        (float(clock()) - float(started_at)) * 1000.0,
    )


def _duration_exhausted(
    *,
    started_at: float,
    clock: ClockFunction,
    policy: ResearchExecutionPolicy,
) -> bool:
    return (
        _elapsed_ms(
            started_at=started_at,
            clock=clock,
        )
        >= policy.max_total_duration_ms
    )


def _retry_backoff_ms(
    *,
    policy: ResearchExecutionPolicy,
    attempt_number: int,
) -> int:
    if policy.retry_backoff_ms <= 0:
        return 0

    calculated = policy.retry_backoff_ms * (
        policy.retry_backoff_multiplier
        ** max(
            0,
            attempt_number - 1,
        )
    )

    return min(
        policy.max_retry_backoff_ms,
        int(round(calculated)),
    )


def _classify_failure(
    error: BaseException,
    *,
    policy: ResearchExecutionPolicy,
) -> tuple[
    RetryDisposition,
    str,
]:
    error_code = _safe_error_code(error)

    if isinstance(
        error,
        (
            ResearchRoutingContractError,
            ResearchExecutorContractError,
        ),
    ):
        return (
            RetryDisposition.FATAL,
            error_code,
        )

    if isinstance(
        error,
        (
            ValidationError,
            EvidenceCollectionError,
            ValueError,
            TypeError,
        ),
    ):
        return (
            RetryDisposition.NON_RETRYABLE,
            error_code,
        )

    signal = " ".join(
        [
            error_code,
            error.__class__.__name__.lower(),
            str(error).lower(),
        ]
    )

    if any(token in signal for token in _NON_RETRYABLE_TOKENS):
        return (
            RetryDisposition.NON_RETRYABLE,
            error_code,
        )

    if isinstance(
        error,
        (
            TimeoutError,
            ConnectionError,
            OSError,
        ),
    ):
        return (
            RetryDisposition.RETRYABLE,
            error_code,
        )

    if any(token in signal for token in _RETRYABLE_TOKENS):
        return (
            RetryDisposition.RETRYABLE,
            error_code,
        )

    if isinstance(error, RuntimeError) and policy.retry_unknown_runtime_errors:
        return (
            RetryDisposition.RETRYABLE,
            error_code,
        )

    return (
        RetryDisposition.NON_RETRYABLE,
        error_code,
    )


def _call_router(
    *,
    plan: ResearchPlan,
    user_id: str | None,
    session_id: str | None,
    trace_id: str,
) -> list[ResearchRoute]:
    router = route_research_plan

    signature = inspect.signature(router)

    parameters = signature.parameters

    candidate_context = {
        "user_id": user_id,
        "session_id": session_id,
        "trace_id": trace_id,
    }

    accepts_kwargs = any(
        parameter.kind == inspect.Parameter.VAR_KEYWORD
        for parameter in parameters.values()
    )

    context_kwargs = {
        name: value
        for name, value in candidate_context.items()
        if (value is not None and (accepts_kwargs or name in parameters))
    }

    if "plan" in parameters:
        routes = router(
            plan=plan,
            **context_kwargs,
        )

    else:
        routes = router(
            plan,
            **context_kwargs,
        )

    return list(routes)


def _align_routes_to_steps(
    *,
    routes: list[ResearchRoute],
    steps: list[ResearchSubquery],
) -> list[ResearchRoute]:
    if len(routes) != len(steps):
        raise ResearchRoutingContractError(
            "A quantidade de rotas não corresponde à quantidade de etapas."
        )

    route_step_ids = [
        getattr(
            route,
            "step_id",
            None,
        )
        for route in routes
    ]

    if any(route_step_ids) and not all(route_step_ids):
        raise ResearchRoutingContractError(
            "O Router retornou identificação parcial das etapas."
        )

    if all(route_step_ids):
        normalized_ids = [str(value) for value in route_step_ids]

        if len(normalized_ids) != len(set(normalized_ids)):
            raise ResearchRoutingContractError("O Router retornou step_ids duplicados.")

        route_by_step_id = {str(route.step_id): route for route in routes}

        missing_step_ids = [
            step.step_id for step in steps if (step.step_id not in route_by_step_id)
        ]

        if missing_step_ids:
            raise ResearchRoutingContractError(
                "O Router não retornou todas as etapas planejadas."
            )

        return [route_by_step_id[step.step_id] for step in steps]

    return routes


def _invoke_executor(
    executor: RouteExecutor,
    *,
    route: ResearchRoute,
    step: ResearchSubquery,
    round_number: int,
    attempt_number: int,
    total_attempt_number: int,
    trace_id: str,
) -> Any:
    try:
        signature = inspect.signature(executor)

    except (TypeError, ValueError) as exc:
        raise ResearchExecutorContractError(
            "Não foi possível inspecionar o contrato do executor."
        ) from exc

    parameters = signature.parameters

    payload = {
        "route": route,
        "step": step,
        "round_number": round_number,
        "attempt_number": attempt_number,
        "total_attempt_number": (total_attempt_number),
        "trace_id": trace_id,
    }

    accepts_kwargs = any(
        parameter.kind == inspect.Parameter.VAR_KEYWORD
        for parameter in parameters.values()
    )

    if accepts_kwargs:
        return executor(**payload)

    route_parameter = parameters.get("route")

    if (
        route_parameter is not None
        and route_parameter.kind != inspect.Parameter.POSITIONAL_ONLY
    ):
        accepted_payload = {
            name: value for name, value in payload.items() if name in parameters
        }

        return executor(**accepted_payload)

    positional_parameters = [
        parameter
        for parameter in parameters.values()
        if parameter.kind
        in (
            inspect.Parameter.POSITIONAL_ONLY,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
        )
    ]

    if len(positional_parameters) == 1:
        return executor(route)

    raise ResearchExecutorContractError(
        "O executor precisa aceitar route ou um único argumento posicional."
    )


def _validate_route_step_alignment(
    *,
    route: ResearchRoute,
    step: ResearchSubquery,
) -> None:
    route_tool_name = getattr(
        route,
        "tool_name",
        None,
    )

    if route_tool_name is not None and str(route_tool_name) != step.tool_name:
        raise ResearchRoutingContractError(
            "O Router retornou ferramenta diferente da etapa planejada."
        )

    route_step_id = getattr(
        route,
        "step_id",
        None,
    )

    if route_step_id is not None and str(route_step_id) != step.step_id:
        raise ResearchRoutingContractError(
            "O Router retornou step_id diferente da etapa planejada."
        )

    route_source = getattr(
        route,
        "source",
        None,
    )

    if route_source is not None:
        route_source_value = getattr(
            route_source,
            "value",
            route_source,
        )

        if str(route_source_value) != step.source.value:
            raise ResearchRoutingContractError(
                "O Router retornou fonte diferente da etapa planejada."
            )


def _raise_for_reported_tool_error(
    tool_result: Any,
) -> None:
    output = getattr(
        tool_result,
        "output",
        None,
    )

    error = getattr(
        tool_result,
        "error",
        None,
    )

    if output is not None or error is None:
        return

    code = getattr(
        error,
        "code",
        None,
    )

    if not code and isinstance(error, dict):
        code = error.get("code")

    raise ToolRuntimeReportedError(str(code or "tool_runtime_error"))


def _failed_collection(
    *,
    step: ResearchSubquery,
    round_number: int,
    error_code: str,
    warning: str,
    retryable: bool,
) -> EvidenceCollectionResult:
    fingerprint = "|".join(
        [
            step.step_id,
            step.source.value,
            step.tool_name,
            str(round_number),
            error_code,
        ]
    )

    return EvidenceCollectionResult(
        step=step,
        status=(EvidenceCollectionStatus.REJECTED),
        evidence=[],
        tool_answer="",
        source_schema=("ResearchAgentExecutionFailure"),
        output_sha256=content_sha256(fingerprint),
        raw_item_count=0,
        selected_count=0,
        discarded_count=0,
        warnings=[warning],
        metadata={
            "research_agent_version": (RESEARCH_AGENT_VERSION),
            "round_number": round_number,
            "error_code": error_code,
            "retryable_error": retryable,
            "content_logged": False,
            "live_call_performed": False,
        },
    )


def _step_evidence(
    *,
    step_id: str,
    collections: list[EvidenceCollectionResult],
) -> list[EvidenceItem]:
    return [
        evidence
        for collection in collections
        for evidence in collection.evidence
        if evidence.step_id == step_id
    ]


def _step_quality(
    *,
    step: ResearchSubquery,
    collections: list[EvidenceCollectionResult],
) -> tuple[
    int,
    float,
    float,
]:
    evidence = _step_evidence(
        step_id=step.step_id,
        collections=collections,
    )

    if not evidence:
        return (
            0,
            0.0,
            0.0,
        )

    relevance = max(item.relevance_score for item in evidence)

    reference_coverage = sum(bool(item.references) for item in evidence) / len(evidence)

    return (
        len(evidence),
        relevance,
        reference_coverage,
    )


def _semantic_retry_step_ids(
    *,
    plan: ResearchPlan,
    assessment: SufficiencyAssessment,
    collections: list[EvidenceCollectionResult],
) -> set[str]:
    retry_step_ids: set[str] = set()

    source_gaps: set[ResearchSource] = set()

    global_quality_gap = False

    for gap in assessment.gaps:
        if gap.step_id:
            retry_step_ids.add(gap.step_id)

        if gap.gap_type == EvidenceGapType.SOURCE_MISSING and gap.source is not None:
            source_gaps.add(gap.source)

        if gap.gap_type in {
            EvidenceGapType.LOW_EVIDENCE_VOLUME,
            EvidenceGapType.LOW_RELEVANCE,
            EvidenceGapType.MISSING_REFERENCES,
            EvidenceGapType.SCORE_BELOW_THRESHOLD,
        }:
            global_quality_gap = True

    for step in plan.subqueries:
        if step.source in source_gaps:
            retry_step_ids.add(step.step_id)

    if global_quality_gap and not retry_step_ids:
        required_steps = [step for step in plan.subqueries if step.required]

        ranked = sorted(
            required_steps,
            key=lambda step: (
                _step_quality(
                    step=step,
                    collections=collections,
                ),
                step.priority,
            ),
        )

        if ranked:
            retry_step_ids.add(ranked[0].step_id)

    if not retry_step_ids:
        successful_step_ids = {
            collection.step.step_id
            for collection in collections
            if (
                collection.status == EvidenceCollectionStatus.COLLECTED
                and collection.evidence
            )
        }

        retry_step_ids.update(
            step.step_id
            for step in plan.subqueries
            if (step.required and step.step_id not in successful_step_ids)
        )

    return retry_step_ids


def _select_semantic_retry_steps(
    *,
    plan: ResearchPlan,
    assessment: SufficiencyAssessment,
    collections: list[EvidenceCollectionResult],
    policy: ResearchExecutionPolicy,
) -> list[ResearchSubquery]:
    retry_ids = _semantic_retry_step_ids(
        plan=plan,
        assessment=assessment,
        collections=collections,
    )

    return [
        step
        for step in plan.subqueries
        if (
            step.step_id in retry_ids
            and (not policy.retry_required_steps_only or step.required)
        )
    ]


def _build_round_plan(
    *,
    original_plan: ResearchPlan,
    steps: list[ResearchSubquery],
    round_number: int,
) -> ResearchPlan:
    return original_plan.model_copy(
        update={
            "subqueries": steps,
            "metadata": {
                **original_plan.metadata,
                "research_round": round_number,
                "research_agent_version": (RESEARCH_AGENT_VERSION),
            },
        },
        deep=True,
    )


def _round_summary(
    *,
    round_number: int,
    planned_steps: list[ResearchSubquery],
    round_collections: list[EvidenceCollectionResult],
    assessment: SufficiencyAssessment,
    retry_steps: list[ResearchSubquery],
    tool_call_count: int,
    technical_retry_count: int,
) -> ResearchRoundSummary:
    successful = [
        collection.step.step_id
        for collection in round_collections
        if (
            collection.status == EvidenceCollectionStatus.COLLECTED
            and collection.evidence
        )
    ]

    rejected = [
        collection.step.step_id
        for collection in round_collections
        if (collection.status == EvidenceCollectionStatus.REJECTED)
    ]

    return ResearchRoundSummary(
        round_number=round_number,
        planned_step_ids=[step.step_id for step in planned_steps],
        executed_step_ids=[collection.step.step_id for collection in round_collections],
        successful_step_ids=list(dict.fromkeys(successful)),
        rejected_step_ids=list(dict.fromkeys(rejected)),
        semantic_retry_step_ids=[step.step_id for step in retry_steps],
        evidence_count=sum(
            len(collection.evidence) for collection in round_collections
        ),
        tool_call_count=tool_call_count,
        technical_retry_count=(technical_retry_count),
        sufficiency_score=assessment.score,
        sufficient=assessment.sufficient,
    )


def _result_metadata(
    *,
    plan: ResearchPlan,
    policy: ResearchExecutionPolicy,
    effective_max_rounds: int,
) -> dict[str, Any]:
    return {
        "research_agent_version": (RESEARCH_AGENT_VERSION),
        "planner_recommended_rounds": (plan.max_rounds),
        "execution_round_limit": (policy.max_rounds),
        "effective_semantic_round_limit": (effective_max_rounds),
        "max_attempts_per_step_per_round": (policy.max_attempts_per_step),
        "max_tool_calls": (policy.max_tool_calls),
        "max_total_duration_ms": (policy.max_total_duration_ms),
        "max_consecutive_failures": (policy.max_consecutive_failures),
        "technical_retry_is_semantic_round": (False),
        "content_logged": False,
    }


def _build_result(
    *,
    status: ResearchAgentStatus,
    stop_reason: ResearchStopReason,
    trace_id: str,
    plan: ResearchPlan,
    collections: list[EvidenceCollectionResult],
    assessment: SufficiencyAssessment,
    rounds: list[ResearchRoundSummary],
    retry_events: list[TechnicalRetryEvent],
    total_tool_calls: int,
    started_at: float,
    clock: ClockFunction,
    attempts: dict[str, int],
    error_codes: list[str],
    runtime_executor_used: bool,
    policy: ResearchExecutionPolicy,
    effective_max_rounds: int,
) -> ResearchAgentResult:
    return ResearchAgentResult(
        status=status,
        stop_reason=stop_reason,
        trace_id=trace_id,
        plan=plan,
        collections=collections,
        assessment=assessment,
        rounds=rounds,
        retry_events=retry_events,
        total_tool_calls=total_tool_calls,
        technical_retry_count=sum(event.retry_scheduled for event in retry_events),
        duration_ms=round(
            _elapsed_ms(
                started_at=started_at,
                clock=clock,
            ),
            3,
        ),
        attempted_steps=dict(attempts),
        error_codes=list(dict.fromkeys(error_codes)),
        runtime_executor_used=(runtime_executor_used),
        metadata=_result_metadata(
            plan=plan,
            policy=policy,
            effective_max_rounds=(effective_max_rounds),
        ),
    )


def run_research_agent(
    *,
    plan: ResearchPlan,
    executor: RouteExecutor,
    policy: (ResearchExecutionPolicy | None) = None,
    user_id: str | None = None,
    session_id: str | None = None,
    trace_id: str | None = None,
    runtime_executor_used: bool = False,
    sleep_fn: SleepFunction = time.sleep,
    monotonic_clock: ClockFunction = (time.monotonic),
) -> ResearchAgentResult:
    """
    Executa pesquisa com duas camadas separadas:

    technical retry:
        ocorre dentro da mesma rodada.

    semantic retry:
        abre outra rodada somente depois da
        avaliação de suficiência.
    """

    if not callable(executor):
        raise ResearchExecutorContractError("O executor informado não é chamável.")

    if not callable(sleep_fn):
        raise ResearchExecutorContractError("sleep_fn precisa ser chamável.")

    if not callable(monotonic_clock):
        raise ResearchExecutorContractError("monotonic_clock precisa ser chamável.")

    effective_policy = policy or ResearchExecutionPolicy()

    effective_trace_id = _trace_id(trace_id)

    effective_max_rounds = min(
        int(plan.max_rounds),
        int(effective_policy.max_rounds),
    )

    assessment_plan = (
        plan
        if (plan.max_rounds == effective_max_rounds)
        else plan.model_copy(
            update={
                "max_rounds": (effective_max_rounds),
            },
            deep=True,
        )
    )

    started_at = float(monotonic_clock())

    all_collections: list[EvidenceCollectionResult] = []

    round_summaries: list[ResearchRoundSummary] = []

    retry_events: list[TechnicalRetryEvent] = []

    attempts: dict[str, int] = defaultdict(int)

    error_codes: list[str] = []

    total_tool_calls = 0
    consecutive_failures = 0

    pending_steps = list(plan.subqueries)

    fatal_stop_reason: ResearchStopReason | None = None

    budget_exhausted = False
    duration_exhausted = False
    consecutive_failure_exhausted = False
    technical_attempts_exhausted = False

    assessment: SufficiencyAssessment | None = None

    for round_number in range(
        1,
        effective_max_rounds + 1,
    ):
        if not pending_steps:
            break

        if _duration_exhausted(
            started_at=started_at,
            clock=monotonic_clock,
            policy=effective_policy,
        ):
            duration_exhausted = True
            break

        round_plan = _build_round_plan(
            original_plan=plan,
            steps=pending_steps,
            round_number=round_number,
        )

        try:
            routes = _call_router(
                plan=round_plan,
                user_id=user_id,
                session_id=session_id,
                trace_id=effective_trace_id,
            )

            routes = _align_routes_to_steps(
                routes=routes,
                steps=pending_steps,
            )

        except Exception as exc:
            error_codes.append(_safe_error_code(exc))

            fatal_stop_reason = ResearchStopReason.ROUTING_CONTRACT_ERROR

            break

        round_collections: list[EvidenceCollectionResult] = []

        round_tool_calls = 0
        round_technical_retries = 0

        for step, route in zip(
            pending_steps,
            routes,
            strict=True,
        ):
            try:
                _validate_route_step_alignment(
                    route=route,
                    step=step,
                )

            except ResearchRoutingContractError as exc:
                error_code = _safe_error_code(exc)

                error_codes.append(error_code)

                round_collections.append(
                    _failed_collection(
                        step=step,
                        round_number=round_number,
                        error_code=error_code,
                        warning=("routing_contract_error"),
                        retryable=False,
                    )
                )

                fatal_stop_reason = ResearchStopReason.ROUTING_CONTRACT_ERROR

                break

            final_collection: EvidenceCollectionResult | None = None

            for attempt_number in range(
                1,
                effective_policy.max_attempts_per_step + 1,
            ):
                if total_tool_calls >= effective_policy.max_tool_calls:
                    budget_exhausted = True
                    break

                if _duration_exhausted(
                    started_at=started_at,
                    clock=monotonic_clock,
                    policy=effective_policy,
                ):
                    duration_exhausted = True
                    break

                attempts[step.step_id] += 1

                total_step_attempt = attempts[step.step_id]

                total_tool_calls += 1
                round_tool_calls += 1

                try:
                    tool_result = _invoke_executor(
                        executor,
                        route=route,
                        step=step,
                        round_number=(round_number),
                        attempt_number=(attempt_number),
                        total_attempt_number=(total_step_attempt),
                        trace_id=(effective_trace_id),
                    )

                    _raise_for_reported_tool_error(tool_result)

                    final_collection = collect_evidence_from_tool_result(
                        step=step,
                        tool_result=tool_result,
                    )

                    consecutive_failures = 0
                    break

                except Exception as exc:
                    consecutive_failures += 1

                    (
                        disposition,
                        error_code,
                    ) = _classify_failure(
                        exc,
                        policy=effective_policy,
                    )

                    error_codes.append(error_code)

                    has_attempt_remaining = (
                        attempt_number < effective_policy.max_attempts_per_step
                    )

                    call_budget_remaining = (
                        total_tool_calls < effective_policy.max_tool_calls
                    )

                    duration_remaining = not (
                        _duration_exhausted(
                            started_at=started_at,
                            clock=monotonic_clock,
                            policy=effective_policy,
                        )
                    )

                    failure_budget_remaining = (
                        consecutive_failures < effective_policy.max_consecutive_failures
                    )

                    retry_scheduled = bool(
                        disposition == RetryDisposition.RETRYABLE
                        and has_attempt_remaining
                        and call_budget_remaining
                        and duration_remaining
                        and failure_budget_remaining
                    )

                    backoff_ms = (
                        _retry_backoff_ms(
                            policy=effective_policy,
                            attempt_number=(attempt_number),
                        )
                        if retry_scheduled
                        else 0
                    )

                    retry_events.append(
                        TechnicalRetryEvent(
                            round_number=(round_number),
                            step_id=step.step_id,
                            attempt_number=(attempt_number),
                            total_step_attempt=(total_step_attempt),
                            error_code=(error_code),
                            disposition=(disposition),
                            retry_scheduled=(retry_scheduled),
                            backoff_ms=backoff_ms,
                        )
                    )

                    if retry_scheduled:
                        round_technical_retries += 1

                        if backoff_ms > 0:
                            sleep_fn(backoff_ms / 1000.0)

                        continue

                    final_collection = _failed_collection(
                        step=step,
                        round_number=(round_number),
                        error_code=(error_code),
                        warning=(
                            "technical_attempts_exhausted"
                            if (
                                disposition == RetryDisposition.RETRYABLE
                                and not has_attempt_remaining
                            )
                            else ("non_retryable_tool_failure")
                        ),
                        retryable=(disposition == RetryDisposition.RETRYABLE),
                    )

                    if (
                        disposition == RetryDisposition.FATAL
                        and effective_policy.stop_on_contract_error
                    ):
                        fatal_stop_reason = ResearchStopReason.EXECUTOR_CONTRACT_ERROR

                    elif (
                        disposition == RetryDisposition.NON_RETRYABLE
                        and not effective_policy.continue_after_nonretryable_tool_failure
                    ):
                        fatal_stop_reason = ResearchStopReason.INTERNAL_ERROR

                    if (
                        disposition == RetryDisposition.RETRYABLE
                        and not has_attempt_remaining
                    ):
                        technical_attempts_exhausted = True

                    if (
                        consecutive_failures
                        >= effective_policy.max_consecutive_failures
                    ):
                        consecutive_failure_exhausted = True

                    break

            if final_collection is not None:
                round_collections.append(final_collection)

            if (
                fatal_stop_reason is not None
                or budget_exhausted
                or duration_exhausted
                or consecutive_failure_exhausted
            ):
                break

        all_collections.extend(round_collections)

        assessment = assess_evidence_sufficiency(
            question=(plan.original_question),
            plan=assessment_plan,
            collections=(all_collections),
            round_number=round_number,
        )

        if assessment.sufficient:
            retry_steps: list[ResearchSubquery] = []

        else:
            retry_steps = _select_semantic_retry_steps(
                plan=plan,
                assessment=assessment,
                collections=(all_collections),
                policy=effective_policy,
            )

        round_summaries.append(
            _round_summary(
                round_number=round_number,
                planned_steps=pending_steps,
                round_collections=(round_collections),
                assessment=assessment,
                retry_steps=retry_steps,
                tool_call_count=(round_tool_calls),
                technical_retry_count=(round_technical_retries),
            )
        )

        if assessment.sufficient:
            return _build_result(
                status=(ResearchAgentStatus.SUCCEEDED),
                stop_reason=(ResearchStopReason.SUFFICIENT),
                trace_id=effective_trace_id,
                plan=plan,
                collections=all_collections,
                assessment=assessment,
                rounds=round_summaries,
                retry_events=retry_events,
                total_tool_calls=total_tool_calls,
                started_at=started_at,
                clock=monotonic_clock,
                attempts=dict(attempts),
                error_codes=error_codes,
                runtime_executor_used=(runtime_executor_used),
                policy=effective_policy,
                effective_max_rounds=(effective_max_rounds),
            )

        if (
            fatal_stop_reason is not None
            or budget_exhausted
            or duration_exhausted
            or consecutive_failure_exhausted
        ):
            break

        if round_number >= effective_max_rounds:
            break

        if not retry_steps:
            break

        pending_steps = retry_steps

    if assessment is None:
        assessment_round = max(
            1,
            min(
                effective_max_rounds,
                assessment_plan.max_rounds,
            ),
        )

        assessment = assess_evidence_sufficiency(
            question=(plan.original_question),
            plan=assessment_plan,
            collections=all_collections,
            round_number=assessment_round,
        )

    if fatal_stop_reason is not None:
        status = ResearchAgentStatus.FAILED
        stop_reason = fatal_stop_reason

    elif budget_exhausted:
        status = ResearchAgentStatus.EXHAUSTED

        stop_reason = ResearchStopReason.TOOL_CALL_BUDGET_EXHAUSTED

    elif duration_exhausted:
        status = ResearchAgentStatus.EXHAUSTED

        stop_reason = ResearchStopReason.DURATION_BUDGET_EXHAUSTED

    elif consecutive_failure_exhausted:
        status = ResearchAgentStatus.EXHAUSTED

        stop_reason = ResearchStopReason.CONSECUTIVE_FAILURE_LIMIT_REACHED

    elif technical_attempts_exhausted and (
        not round_summaries or len(round_summaries) >= effective_max_rounds
    ):
        status = ResearchAgentStatus.EXHAUSTED

        stop_reason = ResearchStopReason.ATTEMPT_LIMIT_REACHED

    elif round_summaries and len(round_summaries) >= effective_max_rounds:
        status = ResearchAgentStatus.EXHAUSTED

        stop_reason = ResearchStopReason.MAX_ROUNDS_REACHED

    else:
        status = ResearchAgentStatus.EXHAUSTED

        stop_reason = ResearchStopReason.NO_RETRYABLE_GAPS

    return _build_result(
        status=status,
        stop_reason=stop_reason,
        trace_id=effective_trace_id,
        plan=plan,
        collections=all_collections,
        assessment=assessment,
        rounds=round_summaries,
        retry_events=retry_events,
        total_tool_calls=total_tool_calls,
        started_at=started_at,
        clock=monotonic_clock,
        attempts=dict(attempts),
        error_codes=error_codes,
        runtime_executor_used=(runtime_executor_used),
        policy=effective_policy,
        effective_max_rounds=(effective_max_rounds),
    )


def create_runtime_route_executor(
    *,
    user_id: str | None = None,
    session_id: str | None = None,
    trace_id: str | None = None,
    tool_executor: (Callable[[Any], Any] | None) = None,
    routed_tool_target: (Callable[..., Any] | None) = None,
) -> RouteExecutor:
    """
    Cria um adaptador para o executor governado real.

    O contexto operacional é capturado no momento da
    criação do adaptador e propagado explicitamente:

    - user_id;
    - session_id;
    - trace_id;
    - executor de ToolCall opcional.

    routed_tool_target permite testes de contrato sem
    chamar RAG, Gemini, Neon ou serviços de rede.
    """

    if routed_tool_target is None:
        from inna_ai.retrieval.agentic.router import execute_routed_tool

        target = execute_routed_tool

    else:
        target = routed_tool_target

    if not callable(target):
        raise ResearchExecutorContractError("O executor de rota não é chamável.")

    bound_trace_id = _trace_id(trace_id)

    def runtime_executor(
        *,
        route: ResearchRoute,
        trace_id: str | None = None,
        **_: Any,
    ) -> Any:
        invocation_trace_id = _trace_id(trace_id or bound_trace_id)

        try:
            signature = inspect.signature(target)

        except (TypeError, ValueError) as exc:
            raise ResearchExecutorContractError(
                "Não foi possível inspecionar o executor governado."
            ) from exc

        parameters = signature.parameters

        accepts_kwargs = any(
            parameter.kind == inspect.Parameter.VAR_KEYWORD
            for parameter in parameters.values()
        )

        route_parameter = parameters.get("route")

        payload: dict[str, Any] = {
            "route": route,
            "user_id": user_id,
            "session_id": session_id,
            "trace_id": (invocation_trace_id),
        }

        if "executor" in parameters or accepts_kwargs:
            payload["executor"] = tool_executor

        unsupported_positional_only = [
            name
            for name, parameter in parameters.items()
            if (
                parameter.kind == inspect.Parameter.POSITIONAL_ONLY
                and name != "route"
                and parameter.default is inspect.Parameter.empty
            )
        ]

        if unsupported_positional_only:
            raise ResearchExecutorContractError(
                "O executor governado possui "
                "parâmetros posicionais obrigatórios "
                "não suportados: " + ",".join(unsupported_positional_only)
            )

        required_names = [
            name
            for name, parameter in parameters.items()
            if (
                parameter.kind
                not in (
                    inspect.Parameter.VAR_POSITIONAL,
                    inspect.Parameter.VAR_KEYWORD,
                )
                and parameter.default is inspect.Parameter.empty
            )
        ]

        missing_required = [name for name in required_names if name not in payload]

        if missing_required:
            raise ResearchExecutorContractError(
                "O adaptador não conseguiu resolver "
                "os parâmetros obrigatórios: " + ",".join(missing_required)
            )

        if accepts_kwargs:
            accepted_payload = payload

        else:
            accepted_payload = {
                name: value for name, value in payload.items() if name in parameters
            }

        if (
            route_parameter is not None
            and route_parameter.kind == inspect.Parameter.POSITIONAL_ONLY
        ):
            accepted_payload.pop(
                "route",
                None,
            )

            return target(
                route,
                **accepted_payload,
            )

        return target(**accepted_payload)

    return runtime_executor


def run_research_agent_with_runtime(
    *,
    plan: ResearchPlan,
    policy: (ResearchExecutionPolicy | None) = None,
    user_id: str | None = None,
    session_id: str | None = None,
    trace_id: str | None = None,
    tool_executor: (Callable[[Any], Any] | None) = None,
    routed_tool_target: (Callable[..., Any] | None) = None,
) -> ResearchAgentResult:
    """
    Executa o Research Agent pelo runtime governado.

    O mesmo trace_id é usado pelo Research Agent,
    Router Agent e executor de ferramentas.

    routed_tool_target é um ponto de injeção destinado
    a testes de contrato. Quando não informado, utiliza
    execute_routed_tool real.
    """

    effective_trace_id = _trace_id(trace_id)

    runtime_executor = create_runtime_route_executor(
        user_id=user_id,
        session_id=session_id,
        trace_id=effective_trace_id,
        tool_executor=tool_executor,
        routed_tool_target=(routed_tool_target),
    )

    return run_research_agent(
        plan=plan,
        executor=runtime_executor,
        policy=policy,
        user_id=user_id,
        session_id=session_id,
        trace_id=effective_trace_id,
        runtime_executor_used=True,
    )


def research_result_to_audit_payload(
    result: ResearchAgentResult,
) -> dict[str, Any]:
    """
    Auditoria sem conteúdo ou identidade.
    """

    return {
        "event": ("agentic_rag_research_completed"),
        "research_agent_version": (RESEARCH_AGENT_VERSION),
        "status": result.status.value,
        "stop_reason": (result.stop_reason.value),
        "trace_id": result.trace_id,
        "semantic_round_count": len(result.rounds),
        "total_tool_calls": (result.total_tool_calls),
        "technical_retry_count": (result.technical_retry_count),
        "duration_ms": result.duration_ms,
        "collection_count": len(result.collections),
        "successful_collection_count": sum(
            (
                collection.status == EvidenceCollectionStatus.COLLECTED
                and bool(collection.evidence)
            )
            for collection in result.collections
        ),
        "rejected_collection_count": sum(
            (collection.status == EvidenceCollectionStatus.REJECTED)
            for collection in result.collections
        ),
        "attempted_step_count": len(result.attempted_steps),
        "error_codes": list(result.error_codes),
        "runtime_executor_used": (result.runtime_executor_used),
        "assessment": (assessment_to_audit_payload(result.assessment)),
        "content_logged": False,
        "identity_logged": False,
    }


class IterativeResearchAgent:
    """
    Fachada orientada a objeto.
    """

    def __init__(
        self,
        *,
        executor: RouteExecutor,
        policy: (ResearchExecutionPolicy | None) = None,
        runtime_executor_used: bool = False,
        sleep_fn: SleepFunction = time.sleep,
        monotonic_clock: ClockFunction = (time.monotonic),
    ) -> None:
        if not callable(executor):
            raise ResearchExecutorContractError("O executor informado não é chamável.")

        self._executor = executor

        self._policy = policy or ResearchExecutionPolicy()

        self._runtime_executor_used = runtime_executor_used

        self._sleep_fn = sleep_fn

        self._monotonic_clock = monotonic_clock

    def run(
        self,
        *,
        plan: ResearchPlan,
        user_id: str | None = None,
        session_id: str | None = None,
        trace_id: str | None = None,
    ) -> ResearchAgentResult:
        return run_research_agent(
            plan=plan,
            executor=self._executor,
            policy=self._policy,
            user_id=user_id,
            session_id=session_id,
            trace_id=trace_id,
            runtime_executor_used=(self._runtime_executor_used),
            sleep_fn=self._sleep_fn,
            monotonic_clock=(self._monotonic_clock),
        )


__all__ = [
    "RESEARCH_AGENT_VERSION",
    "ClockFunction",
    "IterativeResearchAgent",
    "ResearchAgentResult",
    "ResearchAgentStatus",
    "ResearchExecutionError",
    "ResearchExecutionPolicy",
    "ResearchExecutorContractError",
    "ResearchRoundSummary",
    "ResearchRoutingContractError",
    "ResearchStopReason",
    "RetryDisposition",
    "RouteExecutor",
    "SleepFunction",
    "TechnicalRetryEvent",
    "ToolRuntimeReportedError",
    "create_runtime_route_executor",
    "research_result_to_audit_payload",
    "run_research_agent",
    "run_research_agent_with_runtime",
]
