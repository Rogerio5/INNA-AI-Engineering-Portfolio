from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType
from typing import Any

from inna_ai.evaluation.deepeval_runner import MetricRunResult, MetricRunStatus

RAG_TRIAD_METRIC_IDS = (
    "answer-relevancy",
    "faithfulness",
    "contextual-relevancy",
)


class RagTriadAggregationError(
    RuntimeError
):
    """Erro ao consolidar métricas da RAG Triad."""


class RagTriadStatus(StrEnum):
    """
    Estado consolidado da RAG Triad.

    PASSED:
        As três métricas foram executadas e aprovadas.

    FAILED:
        Pelo menos uma métrica foi executada e reprovada.

    BLOCKED:
        Nenhuma métrica reprovou, mas existe métrica bloqueada.

    ERROR:
        Nenhuma métrica reprovou ou foi bloqueada, mas ocorreu erro.

    PLANNED:
        As três métricas estão apenas planejadas em dry-run.

    PARTIAL:
        A tríade está incompleta ou possui métricas ignoradas.

    UNAVAILABLE:
        Nenhuma métrica da tríade foi encontrada.
    """

    PASSED = "passed"
    FAILED = "failed"
    BLOCKED = "blocked"
    ERROR = "error"
    PLANNED = "planned"
    PARTIAL = "partial"
    UNAVAILABLE = "unavailable"


@dataclass(
    frozen=True,
    slots=True,
)
class RagTriadAxisResult:
    """Resultado normalizado de um eixo da RAG Triad."""

    metric_id: str
    status: MetricRunStatus
    score: float | None
    threshold: float | None
    passed: bool | None
    reason: str | None
    duration_ms: float
    estimated_cost: float
    metadata: Mapping[str, Any] = field(
        default_factory=dict
    )

    def __post_init__(self) -> None:
        normalized_metric_id = (
            self.metric_id.strip().lower()
        )

        if (
            normalized_metric_id
            not in RAG_TRIAD_METRIC_IDS
        ):
            raise ValueError(
                "metric_id não pertence à RAG Triad."
            )

        if self.score is not None and not (
            0.0 <= float(self.score) <= 1.0
        ):
            raise ValueError(
                "score deve estar entre 0 e 1."
            )

        if self.threshold is not None and not (
            0.0 <= float(self.threshold) <= 1.0
        ):
            raise ValueError(
                "threshold deve estar entre 0 e 1."
            )

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
            "metric_id",
            normalized_metric_id,
        )
        object.__setattr__(
            self,
            "metadata",
            MappingProxyType(
                dict(self.metadata)
            ),
        )

    @classmethod
    def from_metric_result(
        cls,
        result: MetricRunResult,
    ) -> RagTriadAxisResult:
        return cls(
            metric_id=result.metric_id,
            status=result.status,
            score=result.score,
            threshold=result.threshold,
            passed=result.passed,
            reason=result.reason,
            duration_ms=result.duration_ms,
            estimated_cost=result.estimated_cost,
            metadata=result.metadata,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "metric_id": self.metric_id,
            "status": self.status.value,
            "score": self.score,
            "threshold": self.threshold,
            "passed": self.passed,
            "reason": self.reason,
            "duration_ms": self.duration_ms,
            "estimated_cost": self.estimated_cost,
            "metadata": dict(self.metadata),
        }


@dataclass(
    frozen=True,
    slots=True,
)
class RagTriadResult:
    """Resultado consolidado e auditável da RAG Triad."""

    status: RagTriadStatus
    axes: tuple[RagTriadAxisResult, ...]
    aggregate_score: float | None
    passed: bool | None
    missing_metric_ids: tuple[str, ...]
    failing_metric_ids: tuple[str, ...]
    total_duration_ms: float
    total_estimated_cost: float
    metadata: Mapping[str, Any] = field(
        default_factory=dict
    )

    def __post_init__(self) -> None:
        axis_ids = tuple(
            axis.metric_id
            for axis in self.axes
        )

        if len(axis_ids) != len(set(axis_ids)):
            raise ValueError(
                "A RAG Triad não aceita métricas duplicadas."
            )

        if self.aggregate_score is not None and not (
            0.0 <= self.aggregate_score <= 1.0
        ):
            raise ValueError(
                "aggregate_score deve estar entre 0 e 1."
            )

        if self.total_duration_ms < 0:
            raise ValueError(
                "total_duration_ms não pode ser negativo."
            )

        if self.total_estimated_cost < 0:
            raise ValueError(
                "total_estimated_cost não pode ser negativo."
            )

        object.__setattr__(
            self,
            "metadata",
            MappingProxyType(
                dict(self.metadata)
            ),
        )

    @property
    def is_complete(self) -> bool:
        return not self.missing_metric_ids

    @property
    def scores_by_metric(
        self,
    ) -> Mapping[str, float | None]:
        return MappingProxyType(
            {
                axis.metric_id: axis.score
                for axis in self.axes
            }
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "aggregate_score": (
                self.aggregate_score
            ),
            "passed": self.passed,
            "is_complete": self.is_complete,
            "missing_metric_ids": list(
                self.missing_metric_ids
            ),
            "failing_metric_ids": list(
                self.failing_metric_ids
            ),
            "total_duration_ms": (
                self.total_duration_ms
            ),
            "total_estimated_cost": (
                self.total_estimated_cost
            ),
            "axes": [
                axis.to_dict()
                for axis in self.axes
            ],
            "metadata": dict(self.metadata),
        }


def aggregate_rag_triad(
    metric_results: Iterable[MetricRunResult],
    *,
    require_complete: bool = False,
    metadata: Mapping[str, Any] | None = None,
) -> RagTriadResult:
    """
    Consolida os três eixos formais da RAG Triad.

    Apenas os IDs oficiais da tríade são considerados.
    O score consolidado é a média aritmética dos scores
    disponíveis. A aprovação exige que os três eixos estejam
    presentes e aprovados.
    """

    selected: dict[str, RagTriadAxisResult] = {}

    for result in metric_results:
        metric_id = result.metric_id.strip().lower()

        if metric_id not in RAG_TRIAD_METRIC_IDS:
            continue

        if metric_id in selected:
            raise RagTriadAggregationError(
                "Resultado duplicado para a métrica "
                f"{metric_id!r}."
            )

        selected[metric_id] = (
            RagTriadAxisResult.from_metric_result(
                result
            )
        )

    missing_metric_ids = tuple(
        metric_id
        for metric_id in RAG_TRIAD_METRIC_IDS
        if metric_id not in selected
    )

    if require_complete and missing_metric_ids:
        raise RagTriadAggregationError(
            "RAG Triad incompleta. Métricas ausentes: "
            + ", ".join(missing_metric_ids)
        )

    axes = tuple(
        selected[metric_id]
        for metric_id in RAG_TRIAD_METRIC_IDS
        if metric_id in selected
    )

    status = _resolve_triad_status(
        axes=axes,
        missing_metric_ids=missing_metric_ids,
    )

    scores = tuple(
        axis.score
        for axis in axes
        if axis.score is not None
    )

    aggregate_score = (
        None
        if not scores
        else sum(scores) / len(scores)
    )

    failing_metric_ids = tuple(
        axis.metric_id
        for axis in axes
        if axis.status
        in {
            MetricRunStatus.FAILED,
            MetricRunStatus.BLOCKED,
            MetricRunStatus.ERROR,
        }
    )

    passed: bool | None

    if status == RagTriadStatus.PASSED:
        passed = True
    elif status in {
        RagTriadStatus.FAILED,
        RagTriadStatus.BLOCKED,
        RagTriadStatus.ERROR,
    }:
        passed = False
    else:
        passed = None

    return RagTriadResult(
        status=status,
        axes=axes,
        aggregate_score=aggregate_score,
        passed=passed,
        missing_metric_ids=missing_metric_ids,
        failing_metric_ids=failing_metric_ids,
        total_duration_ms=sum(
            axis.duration_ms
            for axis in axes
        ),
        total_estimated_cost=sum(
            axis.estimated_cost
            for axis in axes
        ),
        metadata=dict(metadata or {}),
    )


def _resolve_triad_status(
    *,
    axes: tuple[RagTriadAxisResult, ...],
    missing_metric_ids: tuple[str, ...],
) -> RagTriadStatus:
    if not axes:
        return RagTriadStatus.UNAVAILABLE

    statuses = {
        axis.status
        for axis in axes
    }

    if MetricRunStatus.FAILED in statuses:
        return RagTriadStatus.FAILED

    if MetricRunStatus.BLOCKED in statuses:
        return RagTriadStatus.BLOCKED

    if MetricRunStatus.ERROR in statuses:
        return RagTriadStatus.ERROR

    if (
        not missing_metric_ids
        and statuses
        == {
            MetricRunStatus.PASSED
        }
    ):
        return RagTriadStatus.PASSED

    if (
        not missing_metric_ids
        and statuses
        == {
            MetricRunStatus.PLANNED
        }
    ):
        return RagTriadStatus.PLANNED

    return RagTriadStatus.PARTIAL


__all__ = [
    "RAG_TRIAD_METRIC_IDS",
    "RagTriadAggregationError",
    "RagTriadAxisResult",
    "RagTriadResult",
    "RagTriadStatus",
    "aggregate_rag_triad",
]
