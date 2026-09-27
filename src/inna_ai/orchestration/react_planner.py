"""Planner estruturado do ReAct governado da INNA.

Não solicita nem armazena chain-of-thought.
O Gemini retorna apenas uma decisão operacional estruturada.
"""

from __future__ import annotations

from typing import Any, Literal

from google.genai import types
from pydantic import BaseModel, Field

from inna_ai.context.privacy_filter import sanitize_sensitive_text
from inna_ai.orchestration.react_agent import REACT_MAX_ITERATIONS, ferramentas_react_disponiveis
from inna_ai.agents.supervision.gemini_client import get_supervisor_client
from inna_ai.observability.llm.tracking import executar_generate_content_observado
from inna_ai.agents.supervision.supervisor_config import get_supervisor_runtime_config


class ReactPlannerDecision(BaseModel):
    """Decisão operacional estruturada do ReAct."""

    action: Literal[
        "tool",
        "finish",
        "human_review",
    ]

    tool_name: str = ""

    arguments: dict[str, Any] = Field(
        default_factory=dict
    )

    final_response: str = ""

    reason_code: str = Field(
        min_length=1,
        max_length=80,
    )

    confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
    )


def _catalogo_react_prompt() -> str:
    tools = ferramentas_react_disponiveis()

    if not tools:
        return "Nenhuma ferramenta disponível."

    blocos: list[str] = []

    for tool in tools:
        blocos.append(
            "\n".join(
                [
                    f"- name: {tool['name']}",
                    f"  description: {tool['description']}",
                    f"  input_schema: {tool['input_schema']}",
                ]
            )
        )

    return "\n".join(blocos)


def _observacoes_seguras(
    history: list[dict[str, Any]] | None,
) -> str:
    if not history:
        return "Nenhuma observação anterior."

    linhas: list[str] = []

    for item in history[-REACT_MAX_ITERATIONS:]:
        if not isinstance(item, dict):
            continue

        linhas.append(
            str(
                {
                    "iteration": item.get(
                        "iteration"
                    ),
                    "tool_name": item.get(
                        "tool_name"
                    ),
                    "status": item.get(
                        "status"
                    ),
                    "output": item.get(
                        "output",
                        {},
                    ),
                }
            )
        )

    return "\n".join(linhas) or (
        "Nenhuma observação anterior."
    )


def criar_prompt_react(
    *,
    user_message: str,
    iteration: int,
    history: list[dict[str, Any]] | None = None,
) -> str:
    mensagem, _ = sanitize_sensitive_text(
        str(user_message or "").strip()
    )

    return f"""
Você é o planner operacional ReAct da INNA.

Sua função é escolher somente a próxima ação operacional.

Você NÃO deve:
- revelar raciocínio interno;
- produzir chain-of-thought;
- inventar ferramentas;
- executar código;
- criar nomes de ferramentas inexistentes;
- tomar decisões financeiras irreversíveis.

Ações permitidas:

1. tool
   Use uma ferramenta disponível.

2. finish
   Finalize quando já houver informação suficiente.

3. human_review
   Solicite revisão humana quando a execução exigir
   decisão sensível, autorização ou houver incerteza alta.

Iteração atual:
{iteration}

Limite:
{REACT_MAX_ITERATIONS}

Ferramentas autorizadas:
{_catalogo_react_prompt()}

Mensagem protegida do usuário:
{mensagem}

Observações anteriores:
{_observacoes_seguras(history)}

Regras:
- tool_name deve existir no catálogo quando action=tool.
- arguments devem respeitar o schema da ferramenta.
- Para finish, tool_name deve ser vazio.
- Para human_review, tool_name deve ser vazio.
- reason_code deve ser curto e categórico.
- final_response deve ser preenchida apenas em finish.
- Se estiver na última iteração, prefira finish ou human_review.
""".strip()


def planejar_proxima_acao_react(
    *,
    user_message: str,
    iteration: int,
    history: list[dict[str, Any]] | None = None,
    usuario_id: str | None = None,
    trace_id: str | None = None,
    request_id: str | None = None,
) -> ReactPlannerDecision:
    if iteration < 1:
        raise ValueError(
            "iteration deve ser maior ou igual a 1."
        )

    if iteration > REACT_MAX_ITERATIONS:
        raise ValueError(
            "Limite de iterações ReAct excedido."
        )

    prompt = criar_prompt_react(
        user_message=user_message,
        iteration=iteration,
        history=history,
    )

    runtime_config = (
        get_supervisor_runtime_config()
    )

    client = get_supervisor_client()

    response = executar_generate_content_observado(
        client,
        modelo=runtime_config.model,
        contents=prompt,
        config=types.GenerateContentConfig(
            temperature=0.0,
            max_output_tokens=(
                runtime_config.max_output_tokens
            ),
            response_mime_type="application/json",
            # JSON validado localmente pelo ReactPlannerDecision.
        ),
        operacao="react_planner",
        origem="react_agent",
        usuario_id=usuario_id,
        trace_id=trace_id,
        request_id=request_id,
        metadados={
            "react_iteration": iteration,
            "conteudo_registrado": False,
        },
    )

    parsed = getattr(
        response,
        "parsed",
        None,
    )

    if isinstance(
        parsed,
        ReactPlannerDecision,
    ):
        decision = parsed

    elif parsed is not None:
        decision = (
            ReactPlannerDecision.model_validate(
                parsed
            )
        )

    else:
        text = str(
            getattr(
                response,
                "text",
                "",
            )
            or ""
        ).strip()

        if not text:
            raise RuntimeError(
                "Gemini não retornou decisão ReAct."
            )

        decision = (
            ReactPlannerDecision.model_validate_json(
                text
            )
        )

    available_tools = {
        item["name"]
        for item in ferramentas_react_disponiveis()
    }

    if decision.action == "tool":
        if decision.tool_name not in available_tools:
            raise RuntimeError(
                "Planner solicitou ferramenta "
                "não autorizada."
            )

    else:
        decision.tool_name = ""
        decision.arguments = {}

    if (
        iteration >= REACT_MAX_ITERATIONS
        and decision.action == "tool"
    ):
        return ReactPlannerDecision(
            action="human_review",
            tool_name="",
            arguments={},
            final_response="",
            reason_code=(
                "react_iteration_limit_reached"
            ),
            confidence=decision.confidence,
        )

    return decision


__all__ = [
    "ReactPlannerDecision",
    "criar_prompt_react",
    "planejar_proxima_acao_react",
]



