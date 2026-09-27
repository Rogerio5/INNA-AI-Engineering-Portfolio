"""
Ferramentas do agente RAG da INNA.

Este módulo adapta o RAG híbrido já existente para o núcleo
LangGraph, sem criar uma segunda base vetorial.
"""

from __future__ import annotations

import time
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from inna_ai.tools.core import ToolDefinition, ToolExecutionContext


class RagToolResult(BaseModel):
    ok: bool

    question: str
    language: str

    answer: str = ""
    sources: list[str] = Field(
        default_factory=list
    )

    mode: str = "unknown"
    retrieved_documents: int = 0
    duration_ms: int = 0

    retrieval_context: list[str] = Field(
        default_factory=list
    )

    raw_result: dict[str, Any] = Field(
        default_factory=dict
    )

    error_type: str | None = None
    error_message: str | None = None


def _normalizar_fontes(
    fontes: Any,
) -> list[str]:
    """
    Converte diferentes formatos de fontes para list[str].
    """
    if fontes is None:
        return []

    if isinstance(fontes, str):
        return [fontes]

    if not isinstance(fontes, (list, tuple)):
        return [str(fontes)]

    normalizadas: list[str] = []

    for fonte in fontes:
        if isinstance(fonte, str):
            valor = fonte.strip()

        elif isinstance(fonte, dict):
            valor = str(
                fonte.get("titulo")
                or fonte.get("title")
                or fonte.get("source")
                or fonte.get("fonte")
                or fonte.get("arquivo")
                or fonte.get("url")
                or fonte
            ).strip()

        else:
            valor = str(fonte).strip()

        if valor and valor not in normalizadas:
            normalizadas.append(valor)

    return normalizadas


def _extrair_contexto_recuperado(
    resultado: dict,
) -> list[str]:
    """
    Extrai o contexto textual efetivamente usado pelo RAG.

    Prioriza contexto_usado. Se esse campo vier vazio em
    algum caminho especializado de answer_with_rag(), usa
    os documentos/contextos retornados como fallback seguro.
    """

    contexto = str(
        resultado.get(
            "contexto_usado",
            "",
        )
        or ""
    ).strip()

    if contexto:
        return [contexto]

    documentos = (
        resultado.get("documentos")
        or resultado.get("contextos")
        or []
    )

    if not isinstance(
        documentos,
        (list, tuple),
    ):
        return []

    contextos: list[str] = []

    for item in documentos:
        if isinstance(item, str):
            texto = item.strip()
        elif isinstance(item, dict):
            texto = str(
                item.get("chunk_text")
                or item.get("texto")
                or item.get("trecho")
                or ""
            ).strip()
        else:
            texto = ""

        if texto and texto not in contextos:
            contextos.append(texto)

    return contextos




def consultar_rag_inna(
    pergunta: str,
    *,
    idioma: str = "pt",
    top_k: int = 2,
) -> RagToolResult:
    """
    Executa o RAG híbrido existente da INNA.

    A função:
    - valida a pergunta;
    - executa answer_with_rag();
    - normaliza resposta, fontes e modo;
    - registra o log técnico do RAG;
    - nunca expõe stack trace ao usuário.
    """
    pergunta = str(pergunta or "").strip()
    idioma = str(idioma or "pt").strip().lower()

    try:
        top_k = max(
            1,
            min(int(top_k), 10),
        )
    except (TypeError, ValueError):
        top_k = 2

    if len(pergunta) < 3:
        return RagToolResult(
            ok=False,
            question=pergunta,
            language=idioma,
            error_type="ValidationError",
            error_message=(
                "A pergunta precisa possuir "
                "pelo menos 3 caracteres."
            ),
        )

    inicio = time.perf_counter()

    try:
        from inna_ai.retrieval.facade import answer_with_rag, save_rag_log

        resultado = answer_with_rag(
            pergunta=pergunta,
            idioma=idioma,
            top_k=top_k,
        )

        if not isinstance(resultado, dict):
            resultado = {
                "resposta": str(resultado),
            }

        duracao_ms = int(
            (time.perf_counter() - inicio)
            * 1000
        )

        resposta = str(
            resultado.get("resposta")
            or resultado.get("answer")
            or resultado.get("response")
            or ""
        ).strip()

        fontes = _normalizar_fontes(
            resultado.get("fontes")
            or resultado.get("sources")
        )
        contexto_recuperado = (
            _extrair_contexto_recuperado(
                resultado
            )
        )


        modo = str(
            resultado.get("modo")
            or resultado.get("mode")
            or "rag"
        )

        documentos = (
            resultado.get("documentos")
            or resultado.get("results")
            or resultado.get("contextos")
            or []
        )

        if isinstance(documentos, (list, tuple)):
            quantidade_documentos = len(
                documentos
            )

            if quantidade_documentos == 0:
                quantidade_documentos = len(
                    fontes
                )
        else:
            quantidade_documentos = len(
                fontes
            )

        try:
            save_rag_log(
                pergunta=pergunta,
                resultado=resultado,
                tempo_resposta_ms=duracao_ms,
            )
        except Exception:
            # A falha da telemetria não deve impedir
            # que o usuário receba a resposta.
            pass

        if not resposta:
            return RagToolResult(
                ok=False,
                question=pergunta,
                language=idioma,
                sources=fontes,
                mode=modo,
                retrieved_documents=(
                    quantidade_documentos
                ),
                duration_ms=duracao_ms,
                raw_result=resultado,
                error_type="EmptyRagAnswer",
                error_message=(
                    "O RAG não retornou uma "
                    "resposta utilizável."
                ),
            )

        return RagToolResult(
            ok=True,
            question=pergunta,
            language=idioma,
            answer=resposta,
            sources=fontes,
            mode=modo,
            retrieved_documents=(
                quantidade_documentos
            ),
            duration_ms=duracao_ms,
            retrieval_context=(
                contexto_recuperado
            ),
            raw_result=resultado,
        )

    except Exception as exc:
        duracao_ms = int(
            (time.perf_counter() - inicio)
            * 1000
        )

        return RagToolResult(
            ok=False,
            question=pergunta,
            language=idioma,
            duration_ms=duracao_ms,
            error_type=type(exc).__name__,
            error_message=str(exc)[:1000],
        )


RAG_TOOL_NAME = "buscar_conhecimento_rag"


class BuscarConhecimentoRagInput(BaseModel):
    """
    Entrada pública e validada da ferramenta RAG.
    """

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
    )

    pergunta: str = Field(
        min_length=3,
        max_length=4000,
        description=(
            "Pergunta financeira ou educacional "
            "que será consultada na base da INNA."
        ),
    )

    idioma: str = Field(
        default="pt",
        min_length=2,
        max_length=10,
        pattern=(
            r"^[A-Za-z]{2,3}"
            r"(?:-[A-Za-z]{2})?$"
        ),
        description=(
            "Idioma da consulta, como pt, en-US "
            "ou es."
        ),
    )

    top_k: int = Field(
        default=2,
        ge=1,
        le=10,
        description=(
            "Quantidade máxima de resultados "
            "recuperados."
        ),
    )


def _extract_retrieval_telemetry(
    raw_result: Any,
) -> dict[str, Any]:
    """
    Extrai somente o resumo seguro de retrieval.

    O raw_result completo permanece interno.
    """
    if not isinstance(
        raw_result,
        dict,
    ):
        return {}

    retrieval_trace = raw_result.get(
        "retrieval_trace",
        {},
    )

    if not isinstance(
        retrieval_trace,
        dict,
    ):
        return {}

    auto_merging = retrieval_trace.get(
        "auto_merging",
        {},
    )

    if not isinstance(
        auto_merging,
        dict,
    ):
        return {}

    try:
        merged_result_count = max(
            0,
            int(
                auto_merging.get(
                    "merged_result_count",
                    0,
                )
                or 0
            ),
        )
    except (
        TypeError,
        ValueError,
    ):
        merged_result_count = 0

    try:
        child_count = max(
            0,
            int(
                auto_merging.get(
                    "child_count",
                    0,
                )
                or 0
            ),
        )
    except (
        TypeError,
        ValueError,
    ):
        child_count = 0

    try:
        duration_ms = max(
            0.0,
            float(
                auto_merging.get(
                    "duration_ms",
                    0.0,
                )
                or 0.0
            ),
        )
    except (
        TypeError,
        ValueError,
    ):
        duration_ms = 0.0

    return {
        "observed": bool(
            auto_merging.get(
                "observed",
                False,
            )
        ),
        "applied": bool(
            auto_merging.get(
                "applied",
                False,
            )
        ),
        "merged_result_count": (
            merged_result_count
        ),
        "child_count": child_count,
        "duration_ms": duration_ms,
    }


class BuscarConhecimentoRagOutput(BaseModel):
    """
    Saída segura disponibilizada ao agente.

    O resultado bruto do banco e detalhes internos
    não são expostos no contrato formal.
    """

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    pergunta: str
    idioma: str

    resposta: str = Field(
        min_length=1,
    )

    fontes: list[str] = Field(
        default_factory=list,
    )

    modo: str = "rag"

    documentos_recuperados: int = Field(
        default=0,
        ge=0,
    )

    contexto_recuperado: list[str] = Field(
        default_factory=list,
    )

    duracao_rag_ms: int = Field(
        default=0,
        ge=0,
    )

    llm_usage: dict[str, int] = Field(
        default_factory=dict,
    )

    retrieval_telemetry: dict[str, Any] = Field(
        default_factory=dict,
    )


class RagFormalToolExecutionError(
    RuntimeError
):
    """
    Falha interna e controlada da ferramenta RAG.
    """


def executar_busca_conhecimento_rag(
    payload: BuscarConhecimentoRagInput,
    context: ToolExecutionContext,
) -> BuscarConhecimentoRagOutput:
    """
    Handler compatível com o ToolExecutor.

    A função reutiliza consultar_rag_inna(), que por
    sua vez reutiliza o RAG híbrido atual.
    """
    del context

    resultado = consultar_rag_inna(
        pergunta=payload.pergunta,
        idioma=payload.idioma.lower(),
        top_k=payload.top_k,
    )

    if not resultado.ok:
        raise RagFormalToolExecutionError(
            resultado.error_type
            or "rag_execution_failed"
        )

    resposta = str(
        resultado.answer or ""
    ).strip()

    raw_llm_usage = (
        resultado.raw_result.get(
            "llm_usage",
            {},
        )
        if isinstance(
            resultado.raw_result,
            dict,
        )
        else {}
    )

    llm_usage: dict[str, int] = {}

    if isinstance(
        raw_llm_usage,
        dict,
    ):
        for key in (
            "input_tokens",
            "output_tokens",
            "total_tokens",
        ):
            try:
                llm_usage[key] = max(
                    0,
                    int(
                        raw_llm_usage.get(
                            key,
                            0,
                        )
                        or 0
                    ),
                )
            except (
                TypeError,
                ValueError,
            ):
                llm_usage[key] = 0

        calculated_total = (
            llm_usage["input_tokens"]
            + llm_usage["output_tokens"]
        )

        if (
            llm_usage["total_tokens"]
            <= 0
        ):
            llm_usage[
                "total_tokens"
            ] = calculated_total

    retrieval_telemetry = (
        _extract_retrieval_telemetry(
            resultado.raw_result
        )
    )

    if not resposta:
        raise RagFormalToolExecutionError(
            "empty_rag_answer"
        )

    return BuscarConhecimentoRagOutput(
        pergunta=resultado.question,
        idioma=resultado.language,
        resposta=resposta,
        fontes=list(resultado.sources),
        modo=resultado.mode,
        documentos_recuperados=(
            resultado.retrieved_documents
        ),
        contexto_recuperado=list(
            resultado.retrieval_context
        ),
        duracao_rag_ms=(
            resultado.duration_ms
        ),
        llm_usage=llm_usage,
        retrieval_telemetry=(
            retrieval_telemetry
        ),
    )


def criar_definicao_buscar_conhecimento_rag(
    *,
    timeout_seconds: float = 20.0,
) -> ToolDefinition:
    """
    Cria a definição formal da ferramenta RAG.
    """
    return ToolDefinition(
        name=RAG_TOOL_NAME,
        description=(
            "Consulta a base de conhecimento "
            "financeiro da INNA usando busca "
            "híbrida, reranking e geração "
            "fundamentada nas fontes recuperadas."
        ),
        input_model=(
            BuscarConhecimentoRagInput
        ),
        output_model=(
            BuscarConhecimentoRagOutput
        ),
        handler=(
            executar_busca_conhecimento_rag
        ),
        allowed_agents=frozenset({
            "rag_agent",
            "education_agent",
            "research_agent",
        }),
        timeout_seconds=timeout_seconds,
        idempotent=True,
        sensitive_output=False,
        tags=frozenset({
            "rag",
            "knowledge",
            "financial_education",
            "read_only",
        }),
    )


__all__ = [
    "BuscarConhecimentoRagInput",
    "BuscarConhecimentoRagOutput",
    "RAG_TOOL_NAME",
    "RagFormalToolExecutionError",
    "RagToolResult",
    "consultar_rag_inna",
    "criar_definicao_buscar_conhecimento_rag",
    "executar_busca_conhecimento_rag",
]
