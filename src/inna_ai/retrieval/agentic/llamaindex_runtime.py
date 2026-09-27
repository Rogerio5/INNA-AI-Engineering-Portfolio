"""LlamaIndex Agentic RAG runtime adapter for INNA."""

from __future__ import annotations

import json
import os
import time
from collections.abc import Mapping
from typing import Any

from llama_index.core.agent.workflow import AgentWorkflow, FunctionAgent
from llama_index.core.tools import FunctionTool
from llama_index.llms.google_genai import GoogleGenAI

from inna_ai.tools import rag_tools

FEATURE_FLAG = "INNA_LLAMAINDEX_AGENTIC_RAG_ENABLED"
TOOL_NAME = "consultar_rag_inna"
ROUTER_AGENT_NAME = "INNARouterAgent"
RESEARCH_AGENT_NAME = "INNAKnowledgeResearchAgent"


def llamaindex_agentic_rag_enabled() -> bool:
    """Return whether the LlamaIndex Agentic RAG gateway is enabled."""
    raw_value = os.getenv(FEATURE_FLAG, "false")
    return raw_value.strip().lower() in {"1", "true", "yes", "on"}


def _serialize_tool_result(result: Any) -> str:
    """Serialize the existing INNA formal RAG result safely."""
    if isinstance(result, str):
        return result

    if hasattr(result, "model_dump"):
        result = result.model_dump()

    if isinstance(result, Mapping):
        return json.dumps(
            dict(result),
            ensure_ascii=False,
            default=str,
        )

    if isinstance(result, (list, tuple)):
        return json.dumps(
            list(result),
            ensure_ascii=False,
            default=str,
        )

    return str(result)


def consultar_conhecimento_inna(pergunta: str) -> str:
    """Call the existing INNA Formal RAG Tool."""
    result = rag_tools.consultar_rag_inna(pergunta)
    return _serialize_tool_result(result)


def criar_llamaindex_rag_tool() -> FunctionTool:
    """Expose INNA Formal RAG as a LlamaIndex FunctionTool."""
    return FunctionTool.from_defaults(
        fn=consultar_conhecimento_inna,
        name=TOOL_NAME,
        description=(
            "Consulta a base de conhecimento financeira da INNA usando "
            "o Formal RAG Tool existente, incluindo o pipeline RAG e "
            "GraphRAG quando aplicavel."
        ),
    )


def _create_default_llm() -> GoogleGenAI:
    """
    Build the default Gemini LLM without exposing credentials.

    SABINO_AI_LLAMAINDEX_GEMINI_IPV4_V1

    O LlamaIndex recebe HttpOptions com transporte HTTPX
    explicitamente ligado ao IPv4. Isso evita tentativas
    lentas de conexão IPv6 em ambientes sem rota IPv6
    operacional.
    """
    import httpx

    api_key = os.getenv(
        "GEMINI_API_KEY",
        "",
    ).strip()

    model = (
        os.getenv(
            "INNA_RAG_MODEL",
            "",
        ).strip()
        or os.getenv(
            "GEMINI_MODEL",
            "",
        ).strip()
    )

    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY nao configurada."
        )

    if not model:
        raise RuntimeError(
            "INNA_RAG_MODEL ou GEMINI_MODEL "
            "nao configurado."
        )


    raw_timeout = os.getenv(
        "INNA_LLAMAINDEX_GEMINI_TIMEOUT_MS",
        "10000",
    ).strip()

    try:
        timeout_ms = int(raw_timeout)
    except (TypeError, ValueError):
        timeout_ms = 10000

    timeout_ms = max(
        1000,
        min(
            timeout_ms,
            60000,
        ),
    )


    transport = httpx.HTTPTransport(
        local_address="0.0.0.0",
        retries=0,
    )


    # GoogleGenAI aceita dict aqui.
    # O próprio adapter acrescenta o header
    # x-goog-api-client do LlamaIndex e depois
    # constrói types.HttpOptions(**http_opts).
    http_options = {
        "timeout": timeout_ms,
        "retry_options": None,
        "client_args": {
            "transport": transport,
        },
    }


    # SABINO_AI_LLAMAINDEX_STATIC_MODEL_LIMITS_V1
    #
    # Gemini 3.5 Flash Lite:
    # input_token_limit  = 1_048_576
    # output_token_limit =    65_536
    #
    # O próprio GoogleGenAI/LlamaIndex calculava:
    # context_window = input + output
    #                = 1_114_112
    #
    # Ao fornecer max_tokens e context_window,
    # evitamos client.models.get(model=...) em
    # cada request sem reutilizar cliente async
    # entre event loops diferentes.

    known_model_limits = {
        "gemini-3.5-flash-lite": {
            "context_window": 1_114_112,
            "max_tokens": 65_536,
        },
    }

    model_limits = known_model_limits.get(
        model.lower()
    )

    llm_kwargs = {
        "model": model,
        "api_key": api_key,
        "temperature": 0.0,
        "http_options": http_options,
    }

    if model_limits is not None:
        llm_kwargs.update(
            context_window=model_limits[
                "context_window"
            ],
            max_tokens=model_limits[
                "max_tokens"
            ],
        )

    llm = GoogleGenAI(
        **llm_kwargs
    )


    try:
        setattr(
            llm,
            "_inna_transport_mode",
            "client_args_ipv4",
        )

        setattr(
            llm,
            "_inna_timeout_ms",
            timeout_ms,
        )

    except Exception:
        pass


    return llm


def criar_llamaindex_rag_agent(
    *,
    llm: Any | None = None,
) -> FunctionAgent:
    """Create the INNA knowledge Research Agent in LlamaIndex."""
    selected_llm = llm if llm is not None else _create_default_llm()
    tool = criar_llamaindex_rag_tool()

    return FunctionAgent(
        name=RESEARCH_AGENT_NAME,
        description=(
            "Agente LlamaIndex especializado em pesquisa fundamentada "
            "na base de conhecimento da INNA."
        ),
        system_prompt=(
            "Voce e o Research Agent de conhecimento da INNA. "
            "Para perguntas financeiras educacionais, use a ferramenta "
            "consultar_rag_inna. Baseie a resposta nas evidencias "
            "recuperadas e nao invente fatos ausentes."
        ),
        tools=[tool],
        llm=selected_llm,
        initial_tool_choice=TOOL_NAME,
        allow_parallel_tool_calls=False,
        can_handoff_to=[],
        streaming=False,
    )



def criar_llamaindex_router_agent(
    *,
    llm: Any | None = None,
) -> FunctionAgent:
    """Create the LlamaIndex routing agent for INNA."""
    selected_llm = llm if llm is not None else _create_default_llm()

    return FunctionAgent(
        name=ROUTER_AGENT_NAME,
        description=(
            "Agente roteador que direciona perguntas de conhecimento "
            "financeiro para o Research Agent da INNA."
        ),
        system_prompt=(
            "Voce e o Router Agent da INNA. Analise a solicitacao. "
            "Quando a pergunta exigir conhecimento financeiro educativo "
            "ou consulta documental, faca handoff para "
            "INNAKnowledgeResearchAgent. Nao invente resposta factual "
            "quando a pesquisa for necessaria."
        ),
        tools=[],
        llm=selected_llm,
        can_handoff_to=[RESEARCH_AGENT_NAME],
        allow_parallel_tool_calls=False,
        streaming=False,
    )


def criar_llamaindex_agent_workflow(
    *,
    llm: Any | None = None,
) -> AgentWorkflow:
    """Create Router -> Research multi-agent workflow."""
    selected_llm = llm if llm is not None else _create_default_llm()

    router_agent = criar_llamaindex_router_agent(
        llm=selected_llm,
    )
    research_agent = criar_llamaindex_rag_agent(
        llm=selected_llm,
    )

    return AgentWorkflow(
        agents=[
            router_agent,
            research_agent,
        ],
        root_agent=router_agent.name,
        timeout=120.0,
    )

# SABINO_AI_DIRECT_RAG_FAST_PATH_V1

def _inna_direct_rag_fast_path_enabled() -> bool:
    """
    Habilita fast path determinístico para consultas
    especializadas que já possuem ferramenta RAG definida.
    """
    return (
        os.getenv(
            "INNA_LLAMAINDEX_DIRECT_RAG_FAST_PATH",
            "false",
        )
        .strip()
        .lower()
        in {
            "1",
            "true",
            "yes",
            "on",
        }
    )


def _execute_direct_formal_rag_fast_path(
    pergunta: str,
    *,
    idioma: str,
    top_k: int,
) -> dict[str, Any]:
    """
    Executa o Formal RAG diretamente quando não há decisão
    real de roteamento a ser tomada pelo AgentWorkflow.

    O AgentWorkflow original permanece disponível quando
    a feature flag está desabilitada.
    """

    runtime_started = time.perf_counter()

    formal_rag_started = time.perf_counter()

    formal_result = rag_tools.consultar_rag_inna(
        pergunta,
        idioma=idioma,
        top_k=top_k,
    )

    formal_rag_finished = time.perf_counter()

    formal_rag_ms = round(
        (
            formal_rag_finished
            - formal_rag_started
        )
        * 1000,
        2,
    )


    # --------------------------------------------------------
    # Preserva exatamente a normalização usada pelo workflow.
    # --------------------------------------------------------

    serialized = _serialize_tool_result(
        formal_result
    )

    normalized = formal_result

    if hasattr(
        normalized,
        "model_dump",
    ):
        normalized = normalized.model_dump()


    formal_payload = None

    if isinstance(
        normalized,
        Mapping,
    ):
        formal_payload = dict(
            normalized
        )

    else:

        try:
            parsed = json.loads(
                serialized
            )

        except (
            TypeError,
            ValueError,
            json.JSONDecodeError,
        ):
            parsed = None

        if isinstance(
            parsed,
            dict,
        ):
            formal_payload = parsed


    if not isinstance(
        formal_payload,
        dict,
    ):
        raise RuntimeError(
            "Fast Path Formal RAG não retornou "
            "payload válido."
        )


    # --------------------------------------------------------
    # Mesmo payload final do caminho AgentWorkflow.
    # --------------------------------------------------------

    payload_build_started = (
        time.perf_counter()
    )

    raw_result = formal_payload.get(
        "raw_result"
    )


    if isinstance(
        raw_result,
        Mapping,
    ):

        payload = dict(
            raw_result
        )

    else:

        payload = dict(
            formal_payload
        )

        if (
            "fontes" not in payload
            and "sources" in formal_payload
        ):

            payload["fontes"] = list(
                formal_payload.get(
                    "sources"
                )
                or []
            )


        if (
            "modo" not in payload
            and "mode" in formal_payload
        ):

            payload["modo"] = str(
                formal_payload.get(
                    "mode"
                )
                or "rag"
            )


    formal_response = payload.get(
        "resposta"
    )

    if formal_response is None:
        formal_response = (
            formal_payload.get(
                "answer"
            )
        )

    if formal_response is None:
        formal_response = serialized


    payload["resposta"] = str(
        formal_response
    )


    payload_build_ms = round(
        (
            time.perf_counter()
            - payload_build_started
        )
        * 1000,
        2,
    )


    total_runtime_ms = round(
        (
            time.perf_counter()
            - runtime_started
        )
        * 1000,
        2,
    )


    # --------------------------------------------------------
    # Telemetria transparente.
    #
    # executed=True preserva compatibilidade indicando que
    # o runtime LlamaIndex/RAG foi executado.
    #
    # workflow_executed=False deixa explícito que o
    # AgentWorkflow não foi necessário nesta consulta.
    # --------------------------------------------------------

    payload[
        "llamaindex_agentic_rag"
    ] = {
        "enabled": True,
        "executed": True,
        "fallback_used": False,

        "runtime": (
            "direct_formal_rag_fast_path"
        ),

        "router_agent": (
            ROUTER_AGENT_NAME
        ),

        "research_agent": (
            RESEARCH_AGENT_NAME
        ),

        "entry_agent": (
            RESEARCH_AGENT_NAME
        ),

        "router_executed": False,

        "workflow_executed": False,

        "deterministic_fast_path": True,

        "routing_strategy": (
            "specialized_rag_direct_research"
        ),

        "return_direct": True,

        "response_strategy": (
            "formal_rag_return_direct"
        ),

        "timings": {
            "llm_setup_ms": 0.0,
            "tool_setup_ms": 0.0,
            "research_agent_setup_ms": 0.0,
            "router_agent_setup_ms": 0.0,
            "workflow_setup_ms": 0.0,
            "pre_workflow_setup_ms": 0.0,

            "pre_formal_rag_ms": 0.0,

            "formal_rag_ms": (
                formal_rag_ms
            ),

            "post_formal_rag_ms": (
                payload_build_ms
            ),

            "workflow_total_ms": (
                total_runtime_ms
            ),

            # Campo antigo mantido por compatibilidade.
            "orchestration_llm_ms": 0.0,

            # Nome semanticamente correto.
            "workflow_non_formal_ms": (
                payload_build_ms
            ),

            "payload_build_ms": (
                payload_build_ms
            ),

            "total_llamaindex_runtime_ms": (
                total_runtime_ms
            ),
        },
    }


    return payload


async def executar_llamaindex_agent_workflow_payload(
    pergunta: str,
    *,
    idioma: str = "pt",
    top_k: int = 2,
    llm: Any | None = None,
) -> dict[str, Any]:
    """Execute AgentWorkflow and preserve the Formal RAG payload."""
    if not llamaindex_agentic_rag_enabled():
        raise RuntimeError(
            "LlamaIndex Agentic RAG esta desabilitado por feature flag."
        )

    if _inna_direct_rag_fast_path_enabled():
        import asyncio

        return await asyncio.to_thread(
            _execute_direct_formal_rag_fast_path,
            pergunta,
            idioma=idioma,
            top_k=top_k,
        )

    runtime_total_started = time.perf_counter()

    llm_setup_started = time.perf_counter()
    selected_llm = llm if llm is not None else _create_default_llm()
    llm_setup_ms = round(
        (time.perf_counter() - llm_setup_started) * 1000,
        2,
    )

    capture: dict[str, Any] = {}

    def _capturing_tool(pergunta: str) -> str:
        formal_rag_started = time.perf_counter()

        capture["pre_formal_rag_ms"] = round(
            (
                formal_rag_started
                - workflow_started
            )
            * 1000,
            2,
        )

        formal_result = rag_tools.consultar_rag_inna(
            pergunta,
            idioma=idioma,
            top_k=top_k,
        )

        formal_rag_finished = time.perf_counter()

        capture["formal_rag_finished_at"] = (
            formal_rag_finished
        )
        capture["formal_rag_ms"] = round(
            (
                formal_rag_finished
                - formal_rag_started
            )
            * 1000,
            2,
        )

        serialized = _serialize_tool_result(formal_result)

        normalized = formal_result
        if hasattr(normalized, "model_dump"):
            normalized = normalized.model_dump()

        if isinstance(normalized, Mapping):
            capture["formal_rag_result"] = dict(normalized)
        else:
            try:
                parsed = json.loads(serialized)
            except (TypeError, ValueError, json.JSONDecodeError):
                parsed = None

            if isinstance(parsed, dict):
                capture["formal_rag_result"] = parsed

        return serialized

    tool_setup_started = time.perf_counter()

    tool = FunctionTool.from_defaults(
        fn=_capturing_tool,
        name=TOOL_NAME,
        description=(
            "Consulta a base de conhecimento financeira da INNA usando "
            "o Formal RAG Tool existente, incluindo RAG e GraphRAG."
        ),
        return_direct=True,
    )

    tool_setup_ms = round(
        (time.perf_counter() - tool_setup_started) * 1000,
        2,
    )

    research_agent_setup_started = time.perf_counter()

    research_agent = FunctionAgent(
        name=RESEARCH_AGENT_NAME,
        description=(
            "Agente LlamaIndex especializado em pesquisa fundamentada "
            "na base de conhecimento da INNA."
        ),
        system_prompt=(
            "Voce e o Research Agent de conhecimento da INNA. "
            "Para perguntas financeiras educacionais, use a ferramenta "
            "consultar_rag_inna e baseie a resposta nas evidencias."
        ),
        tools=[tool],
        llm=selected_llm,
        initial_tool_choice=TOOL_NAME,
        can_handoff_to=[],
        allow_parallel_tool_calls=False,
        streaming=False,
    )

    research_agent_setup_ms = round(
        (
            time.perf_counter()
            - research_agent_setup_started
        )
        * 1000,
        2,
    )

    router_agent_setup_started = time.perf_counter()

    router_agent = criar_llamaindex_router_agent(
        llm=selected_llm,
    )

    router_agent_setup_ms = round(
        (
            time.perf_counter()
            - router_agent_setup_started
        )
        * 1000,
        2,
    )

    workflow_setup_started = time.perf_counter()

    workflow = AgentWorkflow(
        agents=[router_agent, research_agent],
        root_agent=research_agent.name,
        timeout=120.0,
    )

    workflow_setup_ms = round(
        (time.perf_counter() - workflow_setup_started) * 1000,
        2,
    )

    workflow_started = time.perf_counter()

    pre_workflow_setup_ms = round(
        (workflow_started - runtime_total_started) * 1000,
        2,
    )

    result = await workflow.run(user_msg=pergunta)

    workflow_finished = time.perf_counter()

    workflow_total_ms = round(
        (
            workflow_finished
            - workflow_started
        )
        * 1000,
        2,
    )

    formal_payload = capture.get("formal_rag_result")

    if not isinstance(formal_payload, dict):
        raise RuntimeError(
            "LlamaIndex AgentWorkflow nao retornou payload Formal RAG."
        )

    payload_build_started = time.perf_counter()

    raw_result = formal_payload.get("raw_result")

    if isinstance(raw_result, Mapping):
        payload = dict(raw_result)
    else:
        payload = dict(formal_payload)

        if "fontes" not in payload and "sources" in formal_payload:
            payload["fontes"] = list(
                formal_payload.get("sources") or []
            )

        if "modo" not in payload and "mode" in formal_payload:
            payload["modo"] = str(
                formal_payload.get("mode") or "rag"
            )

    formal_response = payload.get("resposta")

    if formal_response is None:
        formal_response = formal_payload.get("answer")

    if formal_response is None:
        formal_response = str(result)

    payload["resposta"] = str(formal_response)

    payload_build_ms = round(
        (time.perf_counter() - payload_build_started) * 1000,
        2,
    )

    formal_rag_ms = float(
        capture.get("formal_rag_ms") or 0.0
    )

    pre_formal_rag_ms = float(
        capture.get("pre_formal_rag_ms") or 0.0
    )

    formal_rag_finished_at = capture.get(
        "formal_rag_finished_at"
    )

    if isinstance(
        formal_rag_finished_at,
        (int, float),
    ):
        post_formal_rag_ms = round(
            max(
                0.0,
                (
                    workflow_finished
                    - float(formal_rag_finished_at)
                )
                * 1000,
            ),
            2,
        )
    else:
        post_formal_rag_ms = 0.0

    orchestration_llm_ms = round(
        max(0.0, workflow_total_ms - formal_rag_ms),
        2,
    )

    total_llamaindex_runtime_ms = round(
        (time.perf_counter() - runtime_total_started) * 1000,
        2,
    )

    payload["llamaindex_agentic_rag"] = {
        "enabled": True,
        "executed": True,
        "fallback_used": False,
        "runtime": "agent_workflow",
        "router_agent": ROUTER_AGENT_NAME,
        "research_agent": RESEARCH_AGENT_NAME,
        "entry_agent": RESEARCH_AGENT_NAME,
        "router_executed": False,
        "routing_strategy": "specialized_rag_direct_research",
        "return_direct": True,
        "response_strategy": "formal_rag_return_direct",
        "timings": {
            "llm_setup_ms": llm_setup_ms,
            "tool_setup_ms": tool_setup_ms,
            "research_agent_setup_ms": (
                research_agent_setup_ms
            ),
            "router_agent_setup_ms": (
                router_agent_setup_ms
            ),
            "workflow_setup_ms": workflow_setup_ms,
            "pre_workflow_setup_ms": (
                pre_workflow_setup_ms
            ),
            "pre_formal_rag_ms": pre_formal_rag_ms,
            "formal_rag_ms": formal_rag_ms,
            "post_formal_rag_ms": post_formal_rag_ms,
            "workflow_total_ms": workflow_total_ms,
            "orchestration_llm_ms": orchestration_llm_ms,
            "payload_build_ms": payload_build_ms,
            "total_llamaindex_runtime_ms": (
                total_llamaindex_runtime_ms
            ),
        },
    }
    return payload


async def executar_llamaindex_agent_workflow(
    pergunta: str,
    *,
    llm: Any | None = None,
) -> str:
    """Execute Router -> Research AgentWorkflow when enabled."""
    if not llamaindex_agentic_rag_enabled():
        raise RuntimeError(
            "LlamaIndex Agentic RAG esta desabilitado por feature flag."
        )

    workflow = criar_llamaindex_agent_workflow(llm=llm)
    result = await workflow.run(user_msg=pergunta)
    return str(result)
async def executar_llamaindex_agentic_rag(
    pergunta: str,
    *,
    llm: Any | None = None,
) -> str:
    """Execute the LlamaIndex gateway only when explicitly enabled."""
    if not llamaindex_agentic_rag_enabled():
        raise RuntimeError(
            "LlamaIndex Agentic RAG esta desabilitado por feature flag."
        )

    agent = criar_llamaindex_rag_agent(llm=llm)
    result = await agent.run(user_msg=pergunta)
    return str(result)
