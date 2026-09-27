"""
Classificador LLM do supervisor híbrido da INNA.

O Gemini é chamado somente quando as regras determinísticas
não conseguem classificar a intenção com segurança.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from google.genai import types

from inna_ai.agents.supervision.gemini_client import get_supervisor_client
from inna_ai.agents.supervision.supervisor_config import DEFAULT_SUPERVISOR_MODEL, get_gemini_api_key, get_supervisor_runtime_config

from inna_ai.orchestration.contracts import SupervisorDecision, SupervisorLLMDecision
from inna_ai.context.privacy_filter import sanitize_sensitive_text


load_dotenv(
    dotenv_path=Path(".env"),
    override=False,
)




_INTENT_ROUTE_MAP = {
    "diagnostico_financeiro": "financial_agent",
    "historico_financeiro": "financial_agent",
    "educacao_financeira": "education_agent",
    "consulta_rag": "rag_agent",
    "relatorio": "report_agent",
    "desconhecido": "fallback_agent",
}


def obter_gemini_api_key() -> str:
    return get_gemini_api_key()


def obter_modelo_supervisor() -> str:
    return (
        get_supervisor_runtime_config()
        .model
    )


def _normalizar_contexto(
    context: dict[str, Any] | None,
) -> str:
    if not isinstance(context, dict):
        return ""

    rendered_prompt = str(
        context.get("rendered_prompt", "")
    ).strip()

    context_limit = (
        get_supervisor_runtime_config()
        .max_context_characters
    )

    if len(rendered_prompt) > context_limit:
        rendered_prompt = (
            rendered_prompt[:context_limit]
            + "\n[CONTEXTO LIMITADO]"
        )

    return rendered_prompt



def _obter_mensagem_protegida(
    mensagem: str,
    context: dict[str, Any] | None,
) -> str:
    """
    Prioriza a mensagem já sanitizada pelo Context Builder.

    Caso o contexto não esteja disponível, aplica o filtro
    de privacidade localmente antes da chamada ao Gemini.
    """
    mensagem_original = str(
        mensagem or ""
    ).strip()

    if isinstance(context, dict):
        mensagem_contexto = str(
            context.get(
                "current_message",
                "",
            )
        ).strip()

        if mensagem_contexto:
            return mensagem_contexto

    mensagem_protegida, _ = (
        sanitize_sensitive_text(
            mensagem_original
        )
    )

    return mensagem_protegida

def _validar_compatibilidade(
    decision: SupervisorLLMDecision,
) -> SupervisorLLMDecision:
    expected_node = _INTENT_ROUTE_MAP[
        decision.intent
    ]

    if decision.next_node != expected_node:
        decision.next_node = expected_node

    decision.use_rag = False
    decision.use_database = False
    decision.generate_report = False

    if decision.intent == "diagnostico_financeiro":
        decision.use_database = True

    elif decision.intent == "historico_financeiro":
        decision.use_database = True

    elif decision.intent == "educacao_financeira":
        decision.use_rag = True

    elif decision.intent == "consulta_rag":
        decision.use_rag = True

    elif decision.intent == "relatorio":
        decision.use_database = True
        decision.generate_report = True

    return decision


def _criar_prompt_classificacao(
    *,
    mensagem: str,
    contexto: str,
) -> str:
    return f"""
Você é o Supervisor de Roteamento da INNA, uma plataforma
de educação e organização financeira.

Classifique a solicitação em exatamente uma intenção:

1. diagnostico_financeiro
   O usuário informa ou quer analisar renda, gastos,
   dívidas, saldo, orçamento, parcelas ou a situação
   financeira atual.

2. historico_financeiro
   O usuário solicita diagnósticos anteriores,
   score anterior, evolução financeira ou histórico
   financeiro vinculado à própria conta.

3. educacao_financeira
   O usuário busca orientação, planejamento, hábitos,
   organização, economia ou passos educativos.

4. consulta_rag
   O usuário faz uma pergunta conceitual que precisa
   consultar a base de conhecimento financeiro.

5. relatorio
   O usuário solicita PDF, relatório, exportação ou
   documento baseado em dados existentes.

6. desconhecido
   A mensagem não permite identificar uma solicitação
   financeira ou está fora do escopo da INNA.

Rotas obrigatórias:
- diagnostico_financeiro -> financial_agent
- historico_financeiro -> financial_agent
- educacao_financeira -> education_agent
- consulta_rag -> rag_agent
- relatorio -> report_agent
- desconhecido -> fallback_agent

Regras:
- Não invente agentes ou ferramentas.
- Não execute nenhuma ação.
- Não responda à pergunta do usuário.
- Apenas classifique.
- Use o contexto anterior somente para resolver referências.
- Caso a intenção continue incerta, use desconhecido.
- Confiança deve ficar entre 0 e 1.
- A justificativa deve ser curta e objetiva.

CONTEXTO PROTEGIDO:
{contexto or "Nenhum contexto anterior disponível."}

MENSAGEM ATUAL:
{mensagem}
""".strip()


def classificar_com_gemini(
    *,
    mensagem: str,
    context: dict[str, Any] | None = None,
) -> SupervisorDecision:
    mensagem_original = str(
        mensagem or ""
    ).strip()

    if len(mensagem_original) < 2:
        raise ValueError(
            "Mensagem insuficiente para classificação."
        )

    mensagem_protegida = (
        _obter_mensagem_protegida(
            mensagem_original,
            context,
        )
    )

    contexto = _normalizar_contexto(
        context
    )

    prompt = _criar_prompt_classificacao(
        mensagem=mensagem_protegida,
        contexto=contexto,
    )

    inicio = time.perf_counter()

    runtime_config = (
        get_supervisor_runtime_config()
    )

    client = get_supervisor_client()

    response = client.models.generate_content(
        model=runtime_config.model,
        contents=prompt,
        config=types.GenerateContentConfig(
            temperature=0.0,
            max_output_tokens=(
                runtime_config.max_output_tokens
            ),
            response_mime_type="application/json",
            response_schema=SupervisorLLMDecision,
        ),
    )

    duration_ms = int(
        (time.perf_counter() - inicio)
        * 1000
    )

    parsed = getattr(
        response,
        "parsed",
        None,
    )

    if isinstance(
        parsed,
        SupervisorLLMDecision,
    ):
        llm_decision = parsed

    elif parsed is not None:
        llm_decision = (
            SupervisorLLMDecision.model_validate(
                parsed
            )
        )

    else:
        response_text = str(
            getattr(response, "text", "")
            or ""
        ).strip()

        if not response_text:
            raise RuntimeError(
                "Gemini não retornou uma "
                "classificação estruturada."
            )

        llm_decision = (
            SupervisorLLMDecision.model_validate_json(
                response_text
            )
        )

    llm_decision = _validar_compatibilidade(
        llm_decision
    )

    return SupervisorDecision(
        **llm_decision.model_dump(),
        classification_source="gemini",
        classification_duration_ms=duration_ms,
        gemini_called=True,
        fallback_used=False,
        classification_error=None,
    )


__all__ = [
    "DEFAULT_SUPERVISOR_MODEL",
    "obter_gemini_api_key",
    "obter_modelo_supervisor",
    "classificar_com_gemini",
]
