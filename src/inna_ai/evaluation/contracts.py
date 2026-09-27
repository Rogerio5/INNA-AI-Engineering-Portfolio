from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from types import MappingProxyType
from typing import Any
from uuid import uuid4

SCHEMA_VERSION = "1.0.0"


class EvaluationStatus(StrEnum):
    """Estado geral de uma avaliação."""

    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    ERROR = "error"


class PrivacyLevel(StrEnum):
    """Nível de sensibilidade dos dados avaliados."""

    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    RESTRICTED = "restricted"


class EvaluationLayer(StrEnum):
    """Camada ou plataforma responsável pela avaliação."""

    DETERMINISTIC = "deterministic"
    DEEPEVAL = "deepeval"
    PHOENIX = "phoenix"
    WEAVE = "weave"
    HUMAN = "human"
    CUSTOM = "custom"


class MetricCategory(StrEnum):
    """Categorias padronizadas de métricas da INNA."""

    CONTRACT = "contract"
    ROUTING = "routing"
    TEAM_ROUTING = "team_routing"
    TOOL_USE = "tool_use"
    TOOL_ARGUMENTS = "tool_arguments"
    TASK_COMPLETION = "task_completion"
    RAG_RELEVANCY = "rag_relevancy"
    RAG_FAITHFULNESS = "rag_faithfulness"
    RAG_RETRIEVAL = "rag_retrieval"
    ANSWER_RELEVANCY = "answer_relevancy"
    FINANCIAL_ACCURACY = "financial_accuracy"
    FINANCIAL_SAFETY = "financial_safety"
    STRUCTURED_OUTPUT = "structured_output"
    PRIVACY = "privacy"
    SECURITY = "security"
    LATENCY = "latency"
    COST = "cost"
    MULTITURN = "multiturn"
    HUMAN_REVIEW = "human_review"
    CUSTOM = "custom"


def utc_now() -> datetime:
    """Retorna a data atual em UTC com timezone explícito."""

    return datetime.now(UTC)


def _immutable_mapping(
    value: Mapping[str, Any] | None,
) -> Mapping[str, Any]:
    """
    Cria uma cópia imutável superficial de um mapeamento.

    Isso impede alterações acidentais no primeiro nível do objeto.
    Estruturas internas podem ser sanitizadas ou serializadas por
    componentes específicos antes de exportações externas.
    """

    return MappingProxyType(dict(value or {}))


def _normalize_optional_string(
    value: str | None,
) -> str | None:
    """Remove espaços de uma string opcional."""

    if value is None:
        return None

    normalized = str(value).strip()

    return normalized or None


def _normalize_string_tuple(
    values: Sequence[str] | None,
) -> tuple[str, ...]:
    """Normaliza uma sequência de strings removendo valores vazios."""

    if not values:
        return ()

    normalized: list[str] = []

    for value in values:
        text = str(value).strip()

        if text:
            normalized.append(text)

    return tuple(normalized)


def _normalize_mapping_tuple(
    values: Sequence[Mapping[str, Any]] | None,
) -> tuple[Mapping[str, Any], ...]:
    """Normaliza uma coleção de mapeamentos."""

    if not values:
        return ()

    return tuple(
        _immutable_mapping(value)
        for value in values
    )


def _validate_score(
    value: float,
    *,
    field_name: str,
) -> None:
    """Garante que uma pontuação esteja entre 0 e 1."""

    if not 0.0 <= float(value) <= 1.0:
        raise ValueError(
            f"{field_name} deve estar entre 0.0 e 1.0. "
            f"Valor recebido: {value!r}."
        )


def _validate_non_negative_number(
    value: int | float | None,
    *,
    field_name: str,
) -> None:
    """Valida números opcionais que não podem ser negativos."""

    if value is not None and value < 0:
        raise ValueError(
            f"{field_name} não pode ser negativo. "
            f"Valor recebido: {value!r}."
        )


@dataclass(frozen=True, slots=True)
class ExpectedToolCall:
    """
    Chamada de ferramenta esperada para um caso de avaliação.

    O campo arguments pode conter somente os argumentos essenciais.
    Quando allow_additional_arguments for verdadeiro, a ferramenta pode
    receber outros argumentos sem reprovar a avaliação.
    """

    name: str
    arguments: Mapping[str, Any] = field(
        default_factory=dict,
    )
    required: bool = True
    allow_additional_arguments: bool = True
    call_order: int | None = None
    minimum_calls: int = 1
    maximum_calls: int | None = None
    metadata: Mapping[str, Any] = field(
        default_factory=dict,
    )

    def __post_init__(self) -> None:
        normalized_name = self.name.strip()

        if not normalized_name:
            raise ValueError(
                "ExpectedToolCall.name não pode ser vazio."
            )

        _validate_non_negative_number(
            self.call_order,
            field_name="ExpectedToolCall.call_order",
        )

        if self.minimum_calls < 0:
            raise ValueError(
                "ExpectedToolCall.minimum_calls não pode ser negativo."
            )

        if (
            self.maximum_calls is not None
            and self.maximum_calls < self.minimum_calls
        ):
            raise ValueError(
                "ExpectedToolCall.maximum_calls não pode ser menor "
                "que minimum_calls."
            )

        object.__setattr__(
            self,
            "name",
            normalized_name,
        )
        object.__setattr__(
            self,
            "arguments",
            _immutable_mapping(self.arguments),
        )
        object.__setattr__(
            self,
            "metadata",
            _immutable_mapping(self.metadata),
        )


@dataclass(frozen=True, slots=True)
class ObservedToolCall:
    """Chamada de ferramenta observada na execução da INNA."""

    name: str
    arguments: Mapping[str, Any] = field(
        default_factory=dict,
    )
    output: Any = None
    status: str = "unknown"
    duration_ms: float | None = None
    call_index: int | None = None
    error_code: str | None = None
    trace_id: str | None = None
    span_id: str | None = None
    metadata: Mapping[str, Any] = field(
        default_factory=dict,
    )

    def __post_init__(self) -> None:
        normalized_name = self.name.strip()

        if not normalized_name:
            raise ValueError(
                "ObservedToolCall.name não pode ser vazio."
            )

        _validate_non_negative_number(
            self.duration_ms,
            field_name="ObservedToolCall.duration_ms",
        )
        _validate_non_negative_number(
            self.call_index,
            field_name="ObservedToolCall.call_index",
        )

        object.__setattr__(
            self,
            "name",
            normalized_name,
        )
        object.__setattr__(
            self,
            "status",
            self.status.strip().lower() or "unknown",
        )
        object.__setattr__(
            self,
            "error_code",
            _normalize_optional_string(self.error_code),
        )
        object.__setattr__(
            self,
            "trace_id",
            _normalize_optional_string(self.trace_id),
        )
        object.__setattr__(
            self,
            "span_id",
            _normalize_optional_string(self.span_id),
        )
        object.__setattr__(
            self,
            "arguments",
            _immutable_mapping(self.arguments),
        )
        object.__setattr__(
            self,
            "metadata",
            _immutable_mapping(self.metadata),
        )


@dataclass(frozen=True, slots=True)
class ConversationTurn:
    """
    Turno de uma avaliação conversacional.

    Pode representar mensagens de usuário, sistema, assistente ou
    ferramentas. Também suporta expectativas específicas por turno.
    """

    role: str
    content: str
    turn_index: int = 0

    expected_output: str | None = None
    expected_agent: str | None = None
    expected_team: str | None = None
    expected_intent: str | None = None
    expected_tools: tuple[ExpectedToolCall, ...] = ()

    metadata: Mapping[str, Any] = field(
        default_factory=dict,
    )

    def __post_init__(self) -> None:
        normalized_role = self.role.strip().lower()
        normalized_content = self.content.strip()

        allowed_roles = {
            "system",
            "user",
            "assistant",
            "tool",
        }

        if normalized_role not in allowed_roles:
            raise ValueError(
                "ConversationTurn.role inválido. "
                f"Valor recebido: {self.role!r}."
            )

        if not normalized_content:
            raise ValueError(
                "ConversationTurn.content não pode ser vazio."
            )

        _validate_non_negative_number(
            self.turn_index,
            field_name="ConversationTurn.turn_index",
        )

        object.__setattr__(
            self,
            "role",
            normalized_role,
        )
        object.__setattr__(
            self,
            "content",
            normalized_content,
        )
        object.__setattr__(
            self,
            "expected_output",
            _normalize_optional_string(
                self.expected_output
            ),
        )
        object.__setattr__(
            self,
            "expected_agent",
            _normalize_optional_string(
                self.expected_agent
            ),
        )
        object.__setattr__(
            self,
            "expected_team",
            _normalize_optional_string(
                self.expected_team
            ),
        )
        object.__setattr__(
            self,
            "expected_intent",
            _normalize_optional_string(
                self.expected_intent
            ),
        )
        object.__setattr__(
            self,
            "metadata",
            _immutable_mapping(self.metadata),
        )


@dataclass(frozen=True, slots=True)
class InnaEvaluationCase:
    """
    Caso versionado de avaliação da INNA.

    Pode representar:

    - classificação e roteamento;
    - supervisor e equipes;
    - diagnóstico financeiro;
    - cálculos;
    - Agentic RAG;
    - uso de ferramentas;
    - saída estruturada;
    - segurança financeira;
    - privacidade;
    - conversas multiturno;
    - Human-in-the-Loop;
    - geração de relatórios.
    """

    case_id: str
    input_text: str = ""

    case_version: str = "1.0.0"
    dataset_name: str = "inna-default"
    dataset_version: str = "1.0.0"

    description: str | None = None
    category: str = "general"
    tags: tuple[str, ...] = ()

    conversation: tuple[ConversationTurn, ...] = ()

    expected_output: str | None = None
    expected_agent: str | None = None
    expected_team: str | None = None
    expected_intent: str | None = None
    expected_task_status: str | None = None

    expected_tools: tuple[ExpectedToolCall, ...] = ()
    forbidden_tools: tuple[str, ...] = ()

    expected_terms: tuple[str, ...] = ()
    forbidden_terms: tuple[str, ...] = ()

    expected_structured_keys: tuple[str, ...] = ()
    forbidden_structured_keys: tuple[str, ...] = ()

    expected_trace_terms: tuple[str, ...] = ()
    forbidden_trace_terms: tuple[str, ...] = ()

    expected_retrieval_terms: tuple[str, ...] = ()
    minimum_retrieved_documents: int = 0

    minimum_completion_score: float = 0.0
    minimum_answer_score: float = 0.0
    maximum_latency_ms: float | None = None
    maximum_estimated_cost: float | None = None

    language: str = "pt"
    currency: str = "BRL"

    privacy_level: PrivacyLevel = PrivacyLevel.CONFIDENTIAL
    external_evaluation_allowed: bool = False
    human_review_expected: bool | None = None

    metadata: Mapping[str, Any] = field(
        default_factory=dict,
    )

    def __post_init__(self) -> None:
        case_id = self.case_id.strip()
        input_text = self.input_text.strip()
        dataset_name = self.dataset_name.strip()
        dataset_version = self.dataset_version.strip()
        case_version = self.case_version.strip()

        if not case_id:
            raise ValueError(
                "InnaEvaluationCase.case_id não pode ser vazio."
            )

        if not input_text and not self.conversation:
            raise ValueError(
                "O caso precisa de input_text ou conversation."
            )

        if not dataset_name:
            raise ValueError(
                "InnaEvaluationCase.dataset_name não pode ser vazio."
            )

        if not dataset_version:
            raise ValueError(
                "InnaEvaluationCase.dataset_version não pode ser vazio."
            )

        if not case_version:
            raise ValueError(
                "InnaEvaluationCase.case_version não pode ser vazio."
            )

        if self.minimum_retrieved_documents < 0:
            raise ValueError(
                "minimum_retrieved_documents não pode ser negativo."
            )

        _validate_score(
            self.minimum_completion_score,
            field_name="minimum_completion_score",
        )
        _validate_score(
            self.minimum_answer_score,
            field_name="minimum_answer_score",
        )

        _validate_non_negative_number(
            self.maximum_latency_ms,
            field_name="maximum_latency_ms",
        )
        _validate_non_negative_number(
            self.maximum_estimated_cost,
            field_name="maximum_estimated_cost",
        )

        if (
            self.privacy_level == PrivacyLevel.RESTRICTED
            and self.external_evaluation_allowed
        ):
            raise ValueError(
                "Casos RESTRICTED não podem permitir "
                "avaliação externa."
            )

        turn_indexes = [
            turn.turn_index
            for turn in self.conversation
        ]

        if len(turn_indexes) != len(set(turn_indexes)):
            raise ValueError(
                "A conversation possui índices de turno duplicados."
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
            "dataset_name",
            dataset_name,
        )
        object.__setattr__(
            self,
            "dataset_version",
            dataset_version,
        )
        object.__setattr__(
            self,
            "case_version",
            case_version,
        )
        object.__setattr__(
            self,
            "description",
            _normalize_optional_string(self.description),
        )
        object.__setattr__(
            self,
            "expected_output",
            _normalize_optional_string(
                self.expected_output
            ),
        )
        object.__setattr__(
            self,
            "expected_agent",
            _normalize_optional_string(
                self.expected_agent
            ),
        )
        object.__setattr__(
            self,
            "expected_team",
            _normalize_optional_string(
                self.expected_team
            ),
        )
        object.__setattr__(
            self,
            "expected_intent",
            _normalize_optional_string(
                self.expected_intent
            ),
        )
        object.__setattr__(
            self,
            "expected_task_status",
            _normalize_optional_string(
                self.expected_task_status
            ),
        )
        object.__setattr__(
            self,
            "category",
            self.category.strip().lower() or "general",
        )
        object.__setattr__(
            self,
            "language",
            self.language.strip().lower() or "pt",
        )
        object.__setattr__(
            self,
            "currency",
            self.currency.strip().upper() or "BRL",
        )
        object.__setattr__(
            self,
            "tags",
            _normalize_string_tuple(self.tags),
        )
        object.__setattr__(
            self,
            "forbidden_tools",
            _normalize_string_tuple(
                self.forbidden_tools
            ),
        )
        object.__setattr__(
            self,
            "expected_terms",
            _normalize_string_tuple(
                self.expected_terms
            ),
        )
        object.__setattr__(
            self,
            "forbidden_terms",
            _normalize_string_tuple(
                self.forbidden_terms
            ),
        )
        object.__setattr__(
            self,
            "expected_structured_keys",
            _normalize_string_tuple(
                self.expected_structured_keys
            ),
        )
        object.__setattr__(
            self,
            "forbidden_structured_keys",
            _normalize_string_tuple(
                self.forbidden_structured_keys
            ),
        )
        object.__setattr__(
            self,
            "expected_trace_terms",
            _normalize_string_tuple(
                self.expected_trace_terms
            ),
        )
        object.__setattr__(
            self,
            "forbidden_trace_terms",
            _normalize_string_tuple(
                self.forbidden_trace_terms
            ),
        )
        object.__setattr__(
            self,
            "expected_retrieval_terms",
            _normalize_string_tuple(
                self.expected_retrieval_terms
            ),
        )
        object.__setattr__(
            self,
            "metadata",
            _immutable_mapping(self.metadata),
        )


@dataclass(frozen=True, slots=True)
class MetricResult:
    """
    Resultado normalizado de uma métrica.

    Pode representar uma regra determinística, uma métrica do DeepEval,
    uma avaliação do Phoenix, um scorer do Weave ou revisão humana.
    """

    name: str
    category: MetricCategory
    score: float
    threshold: float
    passed: bool

    layer: EvaluationLayer = EvaluationLayer.DETERMINISTIC
    reason: str | None = None
    evaluator_model: str | None = None
    evaluator_version: str | None = None

    started_at: datetime | None = None
    finished_at: datetime | None = None
    duration_ms: float | None = None

    error: str | None = None
    details: Mapping[str, Any] = field(
        default_factory=dict,
    )

    def __post_init__(self) -> None:
        normalized_name = self.name.strip()

        if not normalized_name:
            raise ValueError(
                "MetricResult.name não pode ser vazio."
            )

        _validate_score(
            self.score,
            field_name="MetricResult.score",
        )
        _validate_score(
            self.threshold,
            field_name="MetricResult.threshold",
        )

        _validate_non_negative_number(
            self.duration_ms,
            field_name="MetricResult.duration_ms",
        )

        if (
            self.started_at is not None
            and self.started_at.tzinfo is None
        ):
            raise ValueError(
                "MetricResult.started_at precisa possuir timezone."
            )

        if (
            self.finished_at is not None
            and self.finished_at.tzinfo is None
        ):
            raise ValueError(
                "MetricResult.finished_at precisa possuir timezone."
            )

        if (
            self.started_at is not None
            and self.finished_at is not None
            and self.finished_at < self.started_at
        ):
            raise ValueError(
                "MetricResult.finished_at não pode ser anterior "
                "a started_at."
            )

        calculated_passed = self.score >= self.threshold

        if self.error is None and self.passed != calculated_passed:
            raise ValueError(
                "MetricResult.passed está inconsistente com "
                "score e threshold."
            )

        object.__setattr__(
            self,
            "name",
            normalized_name,
        )
        object.__setattr__(
            self,
            "reason",
            _normalize_optional_string(self.reason),
        )
        object.__setattr__(
            self,
            "evaluator_model",
            _normalize_optional_string(
                self.evaluator_model
            ),
        )
        object.__setattr__(
            self,
            "evaluator_version",
            _normalize_optional_string(
                self.evaluator_version
            ),
        )
        object.__setattr__(
            self,
            "error",
            _normalize_optional_string(self.error),
        )
        object.__setattr__(
            self,
            "details",
            _immutable_mapping(self.details),
        )


@dataclass(frozen=True, slots=True)
class TokenUsage:
    """Uso normalizado de tokens de modelos de linguagem."""

    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    cached_tokens: int = 0
    reasoning_tokens: int = 0

    def __post_init__(self) -> None:
        values = {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "cached_tokens": self.cached_tokens,
            "reasoning_tokens": self.reasoning_tokens,
        }

        for name, value in values.items():
            if value < 0:
                raise ValueError(
                    f"{name} não pode ser negativo."
                )

        expected_minimum = (
            self.input_tokens
            + self.output_tokens
        )

        if (
            self.total_tokens
            and self.total_tokens < expected_minimum
        ):
            raise ValueError(
                "total_tokens não pode ser menor que a soma de "
                "input_tokens e output_tokens."
            )

    @property
    def calculated_total_tokens(self) -> int:
        """
        Retorna total_tokens quando fornecido ou calcula a soma básica.
        """

        if self.total_tokens:
            return self.total_tokens

        return self.input_tokens + self.output_tokens


@dataclass(frozen=True, slots=True)
class RetrievalDocument:
    """Documento ou chunk recuperado pelo pipeline RAG."""

    content: str
    document_id: str | None = None
    score: float | None = None
    rank: int | None = None
    source: str | None = None
    content_hash: str | None = None
    metadata: Mapping[str, Any] = field(
        default_factory=dict,
    )

    def __post_init__(self) -> None:
        normalized_content = self.content.strip()

        if not normalized_content:
            raise ValueError(
                "RetrievalDocument.content não pode ser vazio."
            )

        _validate_non_negative_number(
            self.rank,
            field_name="RetrievalDocument.rank",
        )

        if self.score is not None:
            _validate_score(
                self.score,
                field_name="RetrievalDocument.score",
            )

        object.__setattr__(
            self,
            "content",
            normalized_content,
        )
        object.__setattr__(
            self,
            "document_id",
            _normalize_optional_string(
                self.document_id
            ),
        )
        object.__setattr__(
            self,
            "source",
            _normalize_optional_string(self.source),
        )
        object.__setattr__(
            self,
            "content_hash",
            _normalize_optional_string(
                self.content_hash
            ),
        )
        object.__setattr__(
            self,
            "metadata",
            _immutable_mapping(self.metadata),
        )


@dataclass(frozen=True, slots=True)
class ModelExecution:
    """Registro de uma chamada de modelo durante a avaliação."""

    provider: str
    model_name: str

    operation: str = "generation"
    prompt_version: str | None = None

    latency_ms: float | None = None
    estimated_cost: float | None = None
    cost_currency: str = "USD"

    token_usage: TokenUsage = field(
        default_factory=TokenUsage,
    )

    status: str = "success"
    error_code: str | None = None

    trace_id: str | None = None
    span_id: str | None = None

    metadata: Mapping[str, Any] = field(
        default_factory=dict,
    )

    def __post_init__(self) -> None:
        provider = self.provider.strip().lower()
        model_name = self.model_name.strip()

        if not provider:
            raise ValueError(
                "ModelExecution.provider não pode ser vazio."
            )

        if not model_name:
            raise ValueError(
                "ModelExecution.model_name não pode ser vazio."
            )

        _validate_non_negative_number(
            self.latency_ms,
            field_name="ModelExecution.latency_ms",
        )
        _validate_non_negative_number(
            self.estimated_cost,
            field_name="ModelExecution.estimated_cost",
        )

        object.__setattr__(
            self,
            "provider",
            provider,
        )
        object.__setattr__(
            self,
            "model_name",
            model_name,
        )
        object.__setattr__(
            self,
            "operation",
            self.operation.strip().lower() or "generation",
        )
        object.__setattr__(
            self,
            "prompt_version",
            _normalize_optional_string(
                self.prompt_version
            ),
        )
        object.__setattr__(
            self,
            "cost_currency",
            self.cost_currency.strip().upper() or "USD",
        )
        object.__setattr__(
            self,
            "status",
            self.status.strip().lower() or "unknown",
        )
        object.__setattr__(
            self,
            "error_code",
            _normalize_optional_string(self.error_code),
        )
        object.__setattr__(
            self,
            "trace_id",
            _normalize_optional_string(self.trace_id),
        )
        object.__setattr__(
            self,
            "span_id",
            _normalize_optional_string(self.span_id),
        )
        object.__setattr__(
            self,
            "metadata",
            _immutable_mapping(self.metadata),
        )


@dataclass(frozen=True, slots=True)
class InnaEvaluationResult:
    """
    Resultado completo e independente de framework.

    Este contrato pode alimentar:

    - DeepEval;
    - Arize Phoenix;
    - W&B Weave;
    - relatórios JSON;
    - Dashboard LLMOps;
    - pipelines CI/CD.
    """

    case_id: str
    input_text: str
    actual_output: str

    evaluation_id: str = field(
        default_factory=lambda: str(uuid4()),
    )
    schema_version: str = SCHEMA_VERSION
    created_at: datetime = field(
        default_factory=utc_now,
    )

    dataset_name: str = "inna-default"
    dataset_version: str = "1.0.0"
    case_version: str = "1.0.0"

    status: EvaluationStatus = EvaluationStatus.PENDING

    current_agent: str = ""
    current_team: str = ""
    intent: str = ""
    task_status: str = ""
    task_completion_score: float = 0.0

    tools_called: tuple[ObservedToolCall, ...] = ()
    retrieval_documents: tuple[RetrievalDocument, ...] = ()
    model_executions: tuple[ModelExecution, ...] = ()

    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    trace: tuple[str, ...] = ()

    application_version: str | None = None
    graph_version: str | None = None
    prompt_version: str | None = None

    latency_ms: float | None = None
    estimated_cost: float | None = None
    cost_currency: str = "USD"

    metric_results: tuple[MetricResult, ...] = ()

    trace_id: str | None = None
    thread_id: str | None = None
    session_id: str | None = None
    user_reference_hash: str | None = None

    human_review_requested: bool = False
    human_review_status: str | None = None
    human_review_id: str | None = None

    privacy_level: PrivacyLevel = PrivacyLevel.CONFIDENTIAL
    external_payload_sanitized: bool = False

    structured_response: Mapping[str, Any] = field(
        default_factory=dict,
    )
    raw_state: Mapping[str, Any] = field(
        default_factory=dict,
    )
    metadata: Mapping[str, Any] = field(
        default_factory=dict,
    )

    def __post_init__(self) -> None:
        case_id = self.case_id.strip()
        actual_output = self.actual_output.strip()

        if not case_id:
            raise ValueError(
                "InnaEvaluationResult.case_id não pode ser vazio."
            )

        if not self.evaluation_id.strip():
            raise ValueError(
                "InnaEvaluationResult.evaluation_id não pode ser vazio."
            )

        if not self.schema_version.strip():
            raise ValueError(
                "InnaEvaluationResult.schema_version não pode ser vazio."
            )

        if (
            not actual_output
            and self.status
            not in {
                EvaluationStatus.ERROR,
                EvaluationStatus.SKIPPED,
            }
        ):
            raise ValueError(
                "actual_output não pode ser vazio para resultados "
                "executados normalmente."
            )

        _validate_score(
            self.task_completion_score,
            field_name="task_completion_score",
        )

        _validate_non_negative_number(
            self.latency_ms,
            field_name="latency_ms",
        )
        _validate_non_negative_number(
            self.estimated_cost,
            field_name="estimated_cost",
        )

        if self.created_at.tzinfo is None:
            raise ValueError(
                "created_at precisa possuir timezone."
            )

        valid_metrics = [
            metric
            for metric in self.metric_results
            if metric.error is None
        ]

        if (
            self.status == EvaluationStatus.PASSED
            and any(
                not metric.passed
                for metric in valid_metrics
            )
        ):
            raise ValueError(
                "Um resultado PASSED não pode conter "
                "métrica reprovada."
            )

        if (
            self.status == EvaluationStatus.FAILED
            and valid_metrics
            and all(
                metric.passed
                for metric in valid_metrics
            )
        ):
            raise ValueError(
                "Um resultado FAILED deve conter ao menos "
                "uma métrica reprovada."
            )

        if (
            self.privacy_level == PrivacyLevel.RESTRICTED
            and self.external_payload_sanitized
        ):
            raise ValueError(
                "Dados RESTRICTED não devem ser marcados como "
                "exportáveis mesmo quando sanitizados."
            )

        object.__setattr__(
            self,
            "case_id",
            case_id,
        )
        object.__setattr__(
            self,
            "evaluation_id",
            self.evaluation_id.strip(),
        )
        object.__setattr__(
            self,
            "schema_version",
            self.schema_version.strip(),
        )
        object.__setattr__(
            self,
            "input_text",
            self.input_text.strip(),
        )
        object.__setattr__(
            self,
            "actual_output",
            actual_output,
        )
        object.__setattr__(
            self,
            "dataset_name",
            self.dataset_name.strip() or "inna-default",
        )
        object.__setattr__(
            self,
            "dataset_version",
            self.dataset_version.strip() or "1.0.0",
        )
        object.__setattr__(
            self,
            "case_version",
            self.case_version.strip() or "1.0.0",
        )
        object.__setattr__(
            self,
            "current_agent",
            self.current_agent.strip(),
        )
        object.__setattr__(
            self,
            "current_team",
            self.current_team.strip(),
        )
        object.__setattr__(
            self,
            "intent",
            self.intent.strip(),
        )
        object.__setattr__(
            self,
            "task_status",
            self.task_status.strip(),
        )
        object.__setattr__(
            self,
            "cost_currency",
            self.cost_currency.strip().upper() or "USD",
        )
        object.__setattr__(
            self,
            "errors",
            _normalize_string_tuple(self.errors),
        )
        object.__setattr__(
            self,
            "warnings",
            _normalize_string_tuple(self.warnings),
        )
        object.__setattr__(
            self,
            "trace",
            _normalize_string_tuple(self.trace),
        )
        object.__setattr__(
            self,
            "application_version",
            _normalize_optional_string(
                self.application_version
            ),
        )
        object.__setattr__(
            self,
            "graph_version",
            _normalize_optional_string(
                self.graph_version
            ),
        )
        object.__setattr__(
            self,
            "prompt_version",
            _normalize_optional_string(
                self.prompt_version
            ),
        )
        object.__setattr__(
            self,
            "trace_id",
            _normalize_optional_string(self.trace_id),
        )
        object.__setattr__(
            self,
            "thread_id",
            _normalize_optional_string(self.thread_id),
        )
        object.__setattr__(
            self,
            "session_id",
            _normalize_optional_string(self.session_id),
        )
        object.__setattr__(
            self,
            "user_reference_hash",
            _normalize_optional_string(
                self.user_reference_hash
            ),
        )
        object.__setattr__(
            self,
            "human_review_status",
            _normalize_optional_string(
                self.human_review_status
            ),
        )
        object.__setattr__(
            self,
            "human_review_id",
            _normalize_optional_string(
                self.human_review_id
            ),
        )
        object.__setattr__(
            self,
            "structured_response",
            _immutable_mapping(
                self.structured_response
            ),
        )
        object.__setattr__(
            self,
            "raw_state",
            _immutable_mapping(self.raw_state),
        )
        object.__setattr__(
            self,
            "metadata",
            _immutable_mapping(self.metadata),
        )

    @property
    def tools_called_names(self) -> tuple[str, ...]:
        """Retorna somente os nomes das ferramentas chamadas."""

        return tuple(
            tool.name
            for tool in self.tools_called
        )

    @property
    def successful_tools(self) -> tuple[ObservedToolCall, ...]:
        """Retorna ferramentas executadas com sucesso."""

        success_statuses = {
            "success",
            "succeeded",
            "completed",
            "ok",
        }

        return tuple(
            tool
            for tool in self.tools_called
            if tool.status in success_statuses
        )

    @property
    def failed_tools(self) -> tuple[ObservedToolCall, ...]:
        """Retorna ferramentas com falha."""

        failure_statuses = {
            "failed",
            "error",
            "timeout",
            "denied",
        }

        return tuple(
            tool
            for tool in self.tools_called
            if tool.status in failure_statuses
        )

    @property
    def retrieval_context(self) -> tuple[str, ...]:
        """Retorna documentos no formato esperado por métricas RAG."""

        return tuple(
            document.content
            for document in self.retrieval_documents
        )

    @property
    def average_metric_score(self) -> float | None:
        """Calcula a média das métricas sem erro."""

        valid_scores = [
            metric.score
            for metric in self.metric_results
            if metric.error is None
        ]

        if not valid_scores:
            return None

        return sum(valid_scores) / len(valid_scores)

    @property
    def passed_metrics(self) -> int:
        """Quantidade de métricas aprovadas."""

        return sum(
            1
            for metric in self.metric_results
            if metric.error is None
            and metric.passed
        )

    @property
    def failed_metrics(self) -> int:
        """Quantidade de métricas reprovadas."""

        return sum(
            1
            for metric in self.metric_results
            if metric.error is None
            and not metric.passed
        )

    @property
    def metric_errors(self) -> int:
        """Quantidade de métricas que tiveram erro."""

        return sum(
            1
            for metric in self.metric_results
            if metric.error is not None
        )

    @property
    def has_runtime_errors(self) -> bool:
        """Informa se a execução produziu erros."""

        return bool(self.errors)

    @property
    def total_input_tokens(self) -> int:
        """Soma os tokens de entrada de todas as chamadas de modelo."""

        return sum(
            execution.token_usage.input_tokens
            for execution in self.model_executions
        )

    @property
    def total_output_tokens(self) -> int:
        """Soma os tokens de saída de todas as chamadas de modelo."""

        return sum(
            execution.token_usage.output_tokens
            for execution in self.model_executions
        )

    @property
    def total_tokens(self) -> int:
        """Soma o total de tokens das chamadas de modelo."""

        return sum(
            execution.token_usage.calculated_total_tokens
            for execution in self.model_executions
        )

    @property
    def is_external_export_allowed(self) -> bool:
        """
        Determina se o resultado pode ser exportado externamente.

        Resultados restritos nunca são exportáveis. Os demais precisam
        ter passado pela camada de sanitização.
        """

        return (
            self.privacy_level != PrivacyLevel.RESTRICTED
            and self.external_payload_sanitized
        )


@dataclass(frozen=True, slots=True)
class EvaluationRunSummary:
    """Resumo agregado de uma execução com múltiplos casos."""

    run_id: str
    dataset_name: str
    dataset_version: str
    started_at: datetime
    finished_at: datetime

    total_cases: int
    passed_cases: int
    failed_cases: int
    skipped_cases: int
    error_cases: int

    average_score: float | None
    total_latency_ms: float
    total_estimated_cost: float | None
    cost_currency: str = "USD"

    results: tuple[InnaEvaluationResult, ...] = ()
    metadata: Mapping[str, Any] = field(
        default_factory=dict,
    )

    def __post_init__(self) -> None:
        if not self.run_id.strip():
            raise ValueError(
                "EvaluationRunSummary.run_id não pode ser vazio."
            )

        if self.started_at.tzinfo is None:
            raise ValueError(
                "started_at precisa possuir timezone."
            )

        if self.finished_at.tzinfo is None:
            raise ValueError(
                "finished_at precisa possuir timezone."
            )

        if self.finished_at < self.started_at:
            raise ValueError(
                "finished_at não pode ser anterior a started_at."
            )

        counters = {
            "total_cases": self.total_cases,
            "passed_cases": self.passed_cases,
            "failed_cases": self.failed_cases,
            "skipped_cases": self.skipped_cases,
            "error_cases": self.error_cases,
        }

        for name, value in counters.items():
            if value < 0:
                raise ValueError(
                    f"{name} não pode ser negativo."
                )

        classified_cases = (
            self.passed_cases
            + self.failed_cases
            + self.skipped_cases
            + self.error_cases
        )

        if classified_cases != self.total_cases:
            raise ValueError(
                "A soma dos resultados não corresponde "
                "a total_cases."
            )

        if self.total_cases != len(self.results):
            raise ValueError(
                "total_cases não corresponde à quantidade "
                "de results."
            )

        if self.average_score is not None:
            _validate_score(
                self.average_score,
                field_name="average_score",
            )

        _validate_non_negative_number(
            self.total_latency_ms,
            field_name="total_latency_ms",
        )
        _validate_non_negative_number(
            self.total_estimated_cost,
            field_name="total_estimated_cost",
        )

        result_case_ids = [
            result.case_id
            for result in self.results
        ]

        if len(result_case_ids) != len(set(result_case_ids)):
            raise ValueError(
                "EvaluationRunSummary possui case_id duplicado."
            )

        object.__setattr__(
            self,
            "run_id",
            self.run_id.strip(),
        )
        object.__setattr__(
            self,
            "dataset_name",
            self.dataset_name.strip(),
        )
        object.__setattr__(
            self,
            "dataset_version",
            self.dataset_version.strip(),
        )
        object.__setattr__(
            self,
            "cost_currency",
            self.cost_currency.strip().upper() or "USD",
        )
        object.__setattr__(
            self,
            "metadata",
            _immutable_mapping(self.metadata),
        )

    @property
    def pass_rate(self) -> float:
        """Calcula a taxa de aprovação dos casos."""

        if self.total_cases == 0:
            return 0.0

        return self.passed_cases / self.total_cases

    @property
    def failure_rate(self) -> float:
        """Calcula a taxa de reprovação dos casos."""

        if self.total_cases == 0:
            return 0.0

        return self.failed_cases / self.total_cases

    @property
    def error_rate(self) -> float:
        """Calcula a taxa de erros técnicos."""

        if self.total_cases == 0:
            return 0.0

        return self.error_cases / self.total_cases

    @property
    def duration_ms(self) -> float:
        """Calcula a duração total da execução."""

        difference = self.finished_at - self.started_at

        return difference.total_seconds() * 1000


__all__ = [
    "SCHEMA_VERSION",
    "ConversationTurn",
    "EvaluationLayer",
    "EvaluationRunSummary",
    "EvaluationStatus",
    "ExpectedToolCall",
    "InnaEvaluationCase",
    "InnaEvaluationResult",
    "MetricCategory",
    "MetricResult",
    "ModelExecution",
    "ObservedToolCall",
    "PrivacyLevel",
    "RetrievalDocument",
    "TokenUsage",
    "utc_now",
]
