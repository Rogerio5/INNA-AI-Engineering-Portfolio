"""
Grafo principal do núcleo de agentes da INNA.

Suporta:
- execução sem persistência para testes;
- memória persistente PostgreSQL por thread_id;
- histórico acumulado de conversas.
"""

from __future__ import annotations

from inna_ai.orchestration.react_config import react_enabled_from_environment

import time
import uuid
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

from langgraph.errors import GraphRecursionError
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command

from inna_ai.orchestration.gateway.agentic_rag import agentic_rag_gateway_node as rag_agent_node
from inna_ai.orchestration.gateway.adaptive_gateway_node import adaptive_gateway_node, select_adaptive_gateway_route
from inna_ai.memory.conversation_summary_node import conversation_summary_node
from inna_ai.governance.execution_governance import DEFAULT_MAX_EXECUTION_STEPS, DEFAULT_MAX_SAME_AGENT_VISITS, apply_execution_governance
from inna_ai.agents.supervision.handoff_coordinator_node import handoff_coordinator_node
from inna_ai.governance.hitl.interrupt_node import human_review_interrupt_node, select_route_after_human_review_interrupt
from inna_ai.governance.hitl.policy_node import human_review_policy_node, select_route_after_human_review_policy
from inna_ai.demo.financial_education.financial_agent import financial_agent_node
from inna_ai.demo.financial_education.education_agent import education_agent_node
from inna_ai.orchestration.nodes import report_agent_node
from inna_ai.memory.checkpoint import abrir_checkpointer_postgres
from inna_ai.orchestration.state import InnaAgentState

from inna_ai.orchestration.fallback_node import fallback_agent_node
from inna_ai.agents.supervision.supervisor import supervisor_node
from inna_ai.orchestration.react_node import react_agent_node
from inna_ai.agents.supervision.supervisor_mesh_node import select_supervisor_mesh_route, supervisor_mesh_node
from inna_ai.agents.supervision.task_completion.node import task_completion_node
from inna_ai.agents.routing.team_router import select_team_supervisor_route, team_router_node
from inna_ai.agents.routing.team_supervisor import financial_team_supervisor_node, knowledge_team_supervisor_node, support_team_supervisor_node
from inna_ai.context.node import context_builder_node
from inna_ai.observability.langgraph_tracing import add_langgraph_node_result_attributes, add_langgraph_result_attributes, traced_langgraph_execution, traced_langgraph_node

DEFAULT_LANGGRAPH_RECURSION_LIMIT = 25

ALLOWED_AGENT_ROUTES = frozenset(
    {
        "financial_agent",
        "education_agent",
        "rag_agent",
        "report_agent",
        "react_agent",
        "fallback_agent",
    }
)


class LangGraphExecutionLimitError(
    RuntimeError
):
    """
    Indica que a execução do grafo excedeu
    o limite operacional permitido.
    """


def _criar_config_execucao(
    *,
    thread_id: str | None = None,
) -> dict[str, Any]:
    """
    Cria a configuração central de execução.

    recursion_limit é uma chave de nível superior
    do RunnableConfig do LangGraph.
    """
    config: dict[str, Any] = {
        "recursion_limit": (
            DEFAULT_LANGGRAPH_RECURSION_LIMIT
        ),
    }

    normalized_thread_id = str(
        thread_id or ""
    ).strip()

    if normalized_thread_id:
        config["configurable"] = {
            "thread_id": normalized_thread_id,
        }

    return config


def _invocar_grafo_seguro(
    grafo: Any,
    estado_inicial: InnaAgentState,
    *,
    config: dict[str, Any],
) -> InnaAgentState:
    """
    Executa o grafo com limite explícito.

    Não cria resposta parcial silenciosa quando
    o limite é atingido.
    """
    try:
        return grafo.invoke(
            estado_inicial,
            config=config,
        )
    except GraphRecursionError as error:
        raise LangGraphExecutionLimitError(
            "A execução do núcleo agentic excedeu "
            "o limite máximo de passos permitido."
        ) from error


def _selecionar_rota(
    state: InnaAgentState,
) -> str:
    route = str(
        state.get(
            "next_node",
            "fallback_agent",
        )
        or "fallback_agent"
    ).strip()

    if route not in ALLOWED_AGENT_ROUTES:
        return "fallback_agent"

    return route


def _selecionar_rota_apos_handoff(
    state: InnaAgentState,
) -> str:
    """
    Encaminha handoffs solicitados ao roteador hierárquico.

    Handoffs em estado terminal seguem para o resumo final.
    """
    handoff = state.get(
        "handoff_current"
    )

    if not isinstance(
        handoff,
        dict,
    ):
        return "conversation_summary"

    status = str(
        handoff.get(
            "status",
            "",
        )
        or ""
    ).strip()

    target = str(
        handoff.get(
            "to_agent",
            "",
        )
        or ""
    ).strip()

    if (
        status == "requested"
        and target in ALLOWED_AGENT_ROUTES
    ):
        return "team_router"

    return "conversation_summary"


def _selecionar_saida_adaptive_gateway(
    state: InnaAgentState,
) -> str:
    """
    Mantém o fast path simples.

    Rotas complexas passam pelo Supervisor Mesh antes
    da camada hierárquica de equipes.
    """

    route = select_adaptive_gateway_route(
        state
    )

    if route == "team_router":
        return "supervisor_mesh"

    return route


def _selecionar_saida_supervisor_equipe(
    state: InnaAgentState,
) -> str:
    """
    Decide a saída de um supervisor de equipe.

    Rota normal:
        execution_governance

    Escalonamento entre equipes:
        supervisor

    Quando o limite do supervisor raiz é atingido,
    o nó da equipe prepara fallback_agent e a rota
    segue por execution_governance.
    """
    requires_root = bool(
        state.get(
            "team_requires_root_supervisor",
            False,
        )
    )

    if not requires_root:
        return "execution_governance"

    return "supervisor"

def _observed_control_node(
    node_name: str,
    node,
):
    """
    Instrumenta apenas o control plane multiagente.

    Agentes/LLMs continuam usando seus tracers
    específicos já existentes.
    """

    def observed(
        state: InnaAgentState,
    ):
        with traced_langgraph_node(
            node_name=node_name,
            state=state,
        ) as span:
            result = node(
                state
            )

            add_langgraph_node_result_attributes(
                span,
                result,
            )

            return result

    return observed


def criar_builder_inna() -> StateGraph:
    builder = StateGraph(
        InnaAgentState
    )

    # Entrada e supervisão principal
    builder.add_node(
        "context_builder",
        context_builder_node,
    )

    builder.add_node(
        "supervisor",
        supervisor_node,
    )

    builder.add_node(
        "adaptive_gateway",
        _observed_control_node(
            "adaptive_gateway",
            adaptive_gateway_node,
        ),
    )

    # Camada hierárquica
    builder.add_node(
        "supervisor_mesh",
        _observed_control_node(
            "supervisor_mesh",
            supervisor_mesh_node,
        ),
    )

    builder.add_node(
        "team_router",
        _observed_control_node(
            "team_router",
            team_router_node,
        ),
    )

    builder.add_node(
        "financial_team_supervisor",
        _observed_control_node(
            "financial_team_supervisor",
            financial_team_supervisor_node,
        ),
    )

    builder.add_node(
        "knowledge_team_supervisor",
        _observed_control_node(
            "knowledge_team_supervisor",
            knowledge_team_supervisor_node,
        ),
    )

    builder.add_node(
        "support_team_supervisor",
        _observed_control_node(
            "support_team_supervisor",
            support_team_supervisor_node,
        ),
    )

    # Governança de execução
    builder.add_node(
        "execution_governance",
        _observed_control_node(
            "execution_governance",
            apply_execution_governance,
        ),
    )

    # Agentes especializados
    builder.add_node(
        "financial_agent",
        financial_agent_node,
    )

    builder.add_node(
        "education_agent",
        education_agent_node,
    )

    builder.add_node(
        "rag_agent",
        rag_agent_node,
    )

    builder.add_node(
        "react_agent",
        react_agent_node,
    )

    builder.add_node(
        "report_agent",
        report_agent_node,
    )

    builder.add_node(
        "fallback_agent",
        fallback_agent_node,
    )

    # Finalização e handoffs
    builder.add_node(
        "task_completion",
        _observed_control_node(
            "task_completion",
            task_completion_node,
        ),
    )

    builder.add_node(
        "human_review_policy",
        _observed_control_node(
            "human_review_policy",
            human_review_policy_node,
        ),
    )

    builder.add_node(
        "human_review_interrupt",
        _observed_control_node(
            "human_review_interrupt",
            human_review_interrupt_node,
        ),
    )

    builder.add_node(
        "handoff_coordinator",
        _observed_control_node(
            "handoff_coordinator",
            handoff_coordinator_node,
        ),
    )

    builder.add_node(
        "conversation_summary",
        conversation_summary_node,
    )

    # Entrada principal
    builder.add_edge(
        START,
        "context_builder",
    )

    builder.add_edge(
        "context_builder",
        "supervisor",
    )

    builder.add_edge(
        "supervisor",
        "adaptive_gateway",
    )

    builder.add_conditional_edges(
        "adaptive_gateway",
        _selecionar_saida_adaptive_gateway,
        {
            "execution_governance": "execution_governance",
            "supervisor_mesh": "supervisor_mesh",
        },
    )

    # Supervisor Mesh → hierarquia ou fallback governado.
    builder.add_conditional_edges(
        "supervisor_mesh",
        select_supervisor_mesh_route,
        {
            "team_router": "team_router",
            "execution_governance": "execution_governance",
        },
    )

    # Team Router → Supervisor de equipe
    builder.add_conditional_edges(
        "team_router",
        select_team_supervisor_route,
        {
            (
                "financial_team_supervisor"
            ): "financial_team_supervisor",
            (
                "knowledge_team_supervisor"
            ): "knowledge_team_supervisor",
            (
                "support_team_supervisor"
            ): "support_team_supervisor",
        },
    )

    # Supervisor de equipe → governança, supervisor raiz
    # ou fallback protegido.
    for team_supervisor in (
        "financial_team_supervisor",
        "knowledge_team_supervisor",
        "support_team_supervisor",
    ):
        builder.add_conditional_edges(
            team_supervisor,
            _selecionar_saida_supervisor_equipe,
            {
                (
                    "execution_governance"
                ): "execution_governance",
                "supervisor": "supervisor",
            },
        )

    # Governança → agente especializado
    builder.add_conditional_edges(
        "execution_governance",
        _selecionar_rota,
        {
            "financial_agent": "financial_agent",
            "education_agent": "education_agent",
            "rag_agent": "rag_agent",
            "report_agent": "report_agent",
            "react_agent": "react_agent",
            "fallback_agent": "fallback_agent",
        },
    )

    # Todos os agentes passam por Task Completion.
    for node in ALLOWED_AGENT_ROUTES:
        builder.add_edge(
            node,
            "task_completion",
        )

    # Task Completion → política de revisão humana.
    builder.add_edge(
        "task_completion",
        "human_review_policy",
    )

    # A política segue normalmente ou pausa para revisão.
    builder.add_conditional_edges(
        "human_review_policy",
        select_route_after_human_review_policy,
        {
            (
                "human_review_interrupt"
            ): "human_review_interrupt",
            (
                "handoff_coordinator"
            ): "handoff_coordinator",
        },
    )

    # Após a decisão humana, retoma na rota adequada.
    builder.add_conditional_edges(
        "human_review_interrupt",
        select_route_after_human_review_interrupt,
        {
            (
                "handoff_coordinator"
            ): "handoff_coordinator",
            "team_router": "team_router",
            (
                "conversation_summary"
            ): "conversation_summary",
        },
    )

    # Handoff solicitado volta à camada hierárquica.
    builder.add_conditional_edges(
        "handoff_coordinator",
        _selecionar_rota_apos_handoff,
        {
            "team_router": "team_router",
            (
                "conversation_summary"
            ): "conversation_summary",
        },
    )

    builder.add_edge(
        "conversation_summary",
        END,
    )

    return builder

def criar_grafo_inna(
    *,
    checkpointer: Any | None = None,
):
    return criar_builder_inna().compile(
        checkpointer=checkpointer
    )


inna_agent_graph = criar_grafo_inna()


def _criar_estado_inicial(
    mensagem: str,
    *,
    thread_id: str,
    usuario_id: str | None,
    idioma: str,
    moeda: str,
) -> InnaAgentState:
    mensagem = str(mensagem or "").strip()

    return {
        "user_message": mensagem,
        "user_id": usuario_id,
        "language": idioma,
        "currency": moeda,
        "thread_id": thread_id,
        "execution_id": str(uuid.uuid4()),
        "trace_id": str(uuid.uuid4()),
        "conversation_history": [
            {
                "role": "user",
                "content": mensagem,
            }
        ],
        "a2a_message_count": 0,
        "max_a2a_messages": 0,
        "a2a_history": [],
        "handoff_current": None,
        "handoff_history": [],
        "handoff_count": 0,
        "max_handoffs": 3,
        "handoff_limit_exceeded": False,
        "handoff_required": False,
        "handoff_target": "",
        "handoff_reason": "",

        # Roteamento hierárquico
        "hierarchical_routing_enabled": True,
        "current_team": "",
        "team_supervisor": "",
        "team_route": "",
        "team_requested_agent": "",
        "team_route_source": "",
        "team_routing_reason": "",
        "team_requires_root_supervisor": False,
        "team_route_history": [],
        "root_supervisor_visits": 0,
        "max_root_supervisor_visits": 3,

        # Supervisor Mesh
        "supervisor_mesh_active": False,
        "supervisor_mesh_status": "inactive",
        "supervisor_mesh_plan": {},
        "supervisor_mesh_requested_teams": [],
        "supervisor_mesh_supervisors": [],
        "supervisor_mesh_supervisor_count": 0,
        "supervisor_mesh_history": [],
        "supervisor_mesh_visited_supervisors": [],
        "supervisor_mesh_visited_count": 0,
        "supervisor_mesh_visit_history": [],

        # Governed Shared Blackboard
        "shared_blackboard_entries": [],
        "shared_blackboard_count": 0,
        "max_shared_blackboard_entries": 64,
        "shared_blackboard_audit": [],
        "shared_blackboard_last_decision": {},

        "human_review_enabled": True,
        "human_review_required": False,
        "human_review_current": {},
        "human_review_history": [],
        "human_review_policy_decision": {},
        "human_review_resume_payload": {},
        "human_review_decision_action": "",
        "human_review_corrections": {},
        "human_review_resume_route": "",
        "human_review_status": "",
        "human_review_count": 0,
        "max_human_reviews": 3,
        "human_review_limit_exceeded": False,

        # ReAct governado - desligado por padrao
        "react_enabled": react_enabled_from_environment(),
        "react_requested": False,
        "react_status": "disabled",
        "react_iteration": 0,
        "react_action": {},
        "react_last_observation": {},
        "react_history": [],
        "react_max_iterations": 5,

        "context": {},
        "tool_results": [],
        "errors": [],
        "route_history": [],
        "execution_steps": 0,
        "max_execution_steps": (
            DEFAULT_MAX_EXECUTION_STEPS
        ),
        "max_same_agent_visits": (
            DEFAULT_MAX_SAME_AGENT_VISITS
        ),
        "loop_detected": False,
        "execution_budget_exceeded": False,
        "governance_reason": "",
        "governance_decision": {},
        "trace": [],
    }


def _persistir_execucao_global_best_effort(
    *,
    result: Mapping[str, Any],
    execution_mode: str,
    thread_id: str,
    started_at: datetime | None,
    latency_ms: float | None,
) -> None:
    try:
        try:
            from inna_ai.observability.execution_persistence import persist_langgraph_execution
        except ModuleNotFoundError:
            from inna_ai.observability.execution_persistence import persist_langgraph_execution

        persist_langgraph_execution(
            result,
            execution_mode=execution_mode,
            thread_id=thread_id,
            started_at=started_at,
            latency_ms=latency_ms,
        )

    except Exception:
        # Observabilidade nunca pode
        # interromper a execucao principal.
        return


def executar_nucleo_inna(
    mensagem: str,
    *,
    usuario_id: str | None = None,
    idioma: str = "pt",
    moeda: str = "BRL",
) -> InnaAgentState:
    """
    Execução sem persistência.

    Mantida para compatibilidade e testes unitários.
    """
    thread_id = str(uuid.uuid4())

    execution_started_at = datetime.now(
        timezone.utc
    )

    execution_started_monotonic = (
        time.monotonic()
    )

    estado_inicial = _criar_estado_inicial(
        mensagem,
        thread_id=thread_id,
        usuario_id=usuario_id,
        idioma=idioma,
        moeda=moeda,
    )

    # A retomada Human-in-the-Loop depende de
    # checkpoint persistente. A execução legada,
    # sem persistência, continua compatível.
    estado_inicial[
        "human_review_enabled"
    ] = False

    config = _criar_config_execucao()

    with traced_langgraph_execution(
        execution_mode="non_persistent",
        thread_id=thread_id,
        user_id=usuario_id,
        language=idioma,
        currency=moeda,
        human_review_enabled=False,
    ) as span:
        result = _invocar_grafo_seguro(
            inna_agent_graph,
            estado_inicial,
            config=config,
        )

        add_langgraph_result_attributes(
            span,
            result,
        )

        _persistir_execucao_global_best_effort(
            result=result,
            execution_mode="non_persistent",
            thread_id=thread_id,
            started_at=execution_started_at,
            latency_ms=max(
                0.0,
                (
                    time.monotonic()
                    - execution_started_monotonic
                )
                * 1000.0,
            ),
        )

        return result


def executar_nucleo_inna_persistente(
    mensagem: str,
    *,
    thread_id: str,
    usuario_id: str | None = None,
    idioma: str = "pt",
    moeda: str = "BRL",
    human_review_enabled: bool = False,
) -> InnaAgentState:
    """
    Executa o grafo com memória PostgreSQL.

    O mesmo thread_id continua a mesma conversa.
    """
    thread_id = str(thread_id or "").strip()

    if not thread_id:
        raise ValueError(
            "thread_id é obrigatório para "
            "execução persistente."
        )

    if len(thread_id) > 255:
        raise ValueError(
            "thread_id deve possuir no máximo "
            "255 caracteres."
        )

    execution_started_at = datetime.now(
        timezone.utc
    )

    execution_started_monotonic = (
        time.monotonic()
    )

    estado_inicial = _criar_estado_inicial(
        mensagem,
        thread_id=thread_id,
        usuario_id=usuario_id,
        idioma=idioma,
        moeda=moeda,
    )

    # Mantém compatibilidade com chamadas síncronas
    # existentes. O Human-in-the-Loop deve ser
    # habilitado explicitamente pelo consumidor.
    estado_inicial[
        "human_review_enabled"
    ] = bool(
        human_review_enabled
    )

    config = _criar_config_execucao(
        thread_id=thread_id,
    )

    with abrir_checkpointer_postgres() as checkpointer:
        grafo = criar_grafo_inna(
            checkpointer=checkpointer
        )

        with traced_langgraph_execution(
            execution_mode="persistent",
            thread_id=thread_id,
            user_id=usuario_id,
            language=idioma,
            currency=moeda,
            human_review_enabled=(
                human_review_enabled
            ),
        ) as span:
            result = _invocar_grafo_seguro(
                grafo,
                estado_inicial,
                config=config,
            )

            add_langgraph_result_attributes(
                span,
                result,
            )

            _persistir_execucao_global_best_effort(
                result=result,
                execution_mode="persistent",
                thread_id=thread_id,
                started_at=execution_started_at,
                latency_ms=max(
                    0.0,
                    (
                        time.monotonic()
                        - execution_started_monotonic
                    )
                    * 1000.0,
                ),
            )

            return result




def retomar_revisao_humana_persistente(
    *,
    thread_id: str,
    decisao: Mapping[str, Any],
) -> InnaAgentState:
    """
    Retoma uma execução interrompida para revisão.

    O mesmo thread_id utilizado na execução inicial
    é obrigatório para localizar o checkpoint.
    """
    normalized_thread_id = str(
        thread_id or ""
    ).strip()

    if not normalized_thread_id:
        raise ValueError(
            "thread_id é obrigatório para retomar "
            "uma revisão humana."
        )

    if len(normalized_thread_id) > 255:
        raise ValueError(
            "thread_id deve possuir no máximo "
            "255 caracteres."
        )

    if not isinstance(
        decisao,
        Mapping,
    ):
        raise TypeError(
            "decisao deve implementar Mapping."
        )

    normalized_decision = dict(
        decisao
    )

    if not normalized_decision:
        raise ValueError(
            "decisao não pode ser vazia."
        )

    config = _criar_config_execucao(
        thread_id=normalized_thread_id,
    )

    with abrir_checkpointer_postgres() as checkpointer:
        grafo = criar_grafo_inna(
            checkpointer=checkpointer
        )

        with traced_langgraph_execution(
            execution_mode="human_review_resume",
            thread_id=normalized_thread_id,
            human_review_enabled=True,
        ) as span:
            result = grafo.invoke(
                Command(
                    resume=normalized_decision
                ),
                config=config,
            )

            add_langgraph_result_attributes(
                span,
                result,
            )

            _persistir_execucao_global_best_effort(
                result=result,
                execution_mode="human_review_resume",
                thread_id=normalized_thread_id,
                started_at=None,
                latency_ms=None,
            )

    return result


def consultar_estado_conversa(
    *,
    thread_id: str,
) -> dict[str, Any]:
    """
    Retorna o checkpoint atual de uma conversa.
    """
    config = {
        "configurable": {
            "thread_id": thread_id,
        }
    }

    with abrir_checkpointer_postgres() as checkpointer:
        grafo = criar_grafo_inna(
            checkpointer=checkpointer
        )

        snapshot = grafo.get_state(config)

        return {
            "thread_id": thread_id,
            "values": dict(snapshot.values or {}),
            "next": list(snapshot.next or []),
            "created_at": (
                snapshot.created_at
            ),
            "metadata": dict(
                snapshot.metadata or {}
            ),
        }


__all__ = [
    "ALLOWED_AGENT_ROUTES",
    "DEFAULT_LANGGRAPH_RECURSION_LIMIT",
    "LangGraphExecutionLimitError",
    "criar_builder_inna",
    "criar_grafo_inna",
    "inna_agent_graph",
    "executar_nucleo_inna",
    "executar_nucleo_inna_persistente",
    "consultar_estado_conversa",
]





