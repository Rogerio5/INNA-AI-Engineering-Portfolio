"""
Observabilidade de tokens e custos de LLM da INNA.

Responsabilidades:
- calcular custos estimados;
- extrair tokens de respostas do Gemini;
- persistir eventos no PostgreSQL;
- consultar histórico de consumo;
- manter preços configuráveis pelo ambiente.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd


NOME_TABELA = "llm_usage_events_inna"


def _carregar_database_url() -> str:
    database_url = os.getenv(
        "DATABASE_URL"
    )

    if not database_url:
        try:
            from dotenv import load_dotenv

            load_dotenv(
                dotenv_path=Path(".env")
            )

            database_url = os.getenv(
                "DATABASE_URL"
            )

        except Exception:
            database_url = None

    if not database_url:
        raise RuntimeError(
            "DATABASE_URL não encontrada."
        )

    return database_url


def _criar_engine():
    from sqlalchemy import create_engine

    return create_engine(
        _carregar_database_url(),
        pool_pre_ping=True,
    )


def normalizar_modelo(
    modelo: str | None,
) -> str:
    """
    Normaliza o nome do modelo para uso em variáveis de ambiente.
    """
    valor = str(
        modelo or "desconhecido"
    ).strip().lower()

    return (
        valor.replace("-", "_")
        .replace(".", "_")
        .replace("/", "_")
        .replace(":", "_")
    )


def carregar_precos_modelo(
    modelo: str | None,
) -> dict[str, Any]:
    """
    Lê preços por 1 milhão de tokens do ambiente.

    Exemplo para gemini-2.5-flash:

    LLM_PRICE_GEMINI_2_5_FLASH_INPUT_USD_PER_1M
    LLM_PRICE_GEMINI_2_5_FLASH_OUTPUT_USD_PER_1M

    Também aceita preços gerais:

    LLM_PRICE_DEFAULT_INPUT_USD_PER_1M
    LLM_PRICE_DEFAULT_OUTPUT_USD_PER_1M
    """
    chave = normalizar_modelo(
        modelo
    ).upper()

    input_especifico = os.getenv(
        f"LLM_PRICE_{chave}_INPUT_USD_PER_1M"
    )

    output_especifico = os.getenv(
        f"LLM_PRICE_{chave}_OUTPUT_USD_PER_1M"
    )

    input_padrao = os.getenv(
        "LLM_PRICE_DEFAULT_INPUT_USD_PER_1M",
        "0",
    )

    output_padrao = os.getenv(
        "LLM_PRICE_DEFAULT_OUTPUT_USD_PER_1M",
        "0",
    )

    try:
        preco_input = float(
            input_especifico
            if input_especifico is not None
            else input_padrao
        )
    except (TypeError, ValueError):
        preco_input = 0.0

    try:
        preco_output = float(
            output_especifico
            if output_especifico is not None
            else output_padrao
        )
    except (TypeError, ValueError):
        preco_output = 0.0

    return {
        "modelo": str(
            modelo or "desconhecido"
        ),
        "input_usd_por_1m": max(
            preco_input,
            0.0,
        ),
        "output_usd_por_1m": max(
            preco_output,
            0.0,
        ),
        "configurado": (
            preco_input > 0
            or preco_output > 0
        ),
    }


def calcular_custo_estimado(
    *,
    tokens_entrada: int,
    tokens_saida: int,
    preco_entrada_usd_por_1m: float,
    preco_saida_usd_por_1m: float,
) -> dict[str, float]:
    """
    Calcula o custo estimado da chamada em dólares.
    """
    entrada = max(
        int(tokens_entrada or 0),
        0,
    )

    saida = max(
        int(tokens_saida or 0),
        0,
    )

    custo_entrada = (
        entrada
        / 1_000_000
    ) * max(
        float(
            preco_entrada_usd_por_1m
            or 0
        ),
        0.0,
    )

    custo_saida = (
        saida
        / 1_000_000
    ) * max(
        float(
            preco_saida_usd_por_1m
            or 0
        ),
        0.0,
    )

    custo_total = (
        custo_entrada
        + custo_saida
    )

    return {
        "custo_entrada_usd": round(
            custo_entrada,
            10,
        ),
        "custo_saida_usd": round(
            custo_saida,
            10,
        ),
        "custo_total_usd": round(
            custo_total,
            10,
        ),
    }


def extrair_tokens_resposta(
    resposta: Any,
) -> dict[str, int]:
    """
    Extrai usage_metadata de uma resposta do Google GenAI.

    É tolerante a objetos, dicionários e campos ausentes.
    """
    usage = getattr(
        resposta,
        "usage_metadata",
        None,
    )

    if usage is None and isinstance(
        resposta,
        dict,
    ):
        usage = resposta.get(
            "usage_metadata"
        )

    if usage is None:
        return {
            "tokens_entrada": 0,
            "tokens_saida": 0,
            "tokens_totais": 0,
        }

    def obter(
        *nomes: str,
    ) -> int:
        for nome in nomes:
            if isinstance(usage, dict):
                valor = usage.get(nome)
            else:
                valor = getattr(
                    usage,
                    nome,
                    None,
                )

            if valor is not None:
                try:
                    return max(
                        int(valor),
                        0,
                    )
                except (
                    TypeError,
                    ValueError,
                ):
                    return 0

        return 0

    tokens_entrada = obter(
        "prompt_token_count",
        "prompt_tokens",
        "input_tokens",
    )

    tokens_saida = obter(
        "candidates_token_count",
        "completion_tokens",
        "output_tokens",
    )

    tokens_totais = obter(
        "total_token_count",
        "total_tokens",
    )

    if tokens_totais <= 0:
        tokens_totais = (
            tokens_entrada
            + tokens_saida
        )

    return {
        "tokens_entrada": tokens_entrada,
        "tokens_saida": tokens_saida,
        "tokens_totais": tokens_totais,
    }


def inicializar_tabela_llm_usage() -> dict[str, Any]:
    """
    Cria a tabela de consumo de LLM e seus índices.
    """
    try:
        from sqlalchemy import text

        engine = _criar_engine()

        tabela = text(f"""
            CREATE TABLE IF NOT EXISTS {NOME_TABELA} (
                id BIGSERIAL PRIMARY KEY,
                criado_em TIMESTAMPTZ NOT NULL
                    DEFAULT NOW(),

                provider VARCHAR(50) NOT NULL
                    DEFAULT 'google',

                modelo VARCHAR(150) NOT NULL,
                operacao VARCHAR(120) NOT NULL,
                origem VARCHAR(120),

                usuario_id VARCHAR(255),
                trace_id VARCHAR(255),
                request_id VARCHAR(255),

                tokens_entrada INTEGER NOT NULL
                    DEFAULT 0,

                tokens_saida INTEGER NOT NULL
                    DEFAULT 0,

                tokens_totais INTEGER NOT NULL
                    DEFAULT 0,

                preco_entrada_usd_por_1m
                    NUMERIC(18, 8) NOT NULL
                    DEFAULT 0,

                preco_saida_usd_por_1m
                    NUMERIC(18, 8) NOT NULL
                    DEFAULT 0,

                custo_entrada_usd
                    NUMERIC(20, 10) NOT NULL
                    DEFAULT 0,

                custo_saida_usd
                    NUMERIC(20, 10) NOT NULL
                    DEFAULT 0,

                custo_total_usd
                    NUMERIC(20, 10) NOT NULL
                    DEFAULT 0,

                duracao_ms NUMERIC(18, 3)
                    NOT NULL DEFAULT 0,

                sucesso BOOLEAN NOT NULL
                    DEFAULT TRUE,

                erro_tipo VARCHAR(150),
                erro_mensagem TEXT,

                metadados_json JSONB NOT NULL
                    DEFAULT '{{}}'::jsonb
            );
        """)

        indices = [
            text(f"""
                CREATE INDEX IF NOT EXISTS
                idx_{NOME_TABELA}_criado_em
                ON {NOME_TABELA}
                (criado_em DESC);
            """),
            text(f"""
                CREATE INDEX IF NOT EXISTS
                idx_{NOME_TABELA}_modelo
                ON {NOME_TABELA}
                (modelo);
            """),
            text(f"""
                CREATE INDEX IF NOT EXISTS
                idx_{NOME_TABELA}_usuario
                ON {NOME_TABELA}
                (usuario_id);
            """),
            text(f"""
                CREATE INDEX IF NOT EXISTS
                idx_{NOME_TABELA}_trace
                ON {NOME_TABELA}
                (trace_id);
            """),
        ]

        with engine.begin() as connection:
            connection.execute(tabela)

            for indice in indices:
                connection.execute(indice)

        engine.dispose()

        return {
            "ok": True,
            "tabela": NOME_TABELA,
            "message": (
                "Tabela de consumo de LLM inicializada."
            ),
        }

    except Exception as exc:
        return {
            "ok": False,
            "tabela": NOME_TABELA,
            "message": (
                "Erro ao inicializar consumo de LLM: "
                f"{exc}"
            ),
        }


def registrar_consumo_llm(
    *,
    modelo: str,
    operacao: str,
    tokens_entrada: int = 0,
    tokens_saida: int = 0,
    tokens_totais: int | None = None,
    provider: str = "google",
    origem: str | None = None,
    usuario_id: str | None = None,
    trace_id: str | None = None,
    request_id: str | None = None,
    duracao_ms: float = 0.0,
    sucesso: bool = True,
    erro_tipo: str | None = None,
    erro_mensagem: str | None = None,
    metadados: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Persiste um evento de consumo e custo.
    """
    inicializacao = (
        inicializar_tabela_llm_usage()
    )

    if not inicializacao.get("ok"):
        return inicializacao

    entrada = max(
        int(tokens_entrada or 0),
        0,
    )

    saida = max(
        int(tokens_saida or 0),
        0,
    )

    total = (
        max(
            int(tokens_totais),
            0,
        )
        if tokens_totais is not None
        else entrada + saida
    )

    precos = carregar_precos_modelo(
        modelo
    )

    custos = calcular_custo_estimado(
        tokens_entrada=entrada,
        tokens_saida=saida,
        preco_entrada_usd_por_1m=(
            precos[
                "input_usd_por_1m"
            ]
        ),
        preco_saida_usd_por_1m=(
            precos[
                "output_usd_por_1m"
            ]
        ),
    )

    try:
        from sqlalchemy import text

        engine = _criar_engine()

        inserir = text(f"""
            INSERT INTO {NOME_TABELA} (
                provider,
                modelo,
                operacao,
                origem,
                usuario_id,
                trace_id,
                request_id,
                tokens_entrada,
                tokens_saida,
                tokens_totais,
                preco_entrada_usd_por_1m,
                preco_saida_usd_por_1m,
                custo_entrada_usd,
                custo_saida_usd,
                custo_total_usd,
                duracao_ms,
                sucesso,
                erro_tipo,
                erro_mensagem,
                metadados_json
            )
            VALUES (
                :provider,
                :modelo,
                :operacao,
                :origem,
                :usuario_id,
                :trace_id,
                :request_id,
                :tokens_entrada,
                :tokens_saida,
                :tokens_totais,
                :preco_entrada,
                :preco_saida,
                :custo_entrada,
                :custo_saida,
                :custo_total,
                :duracao_ms,
                :sucesso,
                :erro_tipo,
                :erro_mensagem,
                CAST(:metadados_json AS JSONB)
            )
            RETURNING id, criado_em;
        """)

        parametros = {
            "provider": str(
                provider or "google"
            )[:50],
            "modelo": str(
                modelo or "desconhecido"
            )[:150],
            "operacao": str(
                operacao or "desconhecida"
            )[:120],
            "origem": (
                str(origem)[:120]
                if origem
                else None
            ),
            "usuario_id": (
                str(usuario_id)[:255]
                if usuario_id
                else None
            ),
            "trace_id": (
                str(trace_id)[:255]
                if trace_id
                else None
            ),
            "request_id": (
                str(request_id)[:255]
                if request_id
                else None
            ),
            "tokens_entrada": entrada,
            "tokens_saida": saida,
            "tokens_totais": total,
            "preco_entrada": (
                precos[
                    "input_usd_por_1m"
                ]
            ),
            "preco_saida": (
                precos[
                    "output_usd_por_1m"
                ]
            ),
            "custo_entrada": (
                custos[
                    "custo_entrada_usd"
                ]
            ),
            "custo_saida": (
                custos[
                    "custo_saida_usd"
                ]
            ),
            "custo_total": (
                custos[
                    "custo_total_usd"
                ]
            ),
            "duracao_ms": max(
                float(duracao_ms or 0),
                0.0,
            ),
            "sucesso": bool(sucesso),
            "erro_tipo": (
                str(erro_tipo)[:150]
                if erro_tipo
                else None
            ),
            "erro_mensagem": (
                str(erro_mensagem)[:4000]
                if erro_mensagem
                else None
            ),
            "metadados_json": json.dumps(
                metadados or {},
                ensure_ascii=False,
                default=str,
            ),
        }

        with engine.begin() as connection:
            registro = connection.execute(
                inserir,
                parametros,
            ).mappings().first()

        engine.dispose()

        return {
            "ok": True,
            "id": int(
                registro["id"]
            ),
            "criado_em": registro[
                "criado_em"
            ],
            "tokens": {
                "entrada": entrada,
                "saida": saida,
                "total": total,
            },
            "precos": precos,
            "custos": custos,
            "message": (
                "Consumo de LLM registrado."
            ),
        }

    except Exception as exc:
        return {
            "ok": False,
            "message": (
                "Erro ao registrar consumo de LLM: "
                f"{exc}"
            ),
        }


def carregar_consumo_llm(
    *,
    limite: int = 1000,
    dias: int | None = 30,
) -> dict[str, Any]:
    """
    Consulta eventos históricos de consumo.
    """
    inicializacao = (
        inicializar_tabela_llm_usage()
    )

    if not inicializacao.get("ok"):
        return {
            **inicializacao,
            "df": pd.DataFrame(),
            "total": 0,
        }

    try:
        from sqlalchemy import text

        engine = _criar_engine()

        filtro = ""

        parametros: dict[str, Any] = {
            "limite": max(
                int(limite),
                1,
            ),
        }

        if dias is not None:
            filtro = """
                WHERE criado_em >= (
                    NOW()
                    - (
                        :dias
                        * INTERVAL '1 day'
                    )
                )
            """

            parametros["dias"] = max(
                int(dias),
                1,
            )

        consulta = text(f"""
            SELECT
                id,
                criado_em,
                provider,
                modelo,
                operacao,
                origem,
                usuario_id,
                trace_id,
                request_id,
                tokens_entrada,
                tokens_saida,
                tokens_totais,
                custo_entrada_usd,
                custo_saida_usd,
                custo_total_usd,
                duracao_ms,
                sucesso,
                erro_tipo,
                erro_mensagem,
                metadados_json
            FROM {NOME_TABELA}
            {filtro}
            ORDER BY criado_em DESC
            LIMIT :limite;
        """)

        with engine.connect() as connection:
            df = pd.read_sql(
                consulta,
                connection,
                params=parametros,
            )

        engine.dispose()

        if not df.empty:
            df["criado_em"] = pd.to_datetime(
                df["criado_em"],
                utc=True,
                errors="coerce",
            )

            numericas = [
                "tokens_entrada",
                "tokens_saida",
                "tokens_totais",
                "custo_entrada_usd",
                "custo_saida_usd",
                "custo_total_usd",
                "duracao_ms",
            ]

            for coluna in numericas:
                df[coluna] = pd.to_numeric(
                    df[coluna],
                    errors="coerce",
                ).fillna(0)

        return {
            "ok": True,
            "df": df,
            "total": len(df),
            "message": (
                "Consumo de LLM carregado."
            ),
        }

    except Exception as exc:
        return {
            "ok": False,
            "df": pd.DataFrame(),
            "total": 0,
            "message": (
                "Erro ao carregar consumo de LLM: "
                f"{exc}"
            ),
        }


__all__ = [
    "NOME_TABELA",
    "normalizar_modelo",
    "carregar_precos_modelo",
    "calcular_custo_estimado",
    "extrair_tokens_resposta",
    "inicializar_tabela_llm_usage",
    "registrar_consumo_llm",
    "carregar_consumo_llm",
]


# ============================================================
# SABINO_AI_LLM_USAGE_ASYNC_WRITER_V1
# ============================================================

class _LLMUsageAsyncWriter:
    """
    Persiste eventos de consumo LLM fora do caminho crítico.

    Garantias:
    - fila limitada;
    - enqueue não bloqueante;
    - worker daemon criado sob demanda;
    - falha de telemetria não quebra a resposta;
    - registrar_consumo_llm síncrono permanece disponível.
    """

    def __init__(
        self,
        *,
        max_queue_size: int = 1024,
    ) -> None:

        import queue
        import threading

        self._queue = queue.Queue(
            maxsize=max_queue_size
        )

        self._lock = threading.RLock()

        self._worker = None

        self._enqueued = 0
        self._completed = 0
        self._failed = 0
        self._queue_full_drops = 0


    def _ensure_worker(self) -> None:

        import threading

        with self._lock:

            if (
                self._worker is not None
                and self._worker.is_alive()
            ):
                return


            self._worker = threading.Thread(
                target=self._run,
                name="inna-llm-usage-writer",
                daemon=True,
            )

            self._worker.start()


    def enqueue(
        self,
        payload: dict,
    ) -> bool:

        import queue

        self._ensure_worker()

        try:

            self._queue.put_nowait(
                dict(payload)
            )

        except queue.Full:

            with self._lock:
                self._queue_full_drops += 1

            return False


        with self._lock:
            self._enqueued += 1

        return True


    def _run(self) -> None:

        while True:

            payload = self._queue.get()

            try:

                resultado = registrar_consumo_llm(
                    **payload
                )

                ok = bool(
                    isinstance(
                        resultado,
                        dict,
                    )
                    and resultado.get("ok")
                )

                with self._lock:

                    if not ok:
                        self._failed += 1


            except Exception:

                with self._lock:
                    self._failed += 1


            finally:

                with self._lock:
                    self._completed += 1

                self._queue.task_done()


    def snapshot(
        self,
    ) -> dict:

        with self._lock:

            worker_alive = bool(
                self._worker is not None
                and self._worker.is_alive()
            )

            return {
                "enqueued": self._enqueued,
                "completed": self._completed,
                "failed": self._failed,
                "queue_full_drops": (
                    self._queue_full_drops
                ),
                "queue_size": (
                    self._queue.qsize()
                ),
                "worker_alive": worker_alive,
            }


_LLM_USAGE_ASYNC_WRITER = (
    _LLMUsageAsyncWriter()
)


def registrar_consumo_llm_assincrono(
    **payload,
) -> dict:
    """
    Agenda persistência de consumo LLM sem bloquear
    a resposta funcional da INNA.
    """

    accepted = (
        _LLM_USAGE_ASYNC_WRITER.enqueue(
            payload
        )
    )

    return {
        "ok": accepted,
        "queued": accepted,
        "mode": "async_queue",
        "snapshot": (
            _LLM_USAGE_ASYNC_WRITER.snapshot()
        ),
    }


def obter_snapshot_llm_usage_writer(
) -> dict:
    """
    Estado operacional do writer de consumo LLM.
    """

    return (
        _LLM_USAGE_ASYNC_WRITER.snapshot()
    )

