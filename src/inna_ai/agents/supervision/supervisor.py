"""
Supervisor híbrido da INNA.

Fluxo:
1. Usa regras determinísticas em mensagens claras.
2. Usa Gemini com saída Pydantic em casos ambíguos.
3. Usa fallback seguro quando a classificação falha.
"""

from __future__ import annotations

import time
import unicodedata
from typing import Any

from inna_ai.orchestration.contracts import SupervisorDecision
from inna_ai.orchestration.state import InnaAgentState
from inna_ai.agents.supervision.supervisor_deadline import classificar_com_gemini_com_deadline as classificar_com_gemini

MIN_RULE_CONFIDENCE = 0.75
MIN_LLM_CONFIDENCE = 0.60


_REPORT_TERMS = {
    "gerar relatorio",
    "meu relatorio",
    "relatorio em pdf",
    "gerar pdf",
    "baixar pdf",
    "exportar relatorio",
    "documento financeiro",
}

_FINANCIAL_TERMS = {
    "minha renda",
    "renda:",
    "renda mensal:",
    "gastos fixos:",
    "gastos variáveis:",
    "gastos variaveis:",
    "dívidas:",
    "dividas:",
    "dívidas mensais:",
    "dividas mensais:",
    "reserva:",
    "reserva atual:",
    "ingresos:",
    "gastos fijos:",
    "gastos variables:",
    "deudas:",
    "income:",
    "monthly income:",
    "fixed expenses:",
    "variable expenses:",
    "debts:",
    "reserve:",
    "meus gastos",
    "minhas dividas",
    "tenho renda",
    "ganho ",
    "gasto ",
    "meu saldo",
    "meu orcamento",
    "diagnostico financeiro",
    "score financeiro",
    "minhas parcelas",
    "estou devendo",
}


_HISTORY_TERMS = {
    "meu historico",
    "meu historico financeiro",
    "historico financeiro",
    "historico de diagnosticos",
    "consultar historico",
    "consultar meu historico",
    "meus diagnosticos",
    "ultimos diagnosticos",
    "diagnosticos anteriores",
    "diagnostico anterior",
    "meu score anterior",
    "score anterior",
    "como estava meu score",
    "evolucao do meu score",
    "minha evolucao financeira",
}


def _is_history_request(
    texto: str,
) -> bool:
    if _contains_any(
        texto,
        _HISTORY_TERMS,
    ):
        return True

    temporal_terms = {
        "historico",
        "anterior",
        "anteriores",
        "ultimo",
        "ultimos",
        "ultima",
        "ultimas",
        "evolucao",
    }

    mentions_financial_record = (
        "diagnostico" in texto
        or "score" in texto
    )

    mentions_time = any(
        term in texto
        for term in temporal_terms
    )

    return (
        mentions_financial_record
        and mentions_time
    )


_RAG_TERMS = {
    "o que e",
    "como funciona",
    "qual a diferenca",
    "explique",
    "conceito de",
    "juros compostos",
    "reserva financeira",
    "reserva de emergencia",
    "cartao de credito",
}

_EDUCATION_TERMS = {
    "como organizar",
    "como planejar",
    "como economizar",
    "quero aprender",
    "me de dicas",
    "dicas para",
    "educacao financeira",
    "criar habito",
    "melhorar minhas financas",
}


def _normalizar(texto: str) -> str:
    texto = str(
        texto or ""
    ).strip().lower()

    normalized = unicodedata.normalize(
        "NFKD",
        texto,
    )

    return "".join(
        character
        for character in normalized
        if not unicodedata.combining(
            character
        )
    )


def _contains_any(
    texto: str,
    termos: set[str],
) -> bool:
    return any(
        termo in texto
        for termo in termos
    )


def classificar_intencao_por_regras(
    mensagem: str,
) -> SupervisorDecision:
    """
    Classifica mensagens claras sem chamar o Gemini.
    """
    texto = _normalizar(
        mensagem
    )

    if not texto:
        return SupervisorDecision(
            intent="desconhecido",
            next_node="fallback_agent",
            confidence=0.10,
            reason="Mensagem vazia.",
            classification_source="rule",
        )

    report_match = _contains_any(
        texto,
        _REPORT_TERMS,
    )

    history_match = (
        not report_match
        and _is_history_request(
            texto
        )
    )

    financial_match = (
        not report_match
        and not history_match
        and _contains_any(
            texto,
            _FINANCIAL_TERMS,
        )
    )

    matches = {
        "relatorio": report_match,
        "historico_financeiro": (
            history_match
        ),
        "diagnostico_financeiro": (
            financial_match
        ),
        "consulta_rag": _contains_any(
            texto,
            _RAG_TERMS,
        ),
        "educacao_financeira": (
            _contains_any(
                texto,
                _EDUCATION_TERMS,
            )
        ),
    }

    explicit_education_match = _contains_any(
        texto,
        (
            "de forma educativa",
            "explique de forma educativa",
            "orientação educativa",
            "orientacao educativa",
            "passo a passo educativo",
        ),
    )

    if explicit_education_match:
        return SupervisorDecision(
            intent="educacao_financeira",
            next_node="education_agent",
            confidence=0.95,
            use_rag=False,
            reason=(
                "A mensagem solicita explicitamente "
                "uma explicação educativa."
            ),
            classification_source="rule",
        )

    matched_intents = [
        intent
        for intent, matched in matches.items()
        if matched
    ]

    if len(matched_intents) > 1:
        return SupervisorDecision(
            intent="desconhecido",
            next_node="fallback_agent",
            confidence=0.45,
            reason=(
                "Mais de uma intenção foi identificada "
                "pelas regras."
            ),
            classification_source="rule",
        )

    if matched_intents == [
        "historico_financeiro"
    ]:
        return SupervisorDecision(
            intent="historico_financeiro",
            next_node="financial_agent",
            confidence=0.96,
            use_database=True,
            reason=(
                "A mensagem solicita diagnósticos "
                "financeiros anteriores do usuário."
            ),
            classification_source="rule",
        )

    if matched_intents == ["relatorio"]:
        return SupervisorDecision(
            intent="relatorio",
            next_node="report_agent",
            confidence=0.96,
            use_database=True,
            generate_report=True,
            reason=(
                "A mensagem solicita relatório, "
                "PDF ou exportação."
            ),
            classification_source="rule",
        )

    if matched_intents == [
        "diagnostico_financeiro"
    ]:
        return SupervisorDecision(
            intent="diagnostico_financeiro",
            next_node="financial_agent",
            confidence=0.92,
            use_database=True,
            reason=(
                "A mensagem contém dados ou uma "
                "situação financeira pessoal."
            ),
            classification_source="rule",
        )

    if matched_intents == ["consulta_rag"]:
        return SupervisorDecision(
            intent="consulta_rag",
            next_node="rag_agent",
            confidence=0.89,
            use_rag=True,
            reason=(
                "A mensagem solicita explicação de "
                "um conceito financeiro."
            ),
            classification_source="rule",
        )

    if matched_intents == [
        "educacao_financeira"
    ]:
        return SupervisorDecision(
            intent="educacao_financeira",
            next_node="education_agent",
            confidence=0.86,
            use_rag=True,
            reason=(
                "A mensagem solicita orientação "
                "educativa ou planejamento."
            ),
            classification_source="rule",
        )

    return SupervisorDecision(
        intent="desconhecido",
        next_node="fallback_agent",
        confidence=0.40,
        reason=(
            "As regras não identificaram uma "
            "intenção suficientemente clara."
        ),
        classification_source="rule",
    )


def classificar_intencao(
    mensagem: str,
) -> SupervisorDecision:
    """
    Compatibilidade com os módulos anteriores.

    Esta função usa somente regras determinísticas.
    """
    return classificar_intencao_por_regras(
        mensagem
    )


def classificar_intencao_hibrida(
    mensagem: str,
    *,
    context: dict[str, Any] | None = None,
) -> SupervisorDecision:
    """
    Usa regras primeiro e Gemini somente quando necessário.
    """
    start = time.perf_counter()

    rule_decision = (
        classificar_intencao_por_regras(
            mensagem
        )
    )

    clear_rule = (
        rule_decision.intent
        != "desconhecido"
        and rule_decision.confidence
        >= MIN_RULE_CONFIDENCE
    )

    if clear_rule:
        rule_decision.classification_duration_ms = (
            int(
                (
                    time.perf_counter()
                    - start
                )
                * 1000
            )
        )

        return rule_decision

    try:
        llm_decision = classificar_com_gemini(
            mensagem=mensagem,
            context=context,
        )

        if (
            llm_decision.confidence
            >= MIN_LLM_CONFIDENCE
        ):
            return llm_decision

        return SupervisorDecision(
            intent="desconhecido",
            next_node="fallback_agent",
            confidence=(
                llm_decision.confidence
            ),
            reason=(
                "A classificação do Gemini ficou "
                "abaixo do limite mínimo de confiança."
            ),
            classification_source="fallback",
            classification_duration_ms=(
                llm_decision
                .classification_duration_ms
            ),
            gemini_called=True,
            fallback_used=True,
            classification_error=None,
        )

    except Exception as exc:
        duration_ms = int(
            (
                time.perf_counter()
                - start
            )
            * 1000
        )

        return SupervisorDecision(
            intent="desconhecido",
            next_node="fallback_agent",
            confidence=0.20,
            reason=(
                "Não foi possível determinar uma "
                "intenção segura."
            ),
            classification_source="fallback",
            classification_duration_ms=duration_ms,
            gemini_called=True,
            fallback_used=True,
            classification_error=(
                type(exc).__name__
            ),
        )


def _detectar_pedido_diagnostico(
    mensagem: str,
) -> bool:
    """
    Detecta solicitações explícitas de análise ou
    diagnóstico da situação financeira do usuário.

    Não classifica perguntas conceituais nem pedidos
    isolados de relatório.
    """
    normalized = str(
        mensagem or ""
    ).strip().lower()

    if not normalized:
        return False

    diagnostic_markers = (
        "analise minha situação financeira",
        "analise minha situacao financeira",
        "análise minha situação financeira",
        "análise minha situacao financeira",
        "analisar minha situação financeira",
        "analisar minha situacao financeira",
        "faça um diagnóstico financeiro",
        "faca um diagnostico financeiro",
        "faça um diagnóstico das minhas finanças",
        "faca um diagnostico das minhas financas",
        "diagnóstico da minha situação financeira",
        "diagnostico da minha situacao financeira",
        "avalie minha situação financeira",
        "avalie minha situacao financeira",
        "avalie minhas finanças",
        "avalie minhas financas",
        "verifique minha situação financeira",
        "verifique minha situacao financeira",
        "como está minha situação financeira",
        "como esta minha situacao financeira",
    )

    return any(
        marker in normalized
        for marker in diagnostic_markers
    )


def _detectar_diagnostico_com_relatorio(
    mensagem: str,
) -> bool:
    """
    Detecta uma solicitação composta que exige primeiro
    diagnóstico financeiro e depois geração de relatório.

    Um pedido simples de relatório continua seguindo
    diretamente para o report_agent.
    """
    normalized = str(
        mensagem or ""
    ).strip().lower()

    if not normalized:
        return False

    report_markers = (
        "relatório",
        "relatorio",
        "pdf",
        "exportar",
        "exportação",
        "exportacao",
        "documento",
    )

    financial_analysis_markers = (
        "analise minha",
        "análise minha",
        "analisar minha",
        "diagnóstico",
        "diagnostico",
        "minha situação financeira",
        "minha situacao financeira",
        "meu orçamento",
        "meu orcamento",
        "minha renda",
        "meus gastos",
        "minhas dívidas",
        "minhas dividas",
        "meu saldo",
    )

    has_report_request = any(
        marker in normalized
        for marker in report_markers
    )

    has_financial_analysis = any(
        marker in normalized
        for marker in financial_analysis_markers
    )

    return (
        has_report_request
        and has_financial_analysis
    )


def supervisor_node(
    state: InnaAgentState,
) -> dict[str, Any]:
    """
    Nó LangGraph do supervisor híbrido.
    """
    mensagem = str(
        state.get(
            "user_message",
            "",
        )
    ).strip()

    context = state.get(
        "context",
        {},
    )

    if not isinstance(context, dict):
        context = {}

    decision = classificar_intencao_hibrida(
        mensagem,
        context=context,
    )

    composite_diagnosis_report = (
        _detectar_diagnostico_com_relatorio(
            mensagem
        )
    )

    explicit_diagnosis_request = (
        _detectar_pedido_diagnostico(
            mensagem
        )
    )

    if composite_diagnosis_report:
        decision = SupervisorDecision(
            intent="diagnostico_financeiro",
            next_node="financial_agent",
            confidence=max(
                float(decision.confidence),
                0.97,
            ),
            use_database=True,
            use_rag=False,
            generate_report=True,
            reason=(
                "A mensagem solicita primeiro um "
                "diagnóstico financeiro e depois "
                "a geração de um relatório."
            ),
            classification_source="rule",
            classification_duration_ms=(
                decision.classification_duration_ms
            ),
            gemini_called=(
                decision.gemini_called
            ),
            fallback_used=False,
            classification_error=(
                decision.classification_error
            ),
        )

    elif (
        explicit_diagnosis_request
        and decision.intent == "desconhecido"
    ):
        decision = SupervisorDecision(
            intent="diagnostico_financeiro",
            next_node="financial_agent",
            confidence=0.94,
            use_database=True,
            use_rag=False,
            generate_report=False,
            reason=(
                "A mensagem solicita uma análise "
                "ou diagnóstico da situação "
                "financeira do usuário."
            ),
            classification_source="rule",
            classification_duration_ms=(
                decision.classification_duration_ms
            ),
            gemini_called=(
                decision.gemini_called
            ),
            fallback_used=False,
            classification_error=(
                decision.classification_error
            ),
        )

    structured_response = dict(
        state.get(
            "structured_response",
            {},
        )
    )

    structured_response[
        "supervisor_decision"
    ] = decision.model_dump()

    structured_response[
        "supervisor_metrics"
    ] = {
        "classification_source": (
            decision.classification_source
        ),
        "classification_confidence": (
            decision.confidence
        ),
        "classification_duration_ms": (
            decision.classification_duration_ms
        ),
        "gemini_called": (
            decision.gemini_called
        ),
        "fallback_used": (
            decision.fallback_used
        ),
        "selected_agent": (
            decision.next_node
        ),
        "classification_error": (
            decision.classification_error
        ),
    }

    existing_errors = list(
        state.get(
            "errors",
            [],
        )
        or []
    )

    errors = list(existing_errors)

    if decision.classification_error:
        errors.append(
            decision.classification_error
        )

    existing_trace = list(
        state.get(
            "trace",
            [],
        )
        or []
    )

    existing_route_history = list(
        state.get(
            "route_history",
            [],
        )
        or []
    )

    route_source = str(
        decision.classification_source
        or "fallback"
    ).strip()

    routing_reason = str(
        decision.reason
        or "Motivo de roteamento não informado."
    ).strip()

    route_record = {
        "intent": decision.intent,
        "next_node": decision.next_node,
        "source": route_source,
        "reason": routing_reason,
        "confidence": decision.confidence,
        "fallback_used": (
            decision.fallback_used
        ),
        "gemini_called": (
            decision.gemini_called
        ),
    }

    updated_route_history = [
        *existing_route_history,
        route_record,
    ]

    trace_item = (
        "supervisor:"
        f"{route_source}:"
        f"{decision.intent}"
    )

    updated_trace = [
        *existing_trace,
        trace_item,
    ]

    return {
        "intent": decision.intent,
        "confidence": decision.confidence,
        "next_node": decision.next_node,
        "route_source": route_source,
        "routing_reason": routing_reason,
        "route_history": (
            updated_route_history
        ),
        "use_rag": decision.use_rag,
        "use_database": (
            decision.use_database
        ),
        "generate_report": (
            decision.generate_report
        ),
        "structured_response": (
            structured_response
        ),
        "errors": errors,
        "trace": updated_trace,
    }


__all__ = [
    "MIN_RULE_CONFIDENCE",
    "MIN_LLM_CONFIDENCE",
    "classificar_intencao",
    "classificar_intencao_por_regras",
    "classificar_intencao_hibrida",
    "supervisor_node",
]
