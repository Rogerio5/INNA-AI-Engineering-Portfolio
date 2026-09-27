"""
Estado compartilhado do núcleo de agentes da INNA.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal, TypedDict


def merge_conversation_history(
    current: list[dict[str, str]] | None,
    update: list[dict[str, str]] | None,
) -> list[dict[str, str]]:
    """
    Combina o histórico de conversa sem duplicações.

    Compatível tanto com atualizações incrementais quanto
    com nós que retornam o estado completo.
    """
    current = list(current or [])
    update = list(update or [])

    if not update:
        return current

    if not current:
        return update

    # O nó pode devolver o histórico completo mais a nova mensagem.
    if (
        len(update) >= len(current)
        and update[: len(current)] == current
    ):
        return update

    resultado = list(current)

    for mensagem in update:
        if not isinstance(mensagem, dict):
            continue

        role = str(
            mensagem.get("role", "")
        ).strip()

        texto = str(
            mensagem.get("content", "")
        ).strip()

        if not role or not texto:
            continue

        normalizada = {
            "role": role,
            "content": texto,
        }

        # Evita apenas duplicação consecutiva.
        # A mesma pergunta pode aparecer novamente mais tarde.
        if resultado and resultado[-1] == normalizada:
            continue

        resultado.append(normalizada)

    return resultado


def merge_handoff_history(
    current: list[dict[str, Any]] | None,
    update: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    """
    Combina o histórico de handoffs sem duplicar registros.

    Quando o mesmo handoff_id aparece novamente, a versão
    mais recente substitui o registro anterior, preservando
    a ordem original do histórico.
    """
    def normalize_records(
        records: list[dict[str, Any]] | None,
    ) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []

        for item in records or []:
            if not isinstance(
                item,
                dict,
            ):
                continue

            record = dict(item)

            handoff_id = str(
                record.get(
                    "handoff_id",
                    "",
                )
            ).strip()

            if not handoff_id:
                continue

            record["handoff_id"] = handoff_id
            normalized.append(record)

        return normalized

    current_items = normalize_records(
        current
    )

    update_items = normalize_records(
        update
    )

    if not update_items:
        return current_items

    if not current_items:
        return update_items

    # Alguns nós podem devolver o histórico completo.
    if (
        len(update_items) >= len(current_items)
        and update_items[: len(current_items)]
        == current_items
    ):
        return update_items

    result = list(current_items)

    positions: dict[str, int] = {}

    for index, item in enumerate(result):
        handoff_id = str(
            item.get(
                "handoff_id",
                "",
            )
        ).strip()

        if handoff_id:
            positions[handoff_id] = index

    for item in update_items:
        handoff_id = str(
            item.get(
                "handoff_id",
                "",
            )
        ).strip()

        if not handoff_id:
            continue

        if handoff_id in positions:
            result[
                positions[handoff_id]
            ] = item
            continue

        positions[handoff_id] = len(result)
        result.append(item)

    return result


IntentType = Literal[
    "diagnostico_financeiro",
    "educacao_financeira",
    "consulta_rag",
    "relatorio",
    "desconhecido",
]


class InnaAgentState(TypedDict, total=False):
    """
    Estado que percorre o grafo da INNA.

    Nenhum dado sensível deve ser registrado neste estado
    sem necessidade explícita.
    """

    user_message: str
    user_id: str | None
    language: str
    currency: str

    thread_id: str
    execution_id: str
    trace_id: str
    conversation_history: Annotated[
        list[dict[str, str]],
        merge_conversation_history,
    ]
    conversation_summary: str

    # Controle e rastreabilidade do resumo da thread.
    conversation_summary_updated: bool
    conversation_summary_version: int
    conversation_summary_source_messages: int
    conversation_summary_source: str

    intent: IntentType
    confidence: float

    # Semana 5 - Adaptive Intent & Complexity Gateway
    adaptive_complexity: Literal["simple", "complex"]
    adaptive_complexity_reason: str
    adaptive_complexity_signals: list[str]
    adaptive_route_type: Literal["simple", "complex", "escalate"]
    adaptive_domain: str
    adaptive_target_supervisor: str
    adaptive_target_agent: str
    adaptive_risk: Literal["low", "medium", "high", "critical"]
    adaptive_reason: str
    adaptive_multi_domain: bool
    adaptive_budget: dict[str, int]

    next_node: str

    route_source: str
    routing_reason: str
    route_history: list[dict[str, Any]]

    execution_steps: int
    max_execution_steps: int
    max_same_agent_visits: int
    loop_detected: bool
    execution_budget_exceeded: bool
    governance_reason: str
    governance_decision: dict[str, Any]

    use_rag: bool
    agentic_rag_mode: str
    agentic_rag_execution: dict[str, Any]
    agentic_rag_fallback_used: bool
    use_database: bool
    generate_report: bool

    context: dict[str, Any]

    # Agente especializado responsável pela resposta final.
    current_agent: str

    # Evidências da utilização de memória semântica.
    semantic_memory_used: bool
    semantic_memory_operation: str
    semantic_memory_sources: dict[str, str]
    tool_results: list[dict[str, Any]]

    # Contrato formal de conclusão da tarefa.
    task_status: str
    task_requirements: list[str]
    completed_requirements: list[str]
    missing_requirements: list[str]
    task_block_reason: str
    task_completion_score: float
    task_completion_evidence: dict[str, Any]

    # Semana 5 - comunicação Agent-to-Agent governada.
    a2a_message_count: int
    max_a2a_messages: int
    a2a_history: list[dict[str, Any]]

    # Transferência formal de responsabilidade entre agentes.
    handoff_current: dict[str, Any] | None
    handoff_history: Annotated[
        list[dict[str, Any]],
        merge_handoff_history,
    ]
    handoff_count: int
    max_handoffs: int
    handoff_limit_exceeded: bool
    handoff_required: bool
    handoff_target: str
    handoff_reason: str

    # Hierarquia de equipes
    hierarchical_routing_enabled: bool
    current_team: str
    team_supervisor: str
    team_route: str
    team_requested_agent: str
    team_route_source: str
    team_routing_reason: str
    team_requires_root_supervisor: bool
    team_route_history: list[dict[str, Any]]
    root_supervisor_visits: int
    max_root_supervisor_visits: int

    # Semana 5 - Supervisor Mesh governado.
    supervisor_mesh_active: bool
    supervisor_mesh_status: str
    supervisor_mesh_plan: dict[str, Any]
    supervisor_mesh_requested_teams: list[str]
    supervisor_mesh_supervisors: list[str]
    supervisor_mesh_supervisor_count: int
    supervisor_mesh_history: list[dict[str, Any]]
    supervisor_mesh_visited_supervisors: list[str]
    supervisor_mesh_visited_count: int
    supervisor_mesh_visit_history: list[dict[str, Any]]

    # Semana 5 - Shared State / Governed Blackboard.
    shared_blackboard_entries: list[dict[str, Any]]
    shared_blackboard_count: int
    max_shared_blackboard_entries: int
    shared_blackboard_audit: list[dict[str, Any]]
    shared_blackboard_last_decision: dict[str, Any]

    # Human-in-the-Loop
    human_review_enabled: bool
    human_review_required: bool
    human_review_current: dict[str, Any]
    human_review_history: list[dict[str, Any]]
    human_review_policy_decision: dict[str, Any]
    human_review_resume_payload: dict[str, Any]
    human_review_decision_action: str
    human_review_corrections: dict[str, Any]
    human_review_resume_route: str
    human_review_status: str
    human_review_count: int
    max_human_reviews: int
    human_review_limit_exceeded: bool

    # ReAct governado
    react_enabled: bool
    react_requested: bool
    react_status: str
    react_iteration: int
    react_action: dict[str, Any]
    react_last_observation: dict[str, Any]
    react_history: list[dict[str, Any]]
    react_max_iterations: int

    # ReAct -> Human-in-the-Loop
    human_review_force_required: bool

    response: str
    structured_response: dict[str, Any]

    errors: list[str]
    trace: list[str]


__all__ = [
    "IntentType",
    "InnaAgentState",
    "merge_conversation_history",
    "merge_handoff_history",
]



