"""Servidor MCP governado da INNA.

Fluxo:
MCP -> ToolCall -> ToolPermissionPolicy -> ToolExecutor -> ferramenta.

As regras de RAG e diagnóstico financeiro não são duplicadas.
"""

from __future__ import annotations

from time import perf_counter
from typing import Any
from uuid import uuid4

from mcp.server import MCPServer

from inna_ai.tools.catalog import criar_registro_ferramentas_inna
from inna_ai.tools.core.contracts import ToolCall, ToolExecutionContext
from inna_ai.tools.runtime import executar_ferramenta_inna
from inna_ai.agents.registry.agent_catalog import criar_registro_agentes_inna
from inna_ai.integrations.mcp.audit import hash_arguments, registrar_evento_mcp
from inna_ai.integrations.mcp.manifest import MCP_MANIFEST_SCHEMA_VERSION, MCP_MANIFEST_URI, build_mcp_manifest
from inna_ai.integrations.mcp.security import MCPAuthenticationError, validar_autenticacao_interna

SERVER_NAME = "inna-mcp-level-2"
SERVER_VERSION = "0.3.0"

_MCP_TOOL_PRINCIPAL_BINDING = {
    "buscar_conhecimento_rag": "rag_agent",
    "calcular_diagnostico_financeiro": "financial_agent",
    "preparar_email_financeiro": "communication_agent",
    "preparar_mensagem_telegram": "communication_agent",
}

_AGENT_REGISTRY = criar_registro_agentes_inna()
_TOOL_REGISTRY = criar_registro_ferramentas_inna()


class MCPToolExecutionError(RuntimeError):
    """Erro seguro retornado pela camada MCP."""


def _novo_trace_id() -> str:
    return f"mcp-{uuid4().hex}"


def _resolve_mcp_principal(
    tool_name: str,
) -> str:
    """
    Resolve a identidade operacional do MCP.

    O binding escolhe uma identidade determinística.
    Agent Registry e Tool Registry continuam sendo
    as fontes de autorização.
    """
    principal = (
        _MCP_TOOL_PRINCIPAL_BINDING.get(
            tool_name
        )
    )

    if principal is None:
        raise MCPToolExecutionError(
            "Ferramenta MCP não autorizada: "
            f"{tool_name}"
        )

    if not _TOOL_REGISTRY.contains(tool_name):
        raise MCPToolExecutionError(
            "Ferramenta MCP não registrada no "
            "Tool Registry: "
            f"{tool_name}"
        )

    if not _AGENT_REGISTRY.contains(principal):
        raise MCPToolExecutionError(
            "Principal MCP não registrado no "
            "Agent Registry: "
            f"{principal}"
        )

    tool_definition = _TOOL_REGISTRY.get(
        tool_name
    )

    agent_definition = _AGENT_REGISTRY.get(
        principal
    )

    if agent_definition.status != "active":
        raise MCPToolExecutionError(
            "Principal MCP inativo: "
            f"{principal}"
        )

    if (
        tool_name
        not in agent_definition.allowed_tools
    ):
        raise MCPToolExecutionError(
            "Agent Registry não autoriza "
            f"{principal} para {tool_name}"
        )

    if (
        principal
        not in tool_definition.allowed_agents
        and "*"
        not in tool_definition.allowed_agents
    ):
        raise MCPToolExecutionError(
            "Tool Registry não autoriza "
            f"{principal} para {tool_name}"
        )

    return principal


def _validate_mcp_registry_contract() -> None:
    """
    Valida todos os bindings MCP no startup.

    Falha cedo quando MCP, Agent Registry e
    Tool Registry estiverem inconsistentes.
    """
    for tool_name in sorted(
        _MCP_TOOL_PRINCIPAL_BINDING
    ):
        _resolve_mcp_principal(tool_name)


def _autenticar_operacao_mcp(
    *,
    target_name: str,
    event_type: str,
    arguments: dict[str, Any],
    trace_id: str,
) -> None:
    """Autentica e audita recusas sem persistir dados brutos."""
    started_at = perf_counter()

    try:
        validar_autenticacao_interna()
    except MCPAuthenticationError:
        duration_ms = (
            perf_counter() - started_at
        ) * 1000

        registrar_evento_mcp(
            call_id=f"{trace_id}-auth",
            trace_id=trace_id,
            tool_name=target_name,
            status="denied",
            duration_ms=duration_ms,
            arguments_hash=hash_arguments(
                arguments
            ),
            error_code=(
                "mcp_authentication_failed"
            ),
            principal=None,
            event_type=event_type,
            server_name=SERVER_NAME,
            server_version=SERVER_VERSION,
        )

        raise


def _executar_tool_governada(
    *,
    tool_name: str,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    """Executa ferramenta pelo runtime oficial da INNA."""

    trace_id = _novo_trace_id()

    _autenticar_operacao_mcp(
        target_name=tool_name,
        event_type="tool_call",
        arguments=arguments,
        trace_id=trace_id,
    )

    requested_by = _resolve_mcp_principal(
        tool_name
    )

    context = ToolExecutionContext(
        requested_by=requested_by,
        trace_id=trace_id,
        metadata={
            "source": "mcp",
            "server": SERVER_NAME,
            "server_version": SERVER_VERSION,
            "tool_name": tool_name,
            "transport_scope": "internal",
        },
    )

    call = ToolCall(
        tool_name=tool_name,
        arguments=arguments,
        context=context,
    )

    result = executar_ferramenta_inna(
        call,
    )

    arguments_hash = hash_arguments(arguments)

    if result.output is not None:
        registrar_evento_mcp(
            call_id=result.call_id,
            trace_id=trace_id,
            tool_name=result.tool_name,
            status="success",
            duration_ms=result.duration_ms,
            arguments_hash=arguments_hash,
            principal=requested_by,
            event_type="tool_call",
            server_name=SERVER_NAME,
            server_version=SERVER_VERSION,
        )

        return {
            **result.output,
            "_mcp": {
                "call_id": result.call_id,
                "trace_id": trace_id,
                "tool_name": result.tool_name,
                "status": str(
                    getattr(
                        result.status,
                        "value",
                        result.status,
                    )
                ),
                "duration_ms": result.duration_ms,
                "server": SERVER_NAME,
                "server_version": SERVER_VERSION,
            },
        }

    error_code = "tool_execution_failed"
    error_message = "A ferramenta não pôde ser executada."

    if result.error is not None:
        error_code = getattr(
            result.error,
            "code",
            error_code,
        )

        safe_message = getattr(
            result.error,
            "message",
            None,
        )

        if safe_message:
            error_message = safe_message

    registrar_evento_mcp(
        call_id=result.call_id,
        trace_id=trace_id,
        tool_name=result.tool_name,
        status="error",
        duration_ms=result.duration_ms,
        arguments_hash=arguments_hash,
        error_code=error_code,
        principal=requested_by,
        event_type="tool_call",
        server_name=SERVER_NAME,
        server_version=SERVER_VERSION,
    )

    raise MCPToolExecutionError(f"{error_code}: {error_message}")


def buscar_conhecimento_rag(
    pergunta: str,
    idioma: str = "pt",
    top_k: int = 4,
) -> dict[str, Any]:
    """Busca conhecimento na base RAG híbrida da INNA."""

    return _executar_tool_governada(
        tool_name="buscar_conhecimento_rag",
        arguments={
            "pergunta": pergunta,
            "idioma": idioma,
            "top_k": top_k,
        },
    )


def calcular_diagnostico_financeiro(
    renda_mensal: float,
    gastos_fixos: float,
    gastos_variaveis: float,
    dividas_mensais: float = 0,
    reserva_atual: float = 0,
    gastos_incluem_dividas: bool = False,
    moeda: str = "BRL",
    idioma: str = "pt",
) -> dict[str, Any]:
    """Calcula diagnóstico pelo motor financeiro oficial."""

    return _executar_tool_governada(
        tool_name="calcular_diagnostico_financeiro",
        arguments={
            "renda_mensal": renda_mensal,
            "gastos_fixos": gastos_fixos,
            "gastos_variaveis": gastos_variaveis,
            "dividas_mensais": dividas_mensais,
            "reserva_atual": reserva_atual,
            "gastos_incluem_dividas": (gastos_incluem_dividas),
            "moeda": moeda,
            "idioma": idioma,
        },
    )


def preparar_email_financeiro(
    destinatario: str,
    assunto: str,
    corpo: str,
    html_corpo: str | None = None,
    idioma: str = "pt",
) -> dict[str, Any]:
    """
    Prepara um e-mail para aprovação humana.

    Esta ferramenta não envia o e-mail.
    """
    return _executar_tool_governada(
        tool_name="preparar_email_financeiro",
        arguments={
            "destinatario": destinatario,
            "assunto": assunto,
            "corpo": corpo,
            "html_corpo": html_corpo,
            "idioma": idioma,
        },
    )


def preparar_mensagem_telegram(
    chat_id: str,
    mensagem: str,
    idioma: str = "pt",
) -> dict[str, Any]:
    """
    Prepara uma mensagem Telegram para aprovação humana.

    Esta ferramenta não envia a mensagem.
    """
    return _executar_tool_governada(
        tool_name="preparar_mensagem_telegram",
        arguments={
            "chat_id": chat_id,
            "mensagem": mensagem,
            "idioma": idioma,
        },
    )


def obter_manifesto_mcp() -> dict[str, Any]:
    """Retorna o manifesto governado do MCP."""
    _validate_mcp_registry_contract()

    return build_mcp_manifest(
        server_name=SERVER_NAME,
        server_version=SERVER_VERSION,
        principal_binding=(
            _MCP_TOOL_PRINCIPAL_BINDING
        ),
        agent_registry=_AGENT_REGISTRY,
        tool_registry=_TOOL_REGISTRY,
    )


def _obter_manifesto_mcp_resource() -> dict[str, Any]:
    """Lê o manifesto somente após autenticação MCP."""
    trace_id = _novo_trace_id()

    _autenticar_operacao_mcp(
        target_name=MCP_MANIFEST_URI,
        event_type="resource_read",
        arguments={},
        trace_id=trace_id,
    )

    started_at = perf_counter()

    try:
        manifest = obter_manifesto_mcp()
    except Exception:
        duration_ms = (
            perf_counter() - started_at
        ) * 1000

        registrar_evento_mcp(
            call_id=f"{trace_id}-resource",
            trace_id=trace_id,
            tool_name=MCP_MANIFEST_URI,
            status="error",
            duration_ms=duration_ms,
            arguments_hash=hash_arguments({}),
            error_code="mcp_resource_read_failed",
            principal=None,
            event_type="resource_read",
            server_name=SERVER_NAME,
            server_version=SERVER_VERSION,
        )

        raise

    duration_ms = (
        perf_counter() - started_at
    ) * 1000

    registrar_evento_mcp(
        call_id=f"{trace_id}-resource",
        trace_id=trace_id,
        tool_name=MCP_MANIFEST_URI,
        status="success",
        duration_ms=duration_ms,
        arguments_hash=hash_arguments({}),
        principal=None,
        event_type="resource_read",
        server_name=SERVER_NAME,
        server_version=SERVER_VERSION,
    )

    return manifest


def criar_servidor_mcp_inna() -> MCPServer:
    """Cria servidor MCP governado da INNA."""

    _validate_mcp_registry_contract()

    mcp_server = MCPServer(
        name=SERVER_NAME,
        title="INNA Governed MCP Server",
        description=(
            "Servidor MCP interno com validação, permissões, "
            "rastreamento e execução pelo runtime oficial."
        ),
        instructions=(
            "Utilize somente ferramentas registradas e autorizadas. "
            "Identidade, permissões e contexto são definidos no servidor."
        ),
        version=SERVER_VERSION,
        warn_on_duplicate_tools=True,
        log_level="INFO",
    )

    mcp_server.resource(
        MCP_MANIFEST_URI,
        name="inna_mcp_manifest",
        title="INNA MCP Manifest",
        description=(
            "Manifesto governado das ferramentas "
            "expostas pelo servidor MCP da INNA."
        ),
        mime_type="application/json",
        meta={
            "schema_version": (
                MCP_MANIFEST_SCHEMA_VERSION
            ),
            "transport_scope": "internal",
        },
    )(_obter_manifesto_mcp_resource)

    mcp_server.add_tool(
        buscar_conhecimento_rag,
        name="buscar_conhecimento_rag",
        title="Buscar conhecimento RAG",
        description=(
            "Consulta a base RAG híbrida da INNA utilizando "
            "permissões e execução governada."
        ),
        structured_output=True,
    )

    mcp_server.add_tool(
        calcular_diagnostico_financeiro,
        name="calcular_diagnostico_financeiro",
        title="Calcular diagnóstico financeiro",
        description=(
            "Executa o motor financeiro determinístico da INNA "
            "por meio do runtime governado."
        ),
        structured_output=True,
    )

    mcp_server.add_tool(
        preparar_email_financeiro,
        name="preparar_email_financeiro",
        title="Preparar e-mail financeiro",
        description=(
            "Prepara e valida um e-mail financeiro para aprovação humana. Não envia."
        ),
        structured_output=True,
    )

    mcp_server.add_tool(
        preparar_mensagem_telegram,
        name="preparar_mensagem_telegram",
        title="Preparar mensagem Telegram",
        description=(
            "Prepara e valida uma mensagem Telegram para aprovação humana. Não envia."
        ),
        structured_output=True,
    )

    return mcp_server


server = criar_servidor_mcp_inna()


def main() -> None:
    server.run(
        transport="stdio",
    )


if __name__ == "__main__":
    main()
