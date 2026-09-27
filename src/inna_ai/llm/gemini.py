"""
Serviço de geração textual Gemini da INNA Financial Coach AI.

Utiliza o SDK atual google-genai.

Responsabilidades:
- carregar a chave da API;
- criar o cliente Gemini;
- gerar respostas textuais;
- validar o retorno do modelo;
- centralizar configurações;
- evitar dependência direta do Gemini no dashboard.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

try:
    from inna_ai.observability.llm.tracking import executar_generate_content_observado
except ImportError:
    from inna_ai.observability.llm.tracking import executar_generate_content_observado


from inna_ai.resilience.tracing import get_shared_resilience_runtime, traced_resilience_operation
from inna_ai.resilience.deadline import DeadlineBudget
from inna_ai.resilience.policies import GEMINI_TEXT_GENERATION_POLICY
from inna_ai.llm.model_registry import DEFAULT_TEXT_MODEL, LLMRole, get_model_for_role

MODELO_TEXTO_PADRAO = DEFAULT_TEXT_MODEL

DEFAULT_TEXT_GENERATION_TIMEOUT_MS = 15000
DEFAULT_TEXT_GENERATION_TOTAL_DEADLINE_MS = 25000
TEXT_GENERATION_DEADLINE_RESERVE_SECONDS = 0.25


def _ler_inteiro_ambiente(
    name: str,
    default: int,
    *,
    minimum: int,
    maximum: int,
) -> int:
    carregar_variaveis_ambiente()

    raw_value = os.getenv(name)

    if raw_value is None:
        return default

    try:
        value = int(
            str(raw_value).strip()
        )
    except (
        TypeError,
        ValueError,
    ) as exc:
        raise GeminiTextConfigurationError(
            f"{name} possui valor inválido."
        ) from exc

    if (
        value < minimum
        or value > maximum
    ):
        raise GeminiTextConfigurationError(
            f"{name} deve estar entre "
            f"{minimum} e {maximum}."
        )

    return value


def _obter_timeout_geracao_ms() -> int:
    return _ler_inteiro_ambiente(
        "INNA_TEXT_GENERATION_TIMEOUT_MS",
        DEFAULT_TEXT_GENERATION_TIMEOUT_MS,
        minimum=1000,
        maximum=120000,
    )


def _obter_deadline_total_geracao_ms() -> int:
    return _ler_inteiro_ambiente(
        "INNA_TEXT_GENERATION_TOTAL_DEADLINE_MS",
        DEFAULT_TEXT_GENERATION_TOTAL_DEADLINE_MS,
        minimum=1000,
        maximum=180000,
    )


class GeminiTextConfigurationError(RuntimeError):
    """Erro de configuração do serviço Gemini."""


class GeminiTextGenerationError(RuntimeError):
    """Erro durante a geração da resposta Gemini."""


def carregar_variaveis_ambiente() -> None:
    """
    Carrega o arquivo .env local quando disponível.
    """
    try:
        from dotenv import load_dotenv
    except ImportError:
        return

    env_path = Path(".env")

    if env_path.exists():
        load_dotenv(
            dotenv_path=env_path,
            override=False,
        )


def obter_api_key_gemini() -> str:
    """
    Obtém a chave Gemini sem expor seu conteúdo.
    """
    carregar_variaveis_ambiente()

    api_key = (
        os.getenv("GEMINI_API_KEY")
        or os.getenv("GOOGLE_API_KEY")
    )

    if not api_key:
        raise GeminiTextConfigurationError(
            "GEMINI_API_KEY ou GOOGLE_API_KEY não encontrada."
        )

    return api_key.strip()



# SABINO_AI_GEMINI_TEXT_IPV4_SHARED_CLIENT

@lru_cache(maxsize=8)
def _criar_cliente_gemini_cached(
    resolved_timeout_ms: int,
):
    """
    Cria e reutiliza clientes Gemini por timeout.

    Objetivos:
    - reutilização de conexão HTTP;
    - transporte IPv4 explícito;
    - evitar cold-client repetido;
    - manter retry sob autoridade da INNA;
    - preservar timeout por perfil de cliente.
    """

    try:
        import httpx

        from google import genai
        from google.genai import types

    except ImportError as exc:
        raise GeminiTextConfigurationError(
            "Dependência Gemini/HTTPX indisponível "
            f"({type(exc).__name__})."
        ) from exc


    transport = httpx.HTTPTransport(
        local_address="0.0.0.0",
        retries=0,
    )


    http_options_fields = getattr(
        types.HttpOptions,
        "model_fields",
        {},
    )


    http_options_kwargs = {
        "timeout": resolved_timeout_ms,
        "retry_options": None,
    }


    transport_mode = None


    if "client_args" in http_options_fields:

        http_options_kwargs[
            "client_args"
        ] = {
            "transport": transport,
        }

        transport_mode = (
            "client_args_ipv4"
        )


    elif "httpx_client" in http_options_fields:

        http_options_kwargs[
            "httpx_client"
        ] = httpx.Client(
            transport=transport,
            follow_redirects=True,
            trust_env=True,
        )

        transport_mode = (
            "httpx_client_ipv4"
        )


    else:

        raise GeminiTextConfigurationError(
            "A versão instalada do google-genai "
            "não expõe client_args nem "
            "httpx_client em HttpOptions."
        )


    http_options = types.HttpOptions(
        **http_options_kwargs
    )


    client = genai.Client(
        api_key=obter_api_key_gemini(),
        http_options=http_options,
    )


    try:
        setattr(
            client,
            "_inna_transport_mode",
            transport_mode,
        )
    except Exception:
        pass


    return client


def criar_cliente_gemini(
    *,
    timeout_ms: int | None = None,
):
    """
    Retorna cliente Gemini compartilhado e IPv4.

    O cache é indexado pelo timeout para preservar
    a política de deadline existente da INNA.
    """

    resolved_timeout_ms = int(
        timeout_ms
        if timeout_ms is not None
        else _obter_timeout_geracao_ms()
    )


    if resolved_timeout_ms <= 0:

        raise GeminiTextConfigurationError(
            "Timeout Gemini deve ser positivo."
        )


    return _criar_cliente_gemini_cached(
        resolved_timeout_ms
    )


def _normalizar_prompt(prompt: Any) -> str:
    """
    Valida e normaliza o prompt antes do envio.
    """
    prompt_normalizado = str(prompt or "").strip()

    if not prompt_normalizado:
        raise ValueError(
            "Não é possível gerar resposta com prompt vazio."
        )

    return prompt_normalizado


def _extrair_texto_resposta(response: Any) -> str:
    """
    Extrai o texto do retorno do SDK.
    """
    texto = getattr(response, "text", None)

    if texto:
        return str(texto).strip()

    candidatos = getattr(response, "candidates", None) or []

    for candidato in candidatos:
        content = getattr(candidato, "content", None)
        parts = getattr(content, "parts", None) or []

        trechos = []

        for part in parts:
            texto_part = getattr(part, "text", None)

            if texto_part:
                trechos.append(str(texto_part))

        if trechos:
            return "\n".join(trechos).strip()

    return ""



def gerar_texto_gemini(
    prompt: Any,
    *,
    modelo: str | None = None,
    role: LLMRole | str = LLMRole.DEFAULT,
    temperatura: float = 0.3,
    max_tokens: int = 2048,
    usage_out: dict[str, int] | None = None,
    telemetry_out: dict | None = None,
) -> str:
    """
    Gera texto Gemini com resiliência controlada pela INNA.

    O serviço possui:
    - timeout HTTP por tentativa;
    - deadline total;
    - retry controlado;
    - circuit breaker dedicado;
    - observabilidade segura;
    - propagação opcional de usage/tokens.
    """
    if usage_out is not None:
        usage_out.clear()

    prompt_normalizado = _normalizar_prompt(
        prompt
    )

    temperatura = max(
        0.0,
        min(
            float(temperatura),
            2.0,
        ),
    )

    max_tokens = max(
        128,
        min(
            int(max_tokens),
            8192,
        ),
    )

    timeout_ms = (
        _obter_timeout_geracao_ms()
    )

    total_deadline_ms = (
        _obter_deadline_total_geracao_ms()
    )

    deadline_budget = DeadlineBudget(
        total_deadline_ms / 1000.0,
        reserve_seconds=(
            TEXT_GENERATION_DEADLINE_RESERVE_SECONDS
        ),
    )

    # SABINO_AI_NATIVE_GEMINI_AGENTOPS_V1
    import time as _inna_agentops_time

    generation_started = (
        _inna_agentops_time.perf_counter()
    )

    generation_attempts: list[dict] = []

    def _inna_write_generation_trace(
        *,
        success: bool,
        resolved_model=None,
        error=None,
    ) -> None:

        if telemetry_out is None:
            return

        service_ms = (
            _inna_agentops_time.perf_counter()
            - generation_started
        ) * 1000.0

        provider_ms = sum(
            float(
                item.get(
                    "provider_ms",
                    0.0,
                )
                or 0.0
            )
            for item in generation_attempts
        )

        attempts_total_ms = sum(
            float(
                item.get(
                    "attempt_total_ms",
                    0.0,
                )
                or 0.0
            )
            for item in generation_attempts
        )

        telemetry_out.clear()

        telemetry_out.update(
            {
                "executed": True,
                "success": bool(success),
                "provider": "gemini",
                "model": (
                    resolved_model
                    or str(
                        modelo or ""
                    ).strip()
                    or None
                ),
                "service_ms": round(
                    service_ms,
                    2,
                ),
                "provider_ms": round(
                    provider_ms,
                    2,
                ),
                "attempt_total_ms": round(
                    attempts_total_ms,
                    2,
                ),
                "attempts": len(
                    generation_attempts
                ),
                "retry_count": max(
                    0,
                    len(generation_attempts) - 1,
                ),
                "attempt_events": [
                    dict(item)
                    for item
                    in generation_attempts
                ],
                "error_type": (
                    type(error).__name__
                    if error is not None
                    else None
                ),
                "error_message": (
                    str(error)[:300]
                    if error is not None
                    else None
                ),
            }
        )

    try:
        from google.genai import types

        modelo_resolvido = (
            str(
                modelo
                or ""
            ).strip()
            or get_model_for_role(role)
        )

        # Gemini 3.x possui contrato de geração diferente.
        #
        # Não enviamos parâmetros de amostragem legados
        # (temperature/top_p/top_k) nem thinking_budget.
        # O modelo usa seu thinking_level padrão.
        #
        # Para Gemini 2.5 e anteriores preservamos o
        # contrato histórico da INNA.
        modelo_normalizado = (
            modelo_resolvido
            .strip()
            .lower()
        )

        if modelo_normalizado.startswith(
            "gemini-3"
        ):
            config = types.GenerateContentConfig(
                max_output_tokens=max_tokens,
            )
        else:
            config = types.GenerateContentConfig(
                temperature=temperatura,
                max_output_tokens=max_tokens,
                thinking_config=(
                    types.ThinkingConfig(
                        thinking_budget=0
                    )
                ),
            )

        resilience_runtime = (
            get_shared_resilience_runtime()
        )

        def generate_attempt():
            attempt_timeout_seconds = (
                deadline_budget.clamp_timeout(
                    timeout_ms / 1000.0
                )
            )

            attempt_timeout_ms = max(
                1,
                int(
                    attempt_timeout_seconds
                    * 1000
                ),
            )

            attempt_number = (
                len(generation_attempts) + 1
            )

            attempt_started = (
                _inna_agentops_time.perf_counter()
            )

            provider_started = None
            attempt_success = False
            attempt_error = None

            try:

                client = criar_cliente_gemini(
                    timeout_ms=attempt_timeout_ms
                )

                provider_started = (
                    _inna_agentops_time.perf_counter()
                )

                response_attempt = (
                    executar_generate_content_observado(
                        client,
                        modelo=modelo_resolvido,
                        contents=prompt_normalizado,
                        config=config,
                        operacao=(
                            "llm_service_generate"
                        ),
                        origem=(
                            "services.llm.gemini"
                        ),
                        metadados={
                            "temperatura": temperatura,
                            "max_output_tokens": (
                                max_tokens
                            ),
                            "thinking_budget": 0,
                        },
                    )
                )

                attempt_success = True

                return response_attempt

            except Exception as exc:

                attempt_error = exc
                raise

            finally:

                attempt_finished = (
                    _inna_agentops_time.perf_counter()
                )

                provider_ms = (
                    (
                        attempt_finished
                        - provider_started
                    )
                    * 1000.0
                    if provider_started
                    is not None
                    else 0.0
                )

                attempt_total_ms = (
                    attempt_finished
                    - attempt_started
                ) * 1000.0

                generation_attempts.append(
                    {
                        "attempt": attempt_number,
                        "success": (
                            attempt_success
                        ),
                        "attempt_timeout_ms": (
                            attempt_timeout_ms
                        ),
                        "provider_ms": round(
                            provider_ms,
                            2,
                        ),
                        "attempt_total_ms": round(
                            attempt_total_ms,
                            2,
                        ),
                        "error_type": (
                            type(
                                attempt_error
                            ).__name__
                            if attempt_error
                            is not None
                            else None
                        ),
                    }
                )

        with traced_resilience_operation(
            GEMINI_TEXT_GENERATION_POLICY
        ):
            response = (
                resilience_runtime.execute(
                    policy=(
                        GEMINI_TEXT_GENERATION_POLICY
                    ),
                    operation=generate_attempt,
                    deadline_budget=(
                        deadline_budget
                    ),
                    # SABINO_AI_GEMINI_MIN_RETRY_BUDGET_V1
                    minimum_retry_attempt_seconds=min(
                        10.0,
                        (
                            deadline_budget.total_seconds
                            - deadline_budget.reserve_seconds
                        ) / 2.0,
                    ),
                )
            )

        if usage_out is not None:
            try:
                from inna_ai.observability.llm.costs import extrair_tokens_resposta

                extracted_usage = (
                    extrair_tokens_resposta(
                        response
                    )
                )

                usage_out.update(
                    {
                        "tokens_entrada": int(
                            extracted_usage.get(
                                "tokens_entrada",
                                0,
                            )
                            or 0
                        ),
                        "tokens_saida": int(
                            extracted_usage.get(
                                "tokens_saida",
                                0,
                            )
                            or 0
                        ),
                        "tokens_totais": int(
                            extracted_usage.get(
                                "tokens_totais",
                                0,
                            )
                            or 0
                        ),
                    }
                )

            except Exception:
                # Telemetria de custo nunca pode
                # afetar a resposta funcional.
                usage_out.clear()

        resposta = _extrair_texto_resposta(
            response
        )

        # Resposta inválida não é falha transitória.
        if not resposta:
            raise GeminiTextGenerationError(
                "O Gemini não retornou "
                "uma resposta textual."
            )

        _inna_write_generation_trace(
            success=True,
            resolved_model=modelo_resolvido,
        )

        return resposta

    except (
        GeminiTextConfigurationError,
        GeminiTextGenerationError,
        ValueError,
    ) as exc:

        _inna_write_generation_trace(
            success=False,
            resolved_model=locals().get(
                "modelo_resolvido"
            ),
            error=exc,
        )

        raise

    except Exception as exc:

        _inna_write_generation_trace(
            success=False,
            resolved_model=locals().get(
                "modelo_resolvido"
            ),
            error=exc,
        )

        raise GeminiTextGenerationError(
            "Não foi possível gerar a "
            "resposta Gemini "
            f"({type(exc).__name__})."
        ) from exc




# SABINO_AI_NATIVE_GEMINI_STREAM_V1
def gerar_texto_gemini_stream(
    prompt: Any,
    *,
    modelo: str | None = None,
    role: LLMRole | str = LLMRole.DEFAULT,
    temperatura: float = 0.3,
    max_tokens: int = 2048,
    usage_out: dict[str, int] | None = None,
    telemetry_out: dict | None = None,
):
    """
    Gera texto Gemini em streaming.

    Regras de resiliência:
    - retry é permitido somente antes do primeiro chunk;
    - depois do primeiro chunk nenhum retry é executado;
    - reutiliza cliente Gemini IPv4 compartilhado;
    - preserva timeout/deadline da INNA;
    - não registra conteúdo bruto em telemetria.
    """

    import time as _inna_stream_time

    from inna_ai.observability.llm.tracking import executar_generate_content_stream_observado


    if usage_out is not None:
        usage_out.clear()

    if telemetry_out is not None:
        telemetry_out.clear()


    prompt_normalizado = _normalizar_prompt(
        prompt
    )


    temperatura = max(
        0.0,
        min(
            float(temperatura),
            2.0,
        ),
    )


    max_tokens = max(
        128,
        min(
            int(max_tokens),
            8192,
        ),
    )


    timeout_ms = (
        _obter_timeout_geracao_ms()
    )

    total_deadline_ms = (
        _obter_deadline_total_geracao_ms()
    )


    deadline_budget = DeadlineBudget(
        total_deadline_ms / 1000.0,
        reserve_seconds=(
            TEXT_GENERATION_DEADLINE_RESERVE_SECONDS
        ),
    )


    generation_started = (
        _inna_stream_time.perf_counter()
    )

    generation_attempts = []

    chunk_count = 0
    text_chunk_count = 0

    first_chunk_ms = None

    post_first_chunk_provider_ms = 0.0

    last_chunk = None

    resolved_model = None


    def _extract_stream_text(
        chunk,
    ) -> str:

        try:

            value = getattr(
                chunk,
                "text",
                None,
            )

            if value:

                return str(value)

        except Exception:
            pass


        try:

            value = (
                _extrair_texto_resposta(
                    chunk
                )
            )

            if value:

                return str(value)

        except Exception:
            pass


        return ""


    def _write_stream_trace(
        *,
        success: bool,
        error=None,
    ):

        if telemetry_out is None:
            return


        service_ms = (
            _inna_stream_time.perf_counter()
            - generation_started
        ) * 1000.0


        attempt_provider_ms = sum(
            float(
                event.get(
                    "provider_ms",
                    0.0,
                )
                or 0.0
            )
            for event
            in generation_attempts
        )


        provider_ms = (
            attempt_provider_ms
            + float(
                post_first_chunk_provider_ms
                or 0.0
            )
        )


        telemetry_out.clear()

        telemetry_out.update(
            {
                "executed": True,
                "success": bool(success),
                "streaming": True,
                "provider": "gemini",
                "model": resolved_model,

                "service_ms": round(
                    service_ms,
                    2,
                ),

                "provider_ms": round(
                    provider_ms,
                    2,
                ),

                "first_chunk_ms": (
                    round(
                        first_chunk_ms,
                        2,
                    )
                    if first_chunk_ms
                    is not None
                    else None
                ),

                "attempts": len(
                    generation_attempts
                ),

                "retry_count": max(
                    0,
                    len(
                        generation_attempts
                    )
                    - 1,
                ),

                "attempt_events": [
                    dict(event)
                    for event
                    in generation_attempts
                ],

                "chunk_count": int(
                    chunk_count
                ),

                "text_chunk_count": int(
                    text_chunk_count
                ),

                "retry_after_first_chunk": False,

                "error_type": (
                    type(error).__name__
                    if error is not None
                    else None
                ),

                "error_message": (
                    str(error)[:300]
                    if error is not None
                    else None
                ),
            }
        )


    try:

        from google.genai import types


        resolved_model = (
            str(
                modelo or ""
            ).strip()
            or get_model_for_role(
                role
            )
        )


        modelo_normalizado = (
            resolved_model
            .strip()
            .lower()
        )


        if modelo_normalizado.startswith(
            "gemini-3"
        ):

            config = (
                types.GenerateContentConfig(
                    max_output_tokens=(
                        max_tokens
                    ),
                )
            )

        else:

            config = (
                types.GenerateContentConfig(
                    temperature=(
                        temperatura
                    ),
                    max_output_tokens=(
                        max_tokens
                    ),
                    thinking_config=(
                        types.ThinkingConfig(
                            thinking_budget=0
                        )
                    ),
                )
            )


        resilience_runtime = (
            get_shared_resilience_runtime()
        )


        # ====================================================
        # ABRIR STREAM + OBTER PRIMEIRO CHUNK
        #
        # Esta operação fica dentro do ResilienceRuntime.
        # Portanto, falhas ANTES do primeiro chunk podem
        # receber retry.
        # ====================================================

        def start_stream_attempt():

            attempt_timeout_seconds = (
                deadline_budget.clamp_timeout(
                    timeout_ms / 1000.0
                )
            )


            attempt_timeout_ms = max(
                1,
                int(
                    attempt_timeout_seconds
                    * 1000
                ),
            )


            attempt_number = (
                len(
                    generation_attempts
                )
                + 1
            )


            attempt_started = (
                _inna_stream_time
                .perf_counter()
            )

            provider_started = None

            attempt_success = False

            attempt_error = None


            try:

                client = (
                    criar_cliente_gemini(
                        timeout_ms=(
                            attempt_timeout_ms
                        )
                    )
                )


                provider_started = (
                    _inna_stream_time
                    .perf_counter()
                )


                provider_stream = (
                    executar_generate_content_stream_observado(
                        client,
                        modelo=resolved_model,
                        contents=(
                            prompt_normalizado
                        ),
                        config=config,
                        operacao=(
                            "llm_service_generate_stream"
                        ),
                        origem=(
                            "services.llm.gemini"
                        ),
                        metadados={
                            "temperatura": (
                                temperatura
                            ),
                            "max_output_tokens": (
                                max_tokens
                            ),
                            "streaming": True,
                            "retry_scope": (
                                "before_first_chunk_only"
                            ),
                        },
                    )
                )


                iterator = iter(
                    provider_stream
                )


                try:

                    first_chunk = next(
                        iterator
                    )

                except StopIteration as exc:

                    raise (
                        GeminiTextGenerationError(
                            "O Gemini não retornou "
                            "chunks no streaming."
                        )
                    ) from exc


                attempt_success = True


                return (
                    first_chunk,
                    iterator,
                )


            except Exception as exc:

                attempt_error = exc
                raise


            finally:

                attempt_finished = (
                    _inna_stream_time
                    .perf_counter()
                )


                provider_ms = (
                    (
                        attempt_finished
                        - provider_started
                    )
                    * 1000.0
                    if provider_started
                    is not None
                    else 0.0
                )


                attempt_total_ms = (
                    attempt_finished
                    - attempt_started
                ) * 1000.0


                generation_attempts.append(
                    {
                        "attempt": (
                            attempt_number
                        ),

                        "success": (
                            attempt_success
                        ),

                        "attempt_timeout_ms": (
                            attempt_timeout_ms
                        ),

                        "provider_ms": round(
                            provider_ms,
                            2,
                        ),

                        "attempt_total_ms": round(
                            attempt_total_ms,
                            2,
                        ),

                        "error_type": (
                            type(
                                attempt_error
                            ).__name__
                            if attempt_error
                            is not None
                            else None
                        ),
                    }
                )


        with traced_resilience_operation(
            GEMINI_TEXT_GENERATION_POLICY
        ):

            first_chunk, iterator = (
                resilience_runtime.execute(
                    policy=(
                        GEMINI_TEXT_GENERATION_POLICY
                    ),

                    operation=(
                        start_stream_attempt
                    ),

                    deadline_budget=(
                        deadline_budget
                    ),

                    # Retry somente se ainda houver
                    # orçamento válido para o Gemini.
                    minimum_retry_attempt_seconds=min(
                        10.0,
                        (
                            deadline_budget.total_seconds
                            - deadline_budget.reserve_seconds
                        ) / 2.0,
                    ),
                )
            )


        first_chunk_ms = (
            (
                _inna_stream_time
                .perf_counter()
                - generation_started
            )
            * 1000.0
        )


        # ====================================================
        # PRIMEIRO CHUNK
        # ====================================================

        chunk_count += 1
        last_chunk = first_chunk


        first_text = (
            _extract_stream_text(
                first_chunk
            )
        )


        if first_text:

            text_chunk_count += 1

            yield first_text


        # ====================================================
        # APÓS O PRIMEIRO CHUNK:
        # NÃO HÁ MAIS RETRY.
        # ====================================================

        post_first_started = (
            _inna_stream_time
            .perf_counter()
        )


        try:

            for chunk in iterator:

                chunk_count += 1
                last_chunk = chunk


                chunk_text = (
                    _extract_stream_text(
                        chunk
                    )
                )


                if not chunk_text:
                    continue


                text_chunk_count += 1

                yield chunk_text


        finally:

            post_first_chunk_provider_ms = (
                (
                    _inna_stream_time
                    .perf_counter()
                    - post_first_started
                )
                * 1000.0
            )


        # ====================================================
        # USAGE
        # ====================================================

        if usage_out is not None:

            try:

                from inna_ai.observability.llm.costs import extrair_tokens_resposta


                if last_chunk is not None:

                    extracted_usage = (
                        extrair_tokens_resposta(
                            last_chunk
                        )
                    )


                    usage_out.update(
                        {
                            "tokens_entrada": int(
                                extracted_usage.get(
                                    "tokens_entrada",
                                    0,
                                )
                                or 0
                            ),

                            "tokens_saida": int(
                                extracted_usage.get(
                                    "tokens_saida",
                                    0,
                                )
                                or 0
                            ),

                            "tokens_totais": int(
                                extracted_usage.get(
                                    "tokens_totais",
                                    0,
                                )
                                or 0
                            ),
                        }
                    )


            except Exception:

                usage_out.clear()


        # Não aceitamos stream sem texto.
        if text_chunk_count <= 0:

            raise GeminiTextGenerationError(
                "O Gemini não retornou "
                "conteúdo textual no streaming."
            )


        _write_stream_trace(
            success=True,
        )


    except (
        GeminiTextConfigurationError,
        GeminiTextGenerationError,
        ValueError,
    ) as exc:

        _write_stream_trace(
            success=False,
            error=exc,
        )

        raise


    except Exception as exc:

        _write_stream_trace(
            success=False,
            error=exc,
        )

        raise GeminiTextGenerationError(
            "Não foi possível gerar "
            "a resposta Gemini em streaming "
            f"({type(exc).__name__})."
        ) from exc


def testar_servico_gemini() -> dict:
    """
    Executa um teste simples sem expor informações sensíveis.
    """
    try:
        resposta = gerar_texto_gemini(
            "Responda apenas com: INNA funcionando.",
            temperatura=0.0,
            max_tokens=50,
        )

        return {
            "ok": True,
            "message": "Serviço textual Gemini validado.",
            "response": resposta,
            "model": get_model_for_role(
                LLMRole.DEFAULT
            ),
            "sdk": "google-genai",
        }

    except Exception as exc:
        return {
            "ok": False,
            "message": (
                "Falha no serviço textual Gemini "
                f"({type(exc).__name__})."
            ),
            "response": "",
            "model": get_model_for_role(
                LLMRole.DEFAULT
            ),
            "sdk": "google-genai",
        }


__all__ = [
    "MODELO_TEXTO_PADRAO",
    "gerar_texto_gemini",
    "testar_servico_gemini",
]
