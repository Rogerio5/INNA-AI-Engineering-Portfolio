"""
Nó de avaliação formal da conclusão de tarefas da INNA.

O nó consolida evidências produzidas pelos agentes,
avalia os requisitos da solicitação e registra o estado
formal de conclusão antes do resumo conversacional.
"""

from __future__ import annotations

from typing import Any

from inna_ai.orchestration.state import InnaAgentState
from inna_ai.agents.supervision.task_completion.contracts import evaluate_task_completion
from inna_ai.agents.supervision.task_completion.blackboard import publish_task_completion_blackboard

SPECIALIZED_AGENTS = {
    "financial_agent",
    "education_agent",
    "rag_agent",
    "report_agent",
    "react_agent",
    "fallback_agent",
}


def _normalize_text(
    value: Any,
) -> str:
    return str(
        value or ""
    ).strip()


def _resolve_current_agent(
    state: InnaAgentState,
) -> str:
    """
    Resolve o agente efetivamente executado.

    Prioridade:
    1. current_agent explícito;
    2. next_node quando aponta para agente especializado;
    3. último evento agent:<nome> presente no trace.
    """
    explicit_agent = _normalize_text(
        state.get(
            "current_agent",
            "",
        )
    )

    if explicit_agent in SPECIALIZED_AGENTS:
        return explicit_agent

    next_node = _normalize_text(
        state.get(
            "next_node",
            "",
        )
    )

    if next_node in SPECIALIZED_AGENTS:
        return next_node

    trace = state.get(
        "trace",
        [],
    )

    for item in reversed(
        list(trace or [])
    ):
        normalized = _normalize_text(
            item
        )

        if not normalized.startswith(
            "agent:"
        ):
            continue

        candidate = normalized.split(
            ":",
            1,
        )[1].strip()

        if candidate in SPECIALIZED_AGENTS:
            return candidate

    return ""



def _requirements_for_state(
    state: InnaAgentState,
) -> list[str]:
    """
    Define os requisitos mínimos de acordo com a intenção.
    """
    intent = _normalize_text(
        state.get(
            "intent",
            "desconhecido",
        )
    )

    if intent == "diagnostico_financeiro":
        return [
            "agent_execution",
            "financial_inputs_resolved",
            "financial_calculation_executed",
            "response_generation",
        ]

    if intent == "relatorio":
        return [
            "agent_execution",
            "report_generation",
            "response_generation",
        ]

    if intent in {
        "educacao_financeira",
        "consulta_rag",
    }:
        return [
            "agent_execution",
            "rag_retrieval_executed",
            "response_generation",
        ]

    return [
        "agent_execution",
        "response_generation",
    ]



def _has_report_evidence(
    *,
    current_agent: str,
    structured_response: Any,
    tool_results: Any,
) -> bool:
    if current_agent == "report_agent":
        return True

    if isinstance(
        structured_response,
        dict,
    ):
        report_keys = {
            "report",
            "relatorio",
            "report_data",
            "prepared_report",
        }

        if any(
            key in structured_response
            and bool(
                structured_response.get(
                    key
                )
            )
            for key in report_keys
        ):
            return True

    if isinstance(
        tool_results,
        list,
    ):
        for result in tool_results:
            if not isinstance(
                result,
                dict,
            ):
                continue

            tool_name = _normalize_text(
                result.get(
                    "tool_name",
                    result.get(
                        "name",
                        "",
                    ),
                )
            ).lower()

            if (
                "report" in tool_name
                or "relatorio" in tool_name
            ):
                return True

    return False


def _financial_inputs_resolved(
    state: InnaAgentState,
) -> bool:
    structured_response = state.get(
        "structured_response",
        {},
    )

    if not isinstance(
        structured_response,
        dict,
    ):
        return False

    resolution = structured_response.get(
        "financial_input_resolution",
        {},
    )

    return (
        isinstance(
            resolution,
            dict,
        )
        and resolution.get("ready") is True
        and not resolution.get(
            "missing_fields",
            [],
        )
    )



def _rag_retrieval_executed(
    state: InnaAgentState,
) -> bool:
    """
    Confirma execução RAG bem-sucedida com evidência
    de fontes ou documentos recuperados.
    """
    tool_results = state.get(
        "tool_results",
        [],
    )

    successful_tool = False

    if isinstance(tool_results, list):
        for item in tool_results:
            if not isinstance(item, dict):
                continue

            tool_name = _normalize_text(
                item.get(
                    "tool",
                    item.get(
                        "tool_name",
                        item.get("name", ""),
                    ),
                )
            ).lower()

            successful = (
                item.get("ok") is True
                or item.get("status")
                in {
                    "success",
                    "completed",
                    "ok",
                }
            )

            if (
                tool_name
                == "buscar_conhecimento_rag"
                and successful
            ):
                successful_tool = True
                break

    structured_response = state.get(
        "structured_response",
        {},
    )

    if not isinstance(
        structured_response,
        dict,
    ):
        return False

    rag_execution = structured_response.get(
        "rag_execution",
        {},
    )

    if not isinstance(
        rag_execution,
        dict,
    ):
        return False

    retrieved_documents = rag_execution.get(
        "retrieved_documents",
        0,
    )

    try:
        retrieved_documents = int(
            retrieved_documents or 0
        )
    except (TypeError, ValueError):
        retrieved_documents = 0

    sources = rag_execution.get(
        "sources",
        [],
    )

    has_sources = (
        isinstance(sources, (list, tuple))
        and any(
            _normalize_text(source)
            for source in sources
        )
    )

    return (
        successful_tool
        and (
            retrieved_documents > 0
            or has_sources
        )
    )


def _financial_calculation_executed(
    state: InnaAgentState,
) -> bool:
    tool_results = state.get(
        "tool_results",
        [],
    )

    if not isinstance(
        tool_results,
        list,
    ):
        return False

    financial_markers = (
        "finance",
        "financial",
        "diagnostico",
        "diagnóstico",
        "calcular",
        "calculo",
        "cálculo",
    )

    for item in tool_results:
        if not isinstance(
            item,
            dict,
        ):
            continue

        tool_name = _normalize_text(
            item.get(
                "tool",
                item.get(
                    "tool_name",
                    item.get(
                        "name",
                        "",
                    ),
                ),
            )
        ).lower()

        successful = (
            item.get("ok") is True
            or item.get("status")
            in {
                "success",
                "completed",
                "ok",
            }
        )

        if (
            successful
            and any(
                marker in tool_name
                for marker in financial_markers
            )
        ):
            return True

    return False



def _completed_requirements(
    state: InnaAgentState,
    requirements: list[str],
    *,
    current_agent: str,
) -> list[str]:
    completed: list[str] = []

    response = _normalize_text(
        state.get(
            "response",
            "",
        )
    )

    structured_response = state.get(
        "structured_response",
        {},
    )

    tool_results = state.get(
        "tool_results",
        [],
    )

    if current_agent:
        completed.append(
            "agent_execution"
        )

    if (
        "financial_inputs_resolved"
        in requirements
        and _financial_inputs_resolved(
            state
        )
    ):
        completed.append(
            "financial_inputs_resolved"
        )

    if (
        "financial_calculation_executed"
        in requirements
        and _financial_calculation_executed(
            state
        )
    ):
        completed.append(
            "financial_calculation_executed"
        )

    if (
        "rag_retrieval_executed"
        in requirements
        and _rag_retrieval_executed(
            state
        )
    ):
        completed.append(
            "rag_retrieval_executed"
        )

    requires_rag = (
        "rag_retrieval_executed"
        in requirements
    )

    response_generated = (
        _is_substantive_response(response)
        if requires_rag
        else bool(response)
    )

    if response_generated:
        completed.append(
            "response_generation"
        )

    if (
        "report_generation"
        in requirements
        and _has_report_evidence(
            current_agent=current_agent,
            structured_response=(
                structured_response
            ),
            tool_results=tool_results,
        )
    ):
        completed.append(
            "report_generation"
        )

    return completed





def _is_substantive_response(
    response: str,
) -> bool:
    """
    Impede que placeholders e mensagens de roteamento
    sejam considerados respostas finais.
    """
    normalized = _normalize_text(
        response
    ).lower()

    if not normalized:
        return False

    placeholders = (
        "a solicitação foi encaminhada",
        "a solicitacao foi encaminhada",
        "foi encaminhada para o agente",
        "integrar conteúdo do rag",
        "integrar conteudo do rag",
        "processando sua solicitação",
        "processando sua solicitacao",
    )

    if any(
        marker in normalized
        for marker in placeholders
    ):
        return False

    return len(
        normalized.split()
    ) >= 8


def _requires_user_input(
    response: str,
) -> bool:
    normalized = response.lower()

    markers = (
        "preciso que você informe",
        "preciso que voce informe",
        "informe os dados",
        "faltam informações",
        "faltam informacoes",
        "ainda preciso",
        "envie os valores",
        "forneça os dados",
        "forneca os dados",
    )

    return (
        bool(normalized)
        and any(
            marker in normalized
            for marker in markers
        )
    )


def task_completion_node(
    state: InnaAgentState,
) -> dict[str, Any]:
    """
    Avalia formalmente se a tarefa foi concluída.
    """
    current_agent = (
        _resolve_current_agent(
            state
        )
    )

    requirements = (
        _requirements_for_state(
            state
        )
    )

    completed = (
        _completed_requirements(
            state,
            requirements,
            current_agent=current_agent,
        )
    )

    errors = [
        _normalize_text(error)
        for error in state.get(
            "errors",
            [],
        )
        if _normalize_text(error)
    ]

    response = _normalize_text(
        state.get(
            "response",
            "",
        )
    )

    needs_user_input = (
        _requires_user_input(
            response
        )
    )

    failed = bool(errors)

    block_reason = ""

    if failed:
        block_reason = errors[-1]

    elif needs_user_input:
        block_reason = (
            "A execução depende de informações "
            "adicionais do usuário."
        )

    tool_results = state.get(
        "tool_results",
        [],
    )

    result = evaluate_task_completion(
        requirements=requirements,
        completed=completed,
        needs_user_input=(
            needs_user_input
        ),
        failed=failed,
        block_reason=block_reason,
        evidence={
            "intent": state.get(
                "intent"
            ),
            "agent": (
                current_agent or None
            ),
            "agent_resolution": (
                "explicit_or_inferred"
                if current_agent
                else "unresolved"
            ),
            "tool_results_count": (
                len(tool_results)
                if isinstance(
                    tool_results,
                    list,
                )
                else 0
            ),
            "has_response": bool(
                response
            ),
        },
    )

    trace = list(
        state.get(
            "trace",
            [],
        )
    )

    trace.append(
        "task_completion:"
        f"{result['task_status']}:"
        f"{result['task_completion_score']}"
    )

    completion_update = {
        **result,
        "current_agent": current_agent,
        "trace": trace,
    }

    blackboard_update = (
        publish_task_completion_blackboard(
            state,
            completion_update,
        )
    )

    return {
        **completion_update,
        **blackboard_update,
    }


__all__ = [
    "task_completion_node",
]

