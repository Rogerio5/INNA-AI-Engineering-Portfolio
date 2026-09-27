from __future__ import annotations

import os


# ============================================================
# SAFE/OFFLINE TEST ENVIRONMENT
# ============================================================

os.environ["PHOENIX_ENABLED"] = "false"
os.environ[
    "INNA_KNOWLEDGE_GRAPH_ENABLED"
] = "false"
os.environ[
    "INNA_LLAMAINDEX_AGENTIC_RAG_ENABLED"
] = "false"
os.environ[
    "INNA_DEEPEVAL_ENABLED"
] = "false"
os.environ[
    "INNA_DEEPEVAL_LIVE"
] = "false"


# ============================================================
# IMPORTS
# ============================================================

from inna_ai.agents.registry.agent_catalog import (
    criar_registro_agentes_inna,
)

from inna_ai.governance.hitl.policy import (
    evaluate_human_review_policy,
)

from inna_ai.integrations.mcp.server import (
    obter_manifesto_mcp,
)

from inna_ai.resilience.backoff import (
    calculate_backoff_seconds,
)

from inna_ai.resilience.circuit_breaker import (
    CircuitBreaker,
    CircuitState,
)

from inna_ai.retrieval.agentic.contracts import (
    PlanGenerationMode,
    ResearchSource,
)

from inna_ai.retrieval.agentic.planner import (
    create_research_plan,
)

from inna_ai.retrieval.facade import (
    answer_with_rag,
)

from inna_ai.retrieval.graph.config import (
    load_neo4j_settings,
)

from inna_ai.tools.catalog import (
    criar_registro_ferramentas_inna,
)

from inna_ai.tools.communication_tools import (
    PrepararEmailFinanceiroInput,
    executar_preparacao_email_financeiro,
)

from inna_ai.tools.core import (
    ToolExecutionContext,
)

from inna_ai.tools.financial_history_tools import (
    ConsultarHistoricoFinanceiroInput,
    executar_consulta_historico_financeiro,
)

from inna_ai.tools.financial_tools import (
    CalcularDiagnosticoFinanceiroInput,
    executar_calculo_diagnostico_financeiro,
)

from inna_ai.tools.report_tools import (
    PrepararRelatorioFinanceiroInput,
    RelatorioDiagnosticoItem,
    executar_preparacao_relatorio_financeiro,
)


EXPECTED_TOOL_NAMES = {
    "buscar_conhecimento_rag",
    "calcular_diagnostico_financeiro",
    "consultar_historico_financeiro",
    "preparar_relatorio_financeiro",
    "preparar_email_financeiro",
    "preparar_mensagem_telegram",
}


EXPECTED_AGENT_IDS = {
    "financial_agent",
    "report_agent",
    "education_agent",
    "rag_agent",
    "fallback_agent",
    "research_agent",
    "communication_agent",
}


# ============================================================
# TOOL REGISTRY
# ============================================================

def test_tool_registry_contains_public_tools():
    registry = (
        criar_registro_ferramentas_inna()
    )

    definitions = (
        registry.list_definitions()
    )

    names = {
        item.name
        for item in definitions
    }

    assert names == EXPECTED_TOOL_NAMES
    assert len(definitions) == 6


def test_tool_registry_has_no_duplicate_names():
    registry = (
        criar_registro_ferramentas_inna()
    )

    names = [
        item.name
        for item
        in registry.list_definitions()
    ]

    assert len(names) == len(
        set(names)
    )


# ============================================================
# AGENT REGISTRY
# ============================================================

def test_agent_registry_contains_expected_identities():
    registry = (
        criar_registro_agentes_inna()
    )

    definitions = (
        registry.list_definitions()
    )

    ids = {
        item.agent_id
        for item in definitions
    }

    assert ids == EXPECTED_AGENT_IDS
    assert len(definitions) == 7


def test_agent_and_tool_permissions_are_consistent():
    tools = (
        criar_registro_ferramentas_inna()
    )

    agents = (
        criar_registro_agentes_inna()
    )

    for tool in tools.list_definitions():

        assert tool.allowed_agents

        for agent_id in (
            tool.allowed_agents
        ):
            assert agents.contains(
                agent_id
            )

    for agent in agents.list_definitions():

        for tool_name in (
            agent.allowed_tools
        ):

            assert tools.contains(
                tool_name
            )

            tool = tools.get(
                tool_name
            )

            assert (
                agent.agent_id
                in tool.allowed_agents
            )


# ============================================================
# AGENTIC RAG
# ============================================================

def test_agentic_rag_planner_is_deterministic():
    plan = create_research_plan(
        "Como montar uma reserva de emergência?",
        language="pt",
    )

    assert (
        plan.generation_mode
        == PlanGenerationMode.DETERMINISTIC
    )

    assert (
        plan.complexity.value
        in {
            "simple",
            "complex",
        }
    )

    assert len(
        plan.subqueries
    ) == 1

    step = plan.subqueries[0]

    assert (
        step.source
        == ResearchSource.KNOWLEDGE_BASE
    )

    assert (
        step.tool_name
        == "buscar_conhecimento_rag"
    )

    assert (
        plan.metadata[
            "portfolio"
        ]
        is True
    )


# ============================================================
# FINANCIAL EDUCATION DEMO
# ============================================================

def test_financial_demo_is_deterministic():
    context = ToolExecutionContext(
        requested_by="financial_agent",
        trace_id="test-financial",
    )

    payload = (
        CalcularDiagnosticoFinanceiroInput(
            renda_mensal=5000,
            gastos_fixos=2000,
            gastos_variaveis=500,
            dividas_mensais=500,
            reserva_atual=6000,
            gastos_incluem_dividas=False,
            moeda="BRL",
            idioma="pt",
        )
    )

    result = (
        executar_calculo_diagnostico_financeiro(
            payload,
            context,
        )
    )

    assert result.despesas_totais == 3000
    assert result.saldo_estimado == 2000

    assert (
        result.comprometimento_renda_percentual
        == 60
    )

    assert (
        result.meses_reserva_estimados
        == 2
    )

    assert (
        result.base_calculo
        == "portfolio_education_demo"
    )

    assert (
        result.versao_regra
        == "portfolio_education_v1"
    )


def test_public_history_adapter_returns_no_customer_data():
    context = ToolExecutionContext(
        requested_by="research_agent",
        user_id="portfolio-demo-user",
    )

    payload = (
        ConsultarHistoricoFinanceiroInput(
            limite=5
        )
    )

    result = (
        executar_consulta_historico_financeiro(
            payload,
            context,
        )
    )

    assert (
        result.possui_historico
        is False
    )

    assert result.total_retornado == 0
    assert result.diagnosticos == []


# ============================================================
# COMMUNICATION / HITL BOUNDARY
# ============================================================

def test_communication_tool_never_sends_directly():
    context = ToolExecutionContext(
        requested_by="communication_agent",
        trace_id="test-email",
    )

    payload = (
        PrepararEmailFinanceiroInput(
            destinatario=(
                "portfolio@example.com"
            ),
            assunto=(
                "Exemplo educacional"
            ),
            corpo=(
                "Conteúdo demonstrativo."
            ),
            idioma="pt",
        )
    )

    result = (
        executar_preparacao_email_financeiro(
            payload,
            context,
        )
    )

    assert result.sent is False

    assert (
        result.requires_human_approval
        is True
    )

    assert (
        result.status
        == "pending_approval"
    )

    assert (
        result.recipient_masked
        != "portfolio@example.com"
    )

    assert (
        result.recipient_masked.endswith(
            "@example.com"
        )
    )


def test_hitl_policy_requires_review_for_high_risk():
    decision = (
        evaluate_human_review_policy(
            {
                "risk_level": "high",
            }
        )
    )

    assert (
        decision.requires_review
        is True
    )

    assert (
        decision.trigger
        == "high_financial_risk"
    )

    assert (
        decision.risk_level
        == "high"
    )


# ============================================================
# REPORT DEMO
# ============================================================

def test_report_demo_does_not_recalculate_financial_values():
    context = ToolExecutionContext(
        requested_by="report_agent",
        user_id="portfolio-demo",
    )

    diagnostic = (
        RelatorioDiagnosticoItem(
            saldo_estimado=1250,
            score_financeiro=70,
            nivel_risco="Baixo",
            moeda="BRL",
            idioma="pt",
        )
    )

    payload = (
        PrepararRelatorioFinanceiroInput(
            diagnosticos=[
                diagnostic
            ],
            titulo=(
                "Relatório demonstrativo"
            ),
            recomendacoes=[
                "Manter reserva de emergência."
            ],
            proximos_passos=[
                "Revisar orçamento."
            ],
        )
    )

    result = (
        executar_preparacao_relatorio_financeiro(
            payload,
            context,
        )
    )

    assert (
        result.possui_diagnostico
        is True
    )

    assert result.total_diagnosticos == 1

    assert (
        result.financial_values_recalculated
        is False
    )

    assert (
        result.ready_for_pdf_rendering
        is False
    )


# ============================================================
# RAG FACADE
# ============================================================

def test_rag_facade_validation_does_not_call_backend():
    result = answer_with_rag(
        "x"
    )

    assert (
        result["modo"]
        == "validation_error"
    )

    assert result["fontes"] == []
    assert result["documentos"] == []


# ============================================================
# GRAPH RAG CONFIG
# ============================================================

def test_graph_rag_can_remain_disabled_without_credentials():
    settings = load_neo4j_settings(
        {
            "INNA_KNOWLEDGE_GRAPH_ENABLED":
                "false",
        }
    )

    assert settings.enabled is False
    assert settings.password is None

    assert (
        settings.database
        == "neo4j"
    )


# ============================================================
# RESILIENCE
# ============================================================

def test_backoff_is_deterministic_without_jitter():
    value = calculate_backoff_seconds(
        retry_number=3,
        base_delay_seconds=1,
        max_delay_seconds=10,
        jitter_ratio=0,
    )

    assert value == 4


def test_circuit_breaker_open_half_open_closed_cycle():
    breaker = CircuitBreaker(
        failure_threshold=2,
        recovery_seconds=1.0,
    )

    assert (
        breaker.acquire_permission(
            now=10.0
        )
        is True
    )

    breaker.record_failure(
        now=10.0
    )

    assert (
        breaker.snapshot().state
        == CircuitState.CLOSED
    )

    breaker.record_failure(
        now=10.1
    )

    assert (
        breaker.snapshot().state
        == CircuitState.OPEN
    )

    assert (
        breaker.acquire_permission(
            now=10.5
        )
        is False
    )

    assert (
        breaker.acquire_permission(
            now=11.2
        )
        is True
    )

    assert (
        breaker.snapshot().state
        == CircuitState.HALF_OPEN
    )

    breaker.record_success()

    assert (
        breaker.snapshot().state
        == CircuitState.CLOSED
    )


# ============================================================
# MCP
# ============================================================

def test_mcp_manifest_matches_public_registries():
    manifest = (
        obter_manifesto_mcp()
    )

    assert (
        manifest["schema_version"]
        == "1.0.0"
    )

    summary = (
        manifest[
            "registry_summary"
        ]
    )

    assert (
        summary[
            "tool_registry_count"
        ]
        == 6
    )

    assert (
        summary[
            "mcp_exposed_tool_count"
        ]
        == 4
    )

    assert (
        summary[
            "internal_only_tool_count"
        ]
        == 2
    )

    exposed = {
        item["name"]
        for item
        in manifest["tools"]
    }

    assert exposed == {
        "buscar_conhecimento_rag",
        "calcular_diagnostico_financeiro",
        "preparar_email_financeiro",
        "preparar_mensagem_telegram",
    }
