"""
Router Agent seguro do Agentic RAG da INNA.

Responsabilidades:
- transformar etapas do Query Planner em rotas formais;
- selecionar somente fontes e ferramentas autorizadas;
- validar os argumentos permitidos;
- impedir identidade nos argumentos do modelo;
- criar ToolCall com contexto confiável;
- executar pelo runtime governado da INNA;
- produzir auditoria sem registrar conteúdo sensível.

O Router Agent não acessa diretamente banco, RAG,
Gemini, rede, Gmail ou Telegram.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable
from typing import (
    Any,
    Literal,
    Self,
)

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
)

from inna_ai.tools.core import ToolCall, ToolExecutionContext, ToolResult
from inna_ai.tools.runtime import executar_ferramenta_inna
from inna_ai.retrieval.agentic.contracts import ALLOWED_TOOL_BY_SOURCE, ResearchPlan, ResearchSource, ResearchSubquery

ROUTER_VERSION = "2.0.0"
ROUTER_AGENT_NAME = "research_agent"

_LANGUAGE_PATTERN = re.compile(r"^[A-Za-z]{2,3}(?:-[A-Za-z]{2})?$")

_IDENTITY_ARGUMENT_KEYS = frozenset(
    {
        "user_id",
        "usuario_id",
        "usuario",
        "nome",
        "email",
        "cpf",
        "session_id",
        "thread_id",
        "trace_id",
        "token",
    }
)

_ALLOWED_ARGUMENTS_BY_SOURCE = {
    ResearchSource.KNOWLEDGE_BASE: frozenset(
        {
            "pergunta",
            "idioma",
            "top_k",
        }
    ),
    ResearchSource.FINANCIAL_HISTORY: frozenset(
        {
            "limite",
        }
    ),
}


class ResearchRoutingError(RuntimeError):
    """
    Falha segura durante a seleção de uma rota.
    """


class MissingTrustedUserContextError(ResearchRoutingError):
    """
    Uma fonte restrita foi solicitada sem identidade
    proveniente do contexto confiável da aplicação.
    """


class ResearchRoute(BaseModel):
    """
    Decisão estruturada produzida pelo Router Agent.

    O conteúdo dos argumentos é validado novamente,
    mesmo quando a etapa já passou pelos contratos
    do Query Planner.
    """

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
    )

    route_id: str = Field(
        min_length=1,
        max_length=180,
        pattern=r"^[a-z][a-z0-9_]*$",
    )
    step_id: str = Field(
        min_length=1,
        max_length=120,
        pattern=r"^[a-z][a-z0-9_]*$",
    )
    source: ResearchSource
    tool_name: str = Field(
        min_length=1,
        max_length=120,
        pattern=r"^[a-z][a-z0-9_]*$",
    )
    arguments: dict[str, Any] = Field(
        default_factory=dict,
        max_length=10,
    )
    requested_by: Literal["research_agent"] = ROUTER_AGENT_NAME
    requires_trusted_user: bool
    read_only: bool = True
    sensitive_output: bool
    idempotent: bool = True
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        max_length=20,
    )

    @model_validator(mode="after")
    def validate_route_policy(self) -> Self:
        expected_tool = ALLOWED_TOOL_BY_SOURCE.get(self.source)

        if not expected_tool:
            raise ValueError("A fonte não possui uma ferramenta formal autorizada.")

        if self.tool_name != expected_tool:
            raise ValueError("A ferramenta não corresponde à fonte autorizada.")

        allowed_arguments = _ALLOWED_ARGUMENTS_BY_SOURCE.get(
            self.source,
            frozenset(),
        )
        argument_keys = frozenset(str(key) for key in self.arguments)

        unexpected_arguments = argument_keys - allowed_arguments

        if unexpected_arguments:
            unexpected = ", ".join(sorted(unexpected_arguments))

            raise ValueError(f"Argumentos não permitidos para a fonte: {unexpected}.")

        missing_arguments = allowed_arguments - argument_keys

        if missing_arguments:
            missing = ", ".join(sorted(missing_arguments))

            raise ValueError(f"Argumentos obrigatórios ausentes na rota: {missing}.")

        identity_arguments = argument_keys & _IDENTITY_ARGUMENT_KEYS

        if identity_arguments:
            raise ValueError(
                "Identidade e credenciais não podem ser argumentos da ferramenta."
            )

        if not self.read_only:
            raise ValueError("A Fase 2 permite somente rotas de leitura.")

        if not self.idempotent:
            raise ValueError("A Fase 2 permite somente ferramentas idempotentes.")

        if self.source == ResearchSource.KNOWLEDGE_BASE:
            self._validate_knowledge_arguments()

            if self.requires_trusted_user:
                raise ValueError(
                    "A base pública da INNA não exige identidade de usuário."
                )

            if self.sensitive_output:
                raise ValueError(
                    "A saída da base educacional não deve ser marcada como sensível."
                )

        elif self.source == ResearchSource.FINANCIAL_HISTORY:
            self._validate_history_arguments()

            if not self.requires_trusted_user:
                raise ValueError("O histórico financeiro exige contexto confiável.")

            if not self.sensitive_output:
                raise ValueError(
                    "O histórico financeiro deve ser marcado como saída sensível."
                )

        return self

    def _validate_knowledge_arguments(
        self,
    ) -> None:
        question = str(
            self.arguments.get(
                "pergunta",
                "",
            )
            or ""
        ).strip()
        language = str(
            self.arguments.get(
                "idioma",
                "",
            )
            or ""
        ).strip()
        top_k = self.arguments.get("top_k")

        if not 3 <= len(question) <= 4000:
            raise ValueError("A pergunta da rota RAG possui tamanho inválido.")

        if not _LANGUAGE_PATTERN.fullmatch(language):
            raise ValueError("O idioma da rota RAG é inválido.")

        if (
            isinstance(top_k, bool)
            or not isinstance(top_k, int)
            or not 1 <= top_k <= 10
        ):
            raise ValueError("top_k deve ser um inteiro entre 1 e 10.")

    def _validate_history_arguments(
        self,
    ) -> None:
        limit = self.arguments.get("limite")

        if (
            isinstance(limit, bool)
            or not isinstance(limit, int)
            or not 1 <= limit <= 20
        ):
            raise ValueError("limite deve ser um inteiro entre 1 e 20.")


class ResearchSourceRouter:
    """
    Router Agent determinístico e deny-by-default.

    A seleção não é feita livremente pelo LLM.
    A fonte definida no plano deve corresponder ao
    catálogo formal de ferramentas.
    """

    def route(
        self,
        step: ResearchSubquery,
        *,
        language: str,
    ) -> ResearchRoute:
        normalized_language = str(language or "").strip()

        if not _LANGUAGE_PATTERN.fullmatch(normalized_language):
            raise ResearchRoutingError("O idioma informado ao Router Agent é inválido.")

        expected_tool = ALLOWED_TOOL_BY_SOURCE.get(step.source)

        if not expected_tool:
            raise ResearchRoutingError("Fonte de pesquisa não autorizada.")

        if step.tool_name != expected_tool:
            raise ResearchRoutingError(
                "A ferramenta do plano não corresponde à fonte autorizada."
            )

        if step.source == ResearchSource.KNOWLEDGE_BASE:
            arguments: dict[str, Any] = {
                "pergunta": step.question,
                "idioma": normalized_language,
                "top_k": step.top_k,
            }
            requires_trusted_user = False
            sensitive_output = False

        elif step.source == ResearchSource.FINANCIAL_HISTORY:
            arguments = {
                "limite": min(
                    20,
                    step.max_results,
                ),
            }
            requires_trusted_user = True
            sensitive_output = True

        else:
            raise ResearchRoutingError("Fonte de pesquisa não suportada.")

        return ResearchRoute(
            route_id=(f"route_{step.step_id}")[:180],
            step_id=step.step_id,
            source=step.source,
            tool_name=expected_tool,
            arguments=arguments,
            requested_by=ROUTER_AGENT_NAME,
            requires_trusted_user=(requires_trusted_user),
            read_only=True,
            sensitive_output=(sensitive_output),
            idempotent=True,
            metadata={
                "router_version": (ROUTER_VERSION),
                "routing_mode": ("deterministic"),
                "permission_policy": ("deny_by_default"),
                "argument_names": sorted(arguments),
            },
        )

    def route_plan(
        self,
        plan: ResearchPlan,
    ) -> list[ResearchRoute]:
        return [
            self.route(
                step,
                language=plan.language,
            )
            for step in plan.subqueries
        ]


def route_research_plan(
    plan: ResearchPlan,
    *,
    router: ResearchSourceRouter | None = None,
) -> list[ResearchRoute]:
    """
    Converte todas as subconsultas de um plano
    em rotas formais e validadas.
    """

    source_router = router or ResearchSourceRouter()

    return source_router.route_plan(plan)


def _normalize_optional_identifier(
    value: str | None,
    *,
    field_name: str,
    maximum_length: int = 255,
) -> str | None:
    if value is None:
        return None

    normalized = str(value).strip()

    if not normalized:
        return None

    if len(normalized) > maximum_length:
        raise ResearchRoutingError(f"{field_name} excede o tamanho permitido.")

    return normalized


def build_tool_call(
    route: ResearchRoute,
    *,
    user_id: str | None,
    session_id: str | None,
    trace_id: str,
) -> ToolCall:
    """
    Cria uma chamada formal para o runtime da INNA.

    A identidade fica exclusivamente em
    ToolExecutionContext. Ela nunca é adicionada
    ao dicionário de argumentos da ferramenta.
    """

    normalized_user_id = _normalize_optional_identifier(
        user_id,
        field_name="user_id",
    )
    normalized_session_id = _normalize_optional_identifier(
        session_id,
        field_name="session_id",
    )
    normalized_trace_id = _normalize_optional_identifier(
        trace_id,
        field_name="trace_id",
    )

    if not normalized_trace_id:
        raise ResearchRoutingError(
            "trace_id é obrigatório para uma chamada de ferramenta auditável."
        )

    if route.requires_trusted_user and not normalized_user_id:
        raise MissingTrustedUserContextError(
            "A rota exige identidade proveniente do contexto confiável."
        )

    forbidden_arguments = set(route.arguments) & _IDENTITY_ARGUMENT_KEYS

    if forbidden_arguments:
        raise ResearchRoutingError(
            "A rota contém identidade ou credencial nos argumentos da ferramenta."
        )

    context = ToolExecutionContext(
        requested_by=route.requested_by,
        user_id=normalized_user_id,
        session_id=normalized_session_id,
        trace_id=normalized_trace_id,
        metadata={
            "agentic_rag": True,
            "router_version": ROUTER_VERSION,
            "route_id": route.route_id,
            "research_step_id": route.step_id,
            "research_source": (route.source.value),
            "read_only": route.read_only,
            "sensitive_output": (route.sensitive_output),
        },
    )

    return ToolCall(
        tool_name=route.tool_name,
        arguments=dict(route.arguments),
        context=context,
    )


def execute_routed_tool(
    route: ResearchRoute,
    *,
    user_id: str | None,
    session_id: str | None,
    trace_id: str,
    executor: (Callable[[ToolCall], ToolResult] | None) = None,
) -> ToolResult:
    """
    Executa a rota pelo runtime formal da INNA.

    O parâmetro executor permite testes isolados,
    sem chamada real ao Gemini, RAG ou Neon.
    """

    tool_call = build_tool_call(
        route,
        user_id=user_id,
        session_id=session_id,
        trace_id=trace_id,
    )

    runtime_executor = executor or executar_ferramenta_inna

    return runtime_executor(tool_call)


def _arguments_hash(
    arguments: dict[str, Any],
) -> str:
    serialized = json.dumps(
        arguments,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )

    return hashlib.sha256(
        serialized.encode(
            "utf-8",
            errors="replace",
        )
    ).hexdigest()


def route_to_audit_payload(
    route: ResearchRoute,
) -> dict[str, Any]:
    """
    Produz evento de auditoria sanitizado.

    Não inclui:
    - pergunta;
    - valores dos argumentos;
    - identidade;
    - resultado da ferramenta.
    """

    return {
        "event": "agentic_rag_route_created",
        "router_version": ROUTER_VERSION,
        "route_id": route.route_id,
        "step_id": route.step_id,
        "source": route.source.value,
        "tool_name": route.tool_name,
        "requested_by": route.requested_by,
        "argument_names": sorted(route.arguments),
        "arguments_sha256": (_arguments_hash(route.arguments)),
        "requires_trusted_user": (route.requires_trusted_user),
        "read_only": route.read_only,
        "sensitive_output": (route.sensitive_output),
        "idempotent": route.idempotent,
        "permission_policy": ("deny_by_default"),
    }


__all__ = [
    "MissingTrustedUserContextError",
    "ROUTER_AGENT_NAME",
    "ROUTER_VERSION",
    "ResearchRoute",
    "ResearchRoutingError",
    "ResearchSourceRouter",
    "build_tool_call",
    "execute_routed_tool",
    "route_research_plan",
    "route_to_audit_payload",
]
