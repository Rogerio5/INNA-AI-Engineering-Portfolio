from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from time import perf_counter
from types import MappingProxyType
from typing import Any
from uuid import uuid4

from inna_ai.evaluation.contracts import InnaEvaluationCase
from inna_ai.evaluation.deepeval_integration import DeepEvalCasePayload, DeepEvalSettings, ensure_external_case_allowed
from inna_ai.evaluation.deepeval_metrics import MetricDefinition, MetricExecutionMode, MetricInputValidationError, MetricRegistry, MetricSelection, build_default_metric_registry

MetricExecutor = Callable[
    [MetricDefinition, InnaEvaluationCase, DeepEvalCasePayload],
    "MetricExecutionOutput",
]


class EvaluationRunMode(StrEnum):
    """Modo de execução de uma avaliação."""

    DRY_RUN = "dry-run"
    LOCAL = "local"
    LIVE = "live"


class MetricRunStatus(StrEnum):
    """Resultado normalizado da execução de uma métrica."""

    PLANNED = "planned"
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    BLOCKED = "blocked"
    ERROR = "error"


class EvaluationRunStatus(StrEnum):
    """Resultado agregado de uma execução."""

    PLANNED = "planned"
    PASSED = "passed"
    FAILED = "failed"
    PARTIAL = "partial"
    BLOCKED = "blocked"
    ERROR = "error"


class EvaluationRunnerError(RuntimeError):
    """Erro base do runner."""


class EvaluationBudgetError(EvaluationRunnerError):
    """Limite de custo da avaliação excedido."""


class MetricExecutorNotFoundError(
    EvaluationRunnerError,
    KeyError,
):
    """Executor local não registrado."""


@dataclass(frozen=True, slots=True)
class MetricExecutionOutput:
    """
    Saída neutra retornada por um executor de métrica.

    Executors não devem lançar exceções para falhas esperadas da
    avaliação. Uma reprovação normal deve ser representada com
    passed=False.
    """

    passed: bool
    score: float | None = None
    reason: str | None = None
    estimated_cost: float = 0.0
    metadata: Mapping[str, Any] = field(
        default_factory=dict
    )

    def __post_init__(self) -> None:
        if self.score is not None and not (
            0.0 <= float(self.score) <= 1.0
        ):
            raise ValueError(
                "MetricExecutionOutput.score deve estar "
                "entre 0 e 1."
            )

        estimated_cost = float(
            self.estimated_cost
        )

        if estimated_cost < 0:
            raise ValueError(
                "estimated_cost não pode ser negativo."
            )

        object.__setattr__(
            self,
            "score",
            (
                None
                if self.score is None
                else float(self.score)
            ),
        )
        object.__setattr__(
            self,
            "reason",
            _optional_text(self.reason),
        )
        object.__setattr__(
            self,
            "estimated_cost",
            estimated_cost,
        )
        object.__setattr__(
            self,
            "metadata",
            MappingProxyType(
                dict(self.metadata)
            ),
        )


@dataclass(frozen=True, slots=True)
class MetricRunResult:
    metric_id: str
    status: MetricRunStatus
    execution_mode: MetricExecutionMode
    score: float | None
    threshold: float | None
    passed: bool | None
    reason: str | None
    duration_ms: float
    estimated_cost: float
    error_type: str | None = None
    metadata: Mapping[str, Any] = field(
        default_factory=dict
    )

    def __post_init__(self) -> None:
        if self.duration_ms < 0:
            raise ValueError(
                "duration_ms não pode ser negativo."
            )

        if self.estimated_cost < 0:
            raise ValueError(
                "estimated_cost não pode ser negativo."
            )

        object.__setattr__(
            self,
            "metadata",
            MappingProxyType(
                dict(self.metadata)
            ),
        )


@dataclass(frozen=True, slots=True)
class EvaluationRunResult:
    run_id: str
    case_id: str
    dataset_id: str
    category: str
    profile_id: str
    mode: EvaluationRunMode
    status: EvaluationRunStatus
    metric_results: tuple[MetricRunResult, ...]
    started_at: datetime
    finished_at: datetime
    duration_ms: float
    total_estimated_cost: float
    external_run: bool
    deepeval_live_enabled: bool
    metadata: Mapping[str, Any] = field(
        default_factory=dict
    )

    def __post_init__(self) -> None:
        if not self.run_id.strip():
            raise ValueError(
                "run_id não pode ser vazio."
            )

        if self.started_at.tzinfo is None:
            raise ValueError(
                "started_at precisa de timezone."
            )

        if self.finished_at.tzinfo is None:
            raise ValueError(
                "finished_at precisa de timezone."
            )

        if self.finished_at < self.started_at:
            raise ValueError(
                "finished_at não pode ser anterior "
                "a started_at."
            )

        object.__setattr__(
            self,
            "metadata",
            MappingProxyType(
                dict(self.metadata)
            ),
        )

    @property
    def metric_count(self) -> int:
        return len(self.metric_results)

    @property
    def passed_count(self) -> int:
        return sum(
            result.status == MetricRunStatus.PASSED
            for result in self.metric_results
        )

    @property
    def failed_count(self) -> int:
        return sum(
            result.status == MetricRunStatus.FAILED
            for result in self.metric_results
        )

    @property
    def error_count(self) -> int:
        return sum(
            result.status == MetricRunStatus.ERROR
            for result in self.metric_results
        )

    @property
    def blocked_count(self) -> int:
        return sum(
            result.status == MetricRunStatus.BLOCKED
            for result in self.metric_results
        )

    @property
    def skipped_count(self) -> int:
        return sum(
            result.status == MetricRunStatus.SKIPPED
            for result in self.metric_results
        )


    @property
    def rag_triad(self):
        """
        Consolida as métricas oficiais da RAG Triad.

        Retorna None quando a execução não possui nenhuma
        métrica pertencente à tríade.
        """

        from inna_ai.evaluation.rag_triad import RAG_TRIAD_METRIC_IDS, aggregate_rag_triad

        triad_metric_ids = frozenset(
            RAG_TRIAD_METRIC_IDS
        )

        if not any(
            result.metric_id.strip().lower()
            in triad_metric_ids
            for result in self.metric_results
        ):
            return None

        return aggregate_rag_triad(
            self.metric_results,
            metadata={
                "run_id": self.run_id,
                "case_id": self.case_id,
                "dataset_id": self.dataset_id,
                "category": self.category,
                "profile_id": self.profile_id,
                "mode": self.mode.value,
                "run_status": self.status.value,
            },
        )

    @property
    def rag_triad_payload(
        self,
    ) -> dict[str, Any] | None:
        """
        Retorna a representação serializável da RAG Triad.
        """

        triad = self.rag_triad

        if triad is None:
            return None

        return triad.to_dict()


@dataclass(frozen=True, slots=True)
class EvaluationRunnerSettings:
    mode: EvaluationRunMode = EvaluationRunMode.DRY_RUN
    continue_on_metric_error: bool = True
    include_live_metrics: bool = False
    external_run: bool = False
    maximum_total_cost: float = 0.0

    def __post_init__(self) -> None:
        maximum_total_cost = float(
            self.maximum_total_cost
        )

        if maximum_total_cost < 0:
            raise ValueError(
                "maximum_total_cost não pode ser negativo."
            )

        object.__setattr__(
            self,
            "maximum_total_cost",
            maximum_total_cost,
        )

        if (
            self.mode == EvaluationRunMode.LIVE
            and not self.include_live_metrics
        ):
            raise ValueError(
                "O modo LIVE exige "
                "include_live_metrics=True."
            )


class EvaluationRunner:
    """
    Orquestra avaliações locais, dry-run e live.

    O runner não conhece detalhes de implementação das métricas.
    Executors são registrados separadamente por metric_id.
    """

    def __init__(
        self,
        *,
        registry: MetricRegistry | None = None,
        deepeval_settings: DeepEvalSettings | None = None,
        executors: Mapping[str, MetricExecutor] | None = None,
    ) -> None:
        self._registry = (
            registry
            or build_default_metric_registry()
        )

        self._deepeval_settings = (
            deepeval_settings
            or DeepEvalSettings.from_environment()
        )

        self._executors: dict[
            str,
            MetricExecutor,
        ] = dict(executors or {})

    @property
    def registry(self) -> MetricRegistry:
        return self._registry

    @property
    def deepeval_settings(
        self,
    ) -> DeepEvalSettings:
        return self._deepeval_settings

    def register_executor(
        self,
        metric_id: str,
        executor: MetricExecutor,
        *,
        replace_existing: bool = False,
    ) -> None:
        normalized = metric_id.strip().casefold()

        self._registry.get(normalized)

        if (
            normalized in self._executors
            and not replace_existing
        ):
            raise EvaluationRunnerError(
                f"Executor da métrica {normalized!r} "
                "já registrado."
            )

        self._executors[normalized] = executor

    def build_selection(
        self,
        case: InnaEvaluationCase,
        settings: EvaluationRunnerSettings,
    ) -> MetricSelection:
        include_live = (
            settings.include_live_metrics
            or settings.mode
            == EvaluationRunMode.LIVE
        )

        return self._registry.for_case(
            case,
            include_live=include_live,
        )

    def run(
        self,
        case: InnaEvaluationCase,
        payload: DeepEvalCasePayload,
        *,
        settings: EvaluationRunnerSettings | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> EvaluationRunResult:
        resolved_settings = (
            settings or EvaluationRunnerSettings()
        )

        started_at = datetime.now(UTC)
        started_counter = perf_counter()
        run_id = uuid4().hex

        selection = self.build_selection(
            case,
            resolved_settings,
        )

        if resolved_settings.external_run:
            ensure_external_case_allowed(case)

        if resolved_settings.mode == EvaluationRunMode.LIVE:
            self._deepeval_settings.require_live_enabled()

        metric_results: list[
            MetricRunResult
        ] = []

        total_estimated_cost = 0.0

        for metric in selection.metrics:
            result = self._run_metric(
                metric=metric,
                case=case,
                payload=payload,
                settings=resolved_settings,
            )

            projected_cost = (
                total_estimated_cost
                + result.estimated_cost
            )

            if (
                resolved_settings.maximum_total_cost > 0
                and projected_cost
                > resolved_settings.maximum_total_cost
            ):
                metric_results.append(
                    MetricRunResult(
                        metric_id=metric.metric_id,
                        status=MetricRunStatus.BLOCKED,
                        execution_mode=(
                            metric.execution_mode
                        ),
                        score=None,
                        threshold=metric.threshold,
                        passed=None,
                        reason=(
                            "Limite total de custo excedido."
                        ),
                        duration_ms=0.0,
                        estimated_cost=0.0,
                        error_type=(
                            EvaluationBudgetError.__name__
                        ),
                    )
                )
                continue

            metric_results.append(result)
            total_estimated_cost = projected_cost

            if (
                result.status == MetricRunStatus.ERROR
                and not resolved_settings
                .continue_on_metric_error
            ):
                break

        duration_ms = (
            perf_counter() - started_counter
        ) * 1000

        finished_at = datetime.now(UTC)

        run_status = _aggregate_run_status(
            metric_results,
            mode=resolved_settings.mode,
        )

        return EvaluationRunResult(
            run_id=run_id,
            case_id=case.case_id,
            dataset_id=(
                f"{case.dataset_name}@"
                f"{case.dataset_version}"
            ),
            category=case.category,
            profile_id=selection.profile_id,
            mode=resolved_settings.mode,
            status=run_status,
            metric_results=tuple(
                metric_results
            ),
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=duration_ms,
            total_estimated_cost=(
                total_estimated_cost
            ),
            external_run=(
                resolved_settings.external_run
            ),
            deepeval_live_enabled=(
                self._deepeval_settings.live_enabled
            ),
            metadata=dict(metadata or {}),
        )

    def _run_metric(
        self,
        *,
        metric: MetricDefinition,
        case: InnaEvaluationCase,
        payload: DeepEvalCasePayload,
        settings: EvaluationRunnerSettings,
    ) -> MetricRunResult:
        started = perf_counter()

        if settings.mode == EvaluationRunMode.DRY_RUN:
            return _planned_result(
                metric,
                duration_ms=(
                    perf_counter() - started
                )
                * 1000,
            )

        if (
            metric.is_live
            and settings.mode
            != EvaluationRunMode.LIVE
        ):
            return _skipped_result(
                metric,
                reason=(
                    "Métrica live não executada "
                    "fora do modo LIVE."
                ),
                duration_ms=(
                    perf_counter() - started
                )
                * 1000,
            )

        try:
            metric.validate_payload(payload)
        except MetricInputValidationError as error:
            return _blocked_result(
                metric,
                reason=str(error),
                error_type=type(error).__name__,
                duration_ms=(
                    perf_counter() - started
                )
                * 1000,
            )

        executor = self._executors.get(
            metric.metric_id
        )

        if executor is None:
            return _skipped_result(
                metric,
                reason=(
                    "Executor ainda não registrado."
                ),
                error_type=(
                    MetricExecutorNotFoundError.__name__
                ),
                duration_ms=(
                    perf_counter() - started
                )
                * 1000,
            )

        try:
            output = executor(
                metric,
                case,
                payload,
            )
        except Exception as error:
            return MetricRunResult(
                metric_id=metric.metric_id,
                status=MetricRunStatus.ERROR,
                execution_mode=(
                    metric.execution_mode
                ),
                score=None,
                threshold=metric.threshold,
                passed=None,
                reason=str(error),
                duration_ms=(
                    perf_counter() - started
                )
                * 1000,
                estimated_cost=0.0,
                error_type=type(error).__name__,
            )

        status = (
            MetricRunStatus.PASSED
            if output.passed
            else MetricRunStatus.FAILED
        )

        return MetricRunResult(
            metric_id=metric.metric_id,
            status=status,
            execution_mode=metric.execution_mode,
            score=output.score,
            threshold=metric.threshold,
            passed=output.passed,
            reason=output.reason,
            duration_ms=(
                perf_counter() - started
            )
            * 1000,
            estimated_cost=(
                output.estimated_cost
            ),
            metadata=output.metadata,
        )


def _planned_result(
    metric: MetricDefinition,
    *,
    duration_ms: float,
) -> MetricRunResult:
    return MetricRunResult(
        metric_id=metric.metric_id,
        status=MetricRunStatus.PLANNED,
        execution_mode=metric.execution_mode,
        score=None,
        threshold=metric.threshold,
        passed=None,
        reason="Métrica incluída no plano dry-run.",
        duration_ms=duration_ms,
        estimated_cost=0.0,
    )


def _skipped_result(
    metric: MetricDefinition,
    *,
    reason: str,
    duration_ms: float,
    error_type: str | None = None,
) -> MetricRunResult:
    return MetricRunResult(
        metric_id=metric.metric_id,
        status=MetricRunStatus.SKIPPED,
        execution_mode=metric.execution_mode,
        score=None,
        threshold=metric.threshold,
        passed=None,
        reason=reason,
        duration_ms=duration_ms,
        estimated_cost=0.0,
        error_type=error_type,
    )


def _blocked_result(
    metric: MetricDefinition,
    *,
    reason: str,
    error_type: str,
    duration_ms: float,
) -> MetricRunResult:
    return MetricRunResult(
        metric_id=metric.metric_id,
        status=MetricRunStatus.BLOCKED,
        execution_mode=metric.execution_mode,
        score=None,
        threshold=metric.threshold,
        passed=None,
        reason=reason,
        duration_ms=duration_ms,
        estimated_cost=0.0,
        error_type=error_type,
    )


def _aggregate_run_status(
    results: list[MetricRunResult],
    *,
    mode: EvaluationRunMode,
) -> EvaluationRunStatus:
    if not results:
        return EvaluationRunStatus.ERROR

    if mode == EvaluationRunMode.DRY_RUN:
        return EvaluationRunStatus.PLANNED

    statuses = {
        result.status
        for result in results
    }

    if statuses == {
        MetricRunStatus.PASSED
    }:
        return EvaluationRunStatus.PASSED

    if MetricRunStatus.ERROR in statuses:
        return EvaluationRunStatus.PARTIAL

    if MetricRunStatus.FAILED in statuses:
        return EvaluationRunStatus.FAILED

    if MetricRunStatus.BLOCKED in statuses:
        return EvaluationRunStatus.BLOCKED

    if statuses.issubset(
        {
            MetricRunStatus.SKIPPED,
            MetricRunStatus.PLANNED,
        }
    ):
        return EvaluationRunStatus.PARTIAL

    return EvaluationRunStatus.PARTIAL


def _optional_text(
    value: str | None,
) -> str | None:
    if value is None:
        return None

    normalized = value.strip()

    return normalized or None


__all__ = [
    "EvaluationBudgetError",
    "EvaluationRunMode",
    "EvaluationRunResult",
    "EvaluationRunner",
    "EvaluationRunnerError",
    "EvaluationRunnerSettings",
    "EvaluationRunStatus",
    "MetricExecutionOutput",
    "MetricExecutor",
    "MetricExecutorNotFoundError",
    "MetricRunResult",
    "MetricRunStatus",
]
