"""
Armazenamento vetorial RAG da INNA.

Responsabilidades:
- preparar extensão, tabela e índices pgvector;
- salvar embeddings de documentos;
- excluir vetores antigos durante reprocessamento;
- verificar embeddings existentes;
- carregar resumo do armazenamento;
- manter compatibilidade com vetores de 3072 dimensões.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Callable


TABELA_EMBEDDINGS = "chunks_embeddings_rag"
DIMENSOES_EMBEDDING = 3072
MODELO_EMBEDDING_BANCO = "models/gemini-embedding-001"

EmbeddingGenerator = Callable[[str], list[float]]


def _carregar_database_url() -> str:
    """
    Obtém DATABASE_URL do ambiente ou do arquivo .env.
    """
    database_url = os.getenv("DATABASE_URL")

    if not database_url:
        try:
            from dotenv import load_dotenv

            load_dotenv(
                dotenv_path=Path(".env"),
                override=False,
            )

            database_url = os.getenv("DATABASE_URL")
        except ImportError:
            database_url = None

    if not database_url:
        raise RuntimeError(
            "DATABASE_URL não encontrada."
        )

    return database_url


def _conectar_postgres():
    """
    Abre conexão PostgreSQL usando psycopg2.
    """
    try:
        import psycopg2
    except ImportError as exc:
        raise RuntimeError(
            "Pacote psycopg2 não instalado."
        ) from exc

    return psycopg2.connect(
        _carregar_database_url()
    )


def _criar_engine_sqlalchemy():
    """
    Cria engine SQLAlchemy para consultas com pandas.
    """
    try:
        from sqlalchemy import create_engine
    except ImportError as exc:
        raise RuntimeError(
            "Pacote SQLAlchemy não instalado."
        ) from exc

    return create_engine(
        _carregar_database_url(),
        pool_pre_ping=True,
    )


def _converter_vetor_pgvector(
    embedding: list[float],
) -> str:
    """
    Converte uma lista numérica para o formato aceito pelo pgvector.
    """
    if not embedding:
        raise ValueError(
            "Embedding vazio ou inválido."
        )

    vetor = [
        float(valor)
        for valor in embedding
    ]

    if len(vetor) != DIMENSOES_EMBEDDING:
        raise ValueError(
            "Dimensão do embedding incompatível: "
            f"esperado={DIMENSOES_EMBEDDING}, "
            f"recebido={len(vetor)}."
        )

    return "[" + ",".join(
        str(valor)
        for valor in vetor
    ) + "]"


def preparar_tabela_embeddings(
    conn=None,
) -> dict:
    """
    Cria extensão e tabela de embeddings.

    Quando uma conexão é recebida, ela não é fechada.
    """
    conexao_propria = conn is None

    try:
        if conexao_propria:
            conn = _conectar_postgres()

        cur = conn.cursor()

        cur.execute(
            "CREATE EXTENSION IF NOT EXISTS vector;"
        )

        cur.execute(f"""
            CREATE TABLE IF NOT EXISTS {TABELA_EMBEDDINGS} (
                id SERIAL PRIMARY KEY,
                documento_id INTEGER
                    REFERENCES documentos_upload_rag(id)
                    ON DELETE CASCADE,
                chunk_id TEXT NOT NULL,
                documento_origem TEXT,
                chunk_index INTEGER,
                texto TEXT NOT NULL,
                metadata JSONB,
                embedding vector({DIMENSOES_EMBEDDING}),
                modelo_embedding TEXT
                    DEFAULT '{MODELO_EMBEDDING_BANCO}',
                criado_em TIMESTAMP DEFAULT NOW(),
                UNIQUE(documento_id, chunk_id)
            );
        """)

        conn.commit()
        cur.close()

        if conexao_propria:
            conn.close()

        return {
            "ok": True,
            "message": (
                "Tabela de embeddings criada/validada."
            ),
        }

    except Exception as exc:
        if conexao_propria and conn:
            try:
                conn.rollback()
                conn.close()
            except Exception:
                pass

        return {
            "ok": False,
            "message": (
                "Erro ao preparar tabela de embeddings: "
                f"{exc}"
            ),
        }


def excluir_embeddings_documento(
    documento_id: int,
    *,
    conn=None,
) -> dict:
    """
    Exclui embeddings vinculados a um documento.
    """
    conexao_propria = conn is None

    try:
        documento_id = int(documento_id)

        if conexao_propria:
            conn = _conectar_postgres()

        cur = conn.cursor()

        cur.execute(
            f"""
            DELETE FROM {TABELA_EMBEDDINGS}
            WHERE documento_id = %s;
            """,
            (documento_id,),
        )

        total_excluidos = cur.rowcount

        if conexao_propria:
            conn.commit()

        cur.close()

        if conexao_propria:
            conn.close()

        return {
            "ok": True,
            "total": total_excluidos,
            "message": (
                f"{total_excluidos} embedding(s) "
                "excluído(s)."
            ),
        }

    except Exception as exc:
        if conexao_propria and conn:
            try:
                conn.rollback()
                conn.close()
            except Exception:
                pass

        return {
            "ok": False,
            "total": 0,
            "message": (
                "Erro ao excluir embeddings: "
                f"{exc}"
            ),
        }


def salvar_chunks_embeddings(
    documento_id: int,
    caminho_embedding_ready: str | Path,
    *,
    gerar_embedding: EmbeddingGenerator,
    substituir_existentes: bool = True,
    modelo_embedding: str = (
        MODELO_EMBEDDING_BANCO
    ),
) -> dict:
    """
    Lê um JSONL, gera embeddings e salva no pgvector.
    """
    if not callable(gerar_embedding):
        return {
            "ok": False,
            "total": 0,
            "message": (
                "Função de geração de embedding inválida."
            ),
        }

    caminho = Path(
        str(caminho_embedding_ready)
    )

    if not caminho.exists():
        return {
            "ok": False,
            "total": 0,
            "message": (
                f"Arquivo JSONL não encontrado: {caminho}"
            ),
        }

    try:
        documento_id = int(documento_id)

        conn = _conectar_postgres()

        preparacao = preparar_tabela_embeddings(
            conn
        )

        if not preparacao.get("ok"):
            conn.close()
            return {
                "ok": False,
                "total": 0,
                "message": preparacao.get("message"),
            }

        cur = conn.cursor()

        if substituir_existentes:
            cur.execute(
                f"""
                DELETE FROM {TABELA_EMBEDDINGS}
                WHERE documento_id = %s;
                """,
                (documento_id,),
            )

        total_salvos = 0
        total_ignorados = 0

        with caminho.open(
            "r",
            encoding="utf-8",
        ) as arquivo:
            for numero_linha, linha in enumerate(
                arquivo,
                start=1,
            ):
                linha = linha.strip()

                if not linha:
                    continue

                try:
                    item = json.loads(linha)
                except json.JSONDecodeError:
                    total_ignorados += 1
                    continue

                texto = str(
                    item.get("texto") or ""
                ).strip()

                if not texto:
                    total_ignorados += 1
                    continue

                chunk_id = item.get("chunk_id")

                if not chunk_id:
                    chunk_id = (
                        f"documento_{documento_id}"
                        f"_linha_{numero_linha}"
                    )

                embedding = gerar_embedding(texto)

                vetor_pgvector = (
                    _converter_vetor_pgvector(
                        embedding
                    )
                )

                cur.execute(
                    f"""
                    INSERT INTO {TABELA_EMBEDDINGS} (
                        documento_id,
                        chunk_id,
                        documento_origem,
                        chunk_index,
                        texto,
                        metadata,
                        embedding,
                        modelo_embedding
                    )
                    VALUES (
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s::jsonb,
                        %s::vector,
                        %s
                    )
                    ON CONFLICT (
                        documento_id,
                        chunk_id
                    )
                    DO UPDATE SET
                        documento_origem =
                            EXCLUDED.documento_origem,
                        chunk_index =
                            EXCLUDED.chunk_index,
                        texto =
                            EXCLUDED.texto,
                        metadata =
                            EXCLUDED.metadata,
                        embedding =
                            EXCLUDED.embedding,
                        modelo_embedding =
                            EXCLUDED.modelo_embedding,
                        criado_em = NOW();
                    """,
                    (
                        documento_id,
                        str(chunk_id),
                        item.get(
                            "documento_origem"
                        ),
                        int(
                            item.get(
                                "chunk_index",
                                0,
                            )
                            or 0
                        ),
                        texto,
                        json.dumps(
                            item.get(
                                "metadata",
                                {},
                            ),
                            ensure_ascii=False,
                        ),
                        vetor_pgvector,
                        modelo_embedding,
                    ),
                )

                total_salvos += 1

        conn.commit()
        cur.close()
        conn.close()

        return {
            "ok": True,
            "total": total_salvos,
            "total_ignorados": total_ignorados,
            "message": (
                f"{total_salvos} embeddings salvos "
                "no pgvector."
            ),
        }

    except Exception as exc:
        try:
            conn.rollback()
            conn.close()
        except Exception:
            pass

        return {
            "ok": False,
            "total": 0,
            "message": (
                "Erro ao gerar/salvar embeddings "
                f"no pgvector: {exc}"
            ),
        }


def documento_tem_embeddings(
    documento_id: int,
) -> tuple[bool, int]:
    """
    Verifica se um documento já possui embeddings.
    """
    try:
        conn = _conectar_postgres()
        cur = conn.cursor()

        cur.execute(
            f"""
            SELECT COUNT(*)
            FROM {TABELA_EMBEDDINGS}
            WHERE documento_id = %s;
            """,
            (int(documento_id),),
        )

        total = int(
            cur.fetchone()[0]
        )

        cur.close()
        conn.close()

        return total > 0, total

    except Exception:
        return False, 0


def criar_indices_pgvector() -> dict:
    """
    Cria índices HNSW e índices auxiliares.
    """
    try:
        conn = _conectar_postgres()
        cur = conn.cursor()

        cur.execute(
            "CREATE EXTENSION IF NOT EXISTS vector;"
        )

        cur.execute(f"""
            CREATE INDEX IF NOT EXISTS
                idx_chunks_embeddings_rag_embedding_hnsw_halfvec
            ON {TABELA_EMBEDDINGS}
            USING hnsw (
                (
                    embedding::halfvec(
                        {DIMENSOES_EMBEDDING}
                    )
                )
                halfvec_cosine_ops
            );
        """)

        cur.execute(f"""
            CREATE INDEX IF NOT EXISTS
                idx_chunks_embeddings_rag_documento_id
            ON {TABELA_EMBEDDINGS}
                (documento_id);
        """)

        cur.execute(f"""
            CREATE INDEX IF NOT EXISTS
                idx_chunks_embeddings_rag_chunk_id
            ON {TABELA_EMBEDDINGS}
                (chunk_id);
        """)

        cur.execute(
            f"ANALYZE {TABELA_EMBEDDINGS};"
        )

        conn.commit()
        cur.close()
        conn.close()

        return {
            "ok": True,
            "message": (
                "Índices pgvector criados/validados "
                "com sucesso."
            ),
        }

    except Exception as exc:
        return {
            "ok": False,
            "message": (
                "Erro ao criar índices pgvector: "
                f"{exc}"
            ),
        }


def carregar_resumo_embeddings() -> dict:
    """
    Retorna métricas e DataFrame com resumo por documento.
    """
    import pandas as pd

    estrutura_vazia = {
        "ok": False,
        "message": "",
        "total_embeddings": 0,
        "embeddings_ativos": 0,
        "embeddings_inativos": 0,
        "documentos_com_embeddings": 0,
        "documentos_ativos_com_embeddings": 0,
        "documentos_inativos_com_embeddings": 0,
        "df": pd.DataFrame(),
    }

    try:
        engine = _criar_engine_sqlalchemy()

        query = f"""
            SELECT
                ce.documento_id,
                du.nome_salvo,
                COALESCE(
                    du.ativo,
                    TRUE
                ) AS ativo,
                COUNT(*) AS total_embeddings,
                MAX(
                    ce.modelo_embedding
                ) AS modelo_embedding,
                MAX(
                    ce.criado_em
                ) AS ultimo_processamento
            FROM {TABELA_EMBEDDINGS} ce
            LEFT JOIN documentos_upload_rag du
                ON du.id = ce.documento_id
            GROUP BY
                ce.documento_id,
                du.nome_salvo,
                COALESCE(
                    du.ativo,
                    TRUE
                )
            ORDER BY ultimo_processamento DESC;
        """

        with engine.connect() as connection:
            df = pd.read_sql(
                query,
                connection,
            )

        engine.dispose()

        if df.empty:
            estrutura_vazia.update({
                "ok": True,
                "message": (
                    "Nenhum embedding encontrado."
                ),
                "df": df,
            })

            return estrutura_vazia

        total_embeddings = int(
            df["total_embeddings"].sum()
        )

        df_ativos = df[
            df["ativo"] == True
        ]

        df_inativos = df[
            df["ativo"] == False
        ]

        embeddings_ativos = (
            int(
                df_ativos[
                    "total_embeddings"
                ].sum()
            )
            if not df_ativos.empty
            else 0
        )

        embeddings_inativos = (
            int(
                df_inativos[
                    "total_embeddings"
                ].sum()
            )
            if not df_inativos.empty
            else 0
        )

        return {
            "ok": True,
            "message": (
                "Resumo de embeddings carregado."
            ),
            "total_embeddings": total_embeddings,
            "embeddings_ativos": embeddings_ativos,
            "embeddings_inativos": (
                embeddings_inativos
            ),
            "documentos_com_embeddings": int(
                df["documento_id"].nunique()
            ),
            "documentos_ativos_com_embeddings": int(
                df_ativos[
                    "documento_id"
                ].nunique()
            )
            if not df_ativos.empty
            else 0,
            "documentos_inativos_com_embeddings": int(
                df_inativos[
                    "documento_id"
                ].nunique()
            )
            if not df_inativos.empty
            else 0,
            "df": df,
        }

    except Exception as exc:
        estrutura_vazia["message"] = (
            "Erro ao carregar resumo de embeddings: "
            f"{exc}"
        )

        return estrutura_vazia


def obter_status_vector_store() -> dict[str, Any]:
    """
    Retorna configuração pública do armazenamento.
    """
    return {
        "tabela": TABELA_EMBEDDINGS,
        "dimensoes": DIMENSOES_EMBEDDING,
        "modelo": MODELO_EMBEDDING_BANCO,
        "indice": "hnsw",
        "metrica": "cosine",
        "tipo_indice": "halfvec",
    }


__all__ = [
    "TABELA_EMBEDDINGS",
    "DIMENSOES_EMBEDDING",
    "MODELO_EMBEDDING_BANCO",
    "preparar_tabela_embeddings",
    "excluir_embeddings_documento",
    "salvar_chunks_embeddings",
    "documento_tem_embeddings",
    "criar_indices_pgvector",
    "carregar_resumo_embeddings",
    "obter_status_vector_store",
]
