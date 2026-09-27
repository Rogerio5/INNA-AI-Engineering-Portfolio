"""
Recuperação semântica RAG da INNA com PostgreSQL e pgvector.

Responsabilidades:
- inferir categorias prioritárias da pergunta;
- gerar o vetor da pergunta por função injetada;
- consultar embeddings no pgvector;
- considerar somente documentos ativos;
- calcular similaridade aproximada;
- aplicar bônus de categoria;
- ordenar e retornar os melhores chunks.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

try:
    from inna_ai.persistence.postgres import cursor_postgres
except ImportError:
    from inna_ai.persistence.postgres import cursor_postgres


EmbeddingGenerator = Callable[[str], list[float]]
ChunkClassifier = Callable[[str], str]


def inferir_categorias_pergunta(
    pergunta: str,
) -> list[str]:
    """
    Identifica categorias prioritárias com base na pergunta.
    """
    if not pergunta:
        return ["geral"]

    pergunta_lower = str(pergunta).lower()

    regras = [
        (
            [
                "pix",
                "transferência",
                "transferencia",
                "devolver",
                "valor estranho",
                "dinheiro estranho",
            ],
            ["pix", "seguranca"],
        ),
        (
            [
                "cartão",
                "cartao",
                "fatura",
                "parcelas",
                "parcelado",
                "limite",
                "crédito",
                "credito",
            ],
            [
                "cartao_credito",
                "organizacao_financeira",
                "dividas",
            ],
        ),
        (
            [
                "dívida",
                "divida",
                "dívidas",
                "dividas",
                "endividado",
                "juros",
                "negociar",
                "negociação",
                "negociacao",
            ],
            [
                "dividas",
                "organizacao_financeira",
                "cartao_credito",
            ],
        ),
        (
            [
                "reserva",
                "guardar",
                "poupar",
                "emergência",
                "emergencia",
            ],
            [
                "reserva_financeira",
                "organizacao_financeira",
            ],
        ),
        (
            [
                "organizar",
                "orçamento",
                "orcamento",
                "renda",
                "gastos",
                "controle financeiro",
            ],
            [
                "organizacao_financeira",
                "dividas",
                "reserva_financeira",
            ],
        ),
        (
            [
                "senha",
                "token",
                "golpe",
                "link",
                "sms",
                "segurança",
                "seguranca",
                "dados sensíveis",
                "dados sensiveis",
            ],
            ["seguranca", "pix"],
        ),
    ]

    categorias = []

    for termos, categorias_regra in regras:
        if any(
            termo in pergunta_lower
            for termo in termos
        ):
            for categoria in categorias_regra:
                if categoria not in categorias:
                    categorias.append(categoria)

    return categorias or ["geral"]


def _validar_limite(limite: Any) -> int:
    """
    Mantém o limite entre 1 e 20 chunks.
    """
    try:
        limite_final = int(limite)
    except (TypeError, ValueError):
        limite_final = 5

    return max(1, min(limite_final, 20))


def _converter_embedding_pgvector(
    embedding: list[float],
) -> str:
    """
    Converte a lista numérica para a representação aceita pelo pgvector.
    """
    if not embedding:
        raise ValueError(
            "O modelo não retornou um embedding válido."
        )

    valores = [
        str(float(valor))
        for valor in embedding
    ]

    return "[" + ",".join(valores) + "]"


def _calcular_similaridade(
    distancia: Any,
) -> float:
    """
    Converte distância do cosseno em similaridade aproximada.
    """
    try:
        similaridade = 1.0 - float(distancia)
    except (TypeError, ValueError):
        similaridade = 0.0

    return round(similaridade, 4)


def _calcular_score_rag(
    similaridade: float,
    prioridade_categoria: int,
    *,
    bonus_categoria: float = 0.08,
) -> float:
    """
    Combina similaridade semântica e bônus de categoria.
    """
    return round(
        float(similaridade)
        + (
            float(bonus_categoria)
            * int(prioridade_categoria)
        ),
        4,
    )


def _extrair_termos_busca_textual(
    pergunta: str,
    *,
    limite: int = 10,
) -> list[str]:
    """
    Extrai termos relevantes para o retrieval textual estruturado.
    """
    import re

    texto = str(
        pergunta or ""
    ).lower()

    candidatos = re.findall(
        r"[0-9a-zà-ÿ_-]{2,}",
        texto,
    )

    ignorados = {
        "a",
        "ao",
        "aos",
        "as",
        "com",
        "como",
        "da",
        "das",
        "de",
        "do",
        "dos",
        "e",
        "em",
        "essa",
        "esse",
        "eu",
        "isso",
        "me",
        "meu",
        "minha",
        "na",
        "nas",
        "no",
        "nos",
        "o",
        "os",
        "para",
        "por",
        "posso",
        "que",
        "qual",
        "quais",
        "se",
        "sem",
        "sobre",
        "um",
        "uma",
    }

    termos: list[str] = []

    for candidato in candidatos:
        if candidato in ignorados:
            continue

        if candidato in termos:
            continue

        termos.append(candidato)

        if len(termos) >= limite:
            break

    return termos


def buscar_chunks_semanticos(
    pergunta: str,
    *,
    limite: int = 5,
    gerar_embedding: EmbeddingGenerator,
    classificar_chunk: ChunkClassifier,
    dimensoes: int = 3072,
    bonus_categoria: float = 0.08,
    profiling: dict[str, float] | None = None,
) -> dict:
    """
    Executa a recuperação semântica completa.

    As funções de embedding e classificação são recebidas como
    dependências para manter o serviço independente do dashboard.
    """
    pergunta = str(pergunta or "").strip()

    if not pergunta:
        return {
            "ok": False,
            "message": "Pergunta vazia.",
            "resultados": [],
        }

    if not callable(gerar_embedding):
        return {
            "ok": False,
            "message": "Função de geração de embedding inválida.",
            "resultados": [],
        }

    if not callable(classificar_chunk):
        return {
            "ok": False,
            "message": "Função de classificação de chunks inválida.",
            "resultados": [],
        }

    limite_final = _validar_limite(limite)
    limite_busca = max(limite_final * 4, 10)

    categorias_prioritarias = (
        inferir_categorias_pergunta(pergunta)
    )

    try:
        import time

        semantic_started = time.perf_counter()

        embedding_started = time.perf_counter()

        embedding_pergunta = gerar_embedding(pergunta)

        query_embedding_ms = round(
            (
                time.perf_counter()
                - embedding_started
            )
            * 1000,
            2,
        )

        conversion_started = time.perf_counter()

        vetor_pgvector = _converter_embedding_pgvector(
            embedding_pergunta
        )

        vector_conversion_ms = round(
            (
                time.perf_counter()
                - conversion_started
            )
            * 1000,
            2,
        )

        sql = f"""
            SELECT
                ce.id,
                ce.documento_id,
                ce.chunk_id,
                ce.documento_origem,
                ce.chunk_index,
                ce.texto,
                du.nome_logico AS documento_key,
                COALESCE(
                    ce.metadata ->> 'document_title',
                    du.nome_original,
                    du.nome_logico,
                    'Documento INNA'
                ) AS titulo,
                COALESCE(
                    ce.documento_origem,
                    du.caminho_upload,
                    du.nome_salvo,
                    du.nome_logico
                ) AS fonte,
                COALESCE(
                    ce.metadata ->> 'area',
                    du.origem,
                    'conhecimento_inna'
                ) AS categoria_documento,
                COALESCE(
                    ce.metadata ->> 'language',
                    'pt-BR'
                ) AS idioma,
                ce.metadata,
                ce.modelo_embedding,
                ce.embedding::halfvec({int(dimensoes)})
                    <=> %s::halfvec({int(dimensoes)})
                    AS distancia
            FROM chunks_embeddings_rag ce
            JOIN documentos_upload_rag du
                ON du.id = ce.documento_id
            WHERE COALESCE(du.ativo, TRUE) = TRUE
              AND NULLIF(
                    BTRIM(
                        COALESCE(
                            du.nome_logico,
                            ''
                        )
                    ),
                    ''
                  ) IS NOT NULL
            ORDER BY
                ce.embedding::halfvec({int(dimensoes)})
                <=> %s::halfvec({int(dimensoes)})
            LIMIT %s;
        """

        database_started = time.perf_counter()

        with cursor_postgres(
            dict_cursor=True,
            commit_automatico=False,
        ) as cursor:
            cursor.execute(
                sql,
                (
                    vetor_pgvector,
                    vetor_pgvector,
                    limite_busca,
                ),
            )

            registros = cursor.fetchall()

        vector_database_ms = round(
            (
                time.perf_counter()
                - database_started
            )
            * 1000,
            2,
        )

        postprocess_started = time.perf_counter()

        resultados = []

        for registro in registros:
            item = dict(registro)

            texto = item.get("texto") or ""
            distancia = float(
                item.get("distancia") or 0
            )

            categoria = (
                classificar_chunk(texto)
                or item.get(
                    "categoria_documento"
                )
                or "geral"
            )

            similaridade = _calcular_similaridade(
                distancia
            )

            prioridade_categoria = int(
                categoria in categorias_prioritarias
            )

            item.update({
                "chunk_text": texto,
                "distancia": distancia,
                "similaridade_aproximada": similaridade,
                "score": similaridade,
                "categoria": categoria,
                "modo_busca": (
                    "rag_estruturado_3072_vetorial"
                ),
                "categorias_prioritarias": (
                    categorias_prioritarias
                ),
                "prioridade_categoria": (
                    prioridade_categoria
                ),
                "score_rag": _calcular_score_rag(
                    similaridade,
                    prioridade_categoria,
                    bonus_categoria=bonus_categoria,
                ),
            })

            resultados.append(item)

        resultados = sorted(
            resultados,
            key=lambda item: (
                item.get(
                    "prioridade_categoria",
                    0,
                ),
                item.get(
                    "similaridade_aproximada",
                    0,
                ),
            ),
            reverse=True,
        )[:limite_final]

        categorias_texto = ", ".join(
            categorias_prioritarias
        )

        vector_postprocess_ms = round(
            (
                time.perf_counter()
                - postprocess_started
            )
            * 1000,
            2,
        )

        vector_semantic_total_ms = round(
            (
                time.perf_counter()
                - semantic_started
            )
            * 1000,
            2,
        )

        if profiling is not None:
            profiling.update(
                {
                    "query_embedding_ms": (
                        query_embedding_ms
                    ),
                    "vector_conversion_ms": (
                        vector_conversion_ms
                    ),
                    "vector_database_ms": (
                        vector_database_ms
                    ),
                    "vector_postprocess_ms": (
                        vector_postprocess_ms
                    ),
                    "vector_semantic_total_ms": (
                        vector_semantic_total_ms
                    ),
                }
            )

        return {
            "ok": True,
            "message": (
                f"{len(resultados)} chunks encontrados. "
                f"Categorias priorizadas: {categorias_texto}."
            ),
            "resultados": resultados,
            "categorias_prioritarias": (
                categorias_prioritarias
            ),
            "limite_utilizado": limite_final,
            "total_candidatos": len(registros),
        }

    except Exception as exc:
        return {
            "ok": False,
            "message": (
                "Erro na busca semântica pgvector: "
                f"{exc}"
            ),
            "resultados": [],
        }


def buscar_chunks_textuais(
    pergunta: str,
    *,
    limite: int = 5,
    classificar_chunk: ChunkClassifier,
) -> dict:
    """
    Busca textual estruturada sobre chunks_embeddings_rag.

    Somente documentos ativos e com nome lógico participam
    do retrieval de produção.
    """
    pergunta = str(
        pergunta or ""
    ).strip()

    if not pergunta:
        return {
            "ok": False,
            "message": "Pergunta vazia.",
            "resultados": [],
        }

    if not callable(classificar_chunk):
        return {
            "ok": False,
            "message": (
                "Função de classificação "
                "de chunks inválida."
            ),
            "resultados": [],
        }

    termos = _extrair_termos_busca_textual(
        pergunta
    )

    if not termos:
        return {
            "ok": True,
            "message": (
                "Nenhum termo textual "
                "relevante identificado."
            ),
            "resultados": [],
            "limite_utilizado": 0,
            "total_candidatos": 0,
        }

    limite_final = _validar_limite(
        limite
    )

    limite_busca = max(
        limite_final * 4,
        10,
    )

    score_partes: list[str] = []
    where_partes: list[str] = []

    score_params: list[str] = []
    where_params: list[str] = []

    for termo in termos:
        pattern = f"%{termo}%"

        score_partes.append(
            """
            (
                CASE
                    WHEN LOWER(ce.texto)
                         LIKE %s
                    THEN 1.00
                    ELSE 0.00
                END
                +
                CASE
                    WHEN LOWER(
                        COALESCE(
                            du.nome_original,
                            ''
                        )
                    ) LIKE %s
                    THEN 0.35
                    ELSE 0.00
                END
                +
                CASE
                    WHEN LOWER(
                        COALESCE(
                            du.nome_logico,
                            ''
                        )
                    ) LIKE %s
                    THEN 0.50
                    ELSE 0.00
                END
            )
            """
        )

        score_params.extend(
            [
                pattern,
                pattern,
                pattern,
            ]
        )

        where_partes.append(
            """
            (
                LOWER(ce.texto) LIKE %s
                OR LOWER(
                    COALESCE(
                        du.nome_original,
                        ''
                    )
                ) LIKE %s
                OR LOWER(
                    COALESCE(
                        du.nome_logico,
                        ''
                    )
                ) LIKE %s
            )
            """
        )

        where_params.extend(
            [
                pattern,
                pattern,
                pattern,
            ]
        )

    score_sql = " + ".join(
        score_partes
    )

    where_sql = " OR ".join(
        where_partes
    )

    sql = f"""
        SELECT
            ce.id,
            ce.documento_id,
            ce.chunk_id,
            ce.documento_origem,
            ce.chunk_index,
            ce.texto,
            du.nome_logico AS documento_key,
            COALESCE(
                ce.metadata ->> 'document_title',
                du.nome_original,
                du.nome_logico,
                'Documento INNA'
            ) AS titulo,
            COALESCE(
                ce.documento_origem,
                du.caminho_upload,
                du.nome_salvo,
                du.nome_logico
            ) AS fonte,
            COALESCE(
                ce.metadata ->> 'area',
                du.origem,
                'conhecimento_inna'
            ) AS categoria_documento,
            COALESCE(
                ce.metadata ->> 'language',
                'pt-BR'
            ) AS idioma,
            ce.metadata,
            ce.modelo_embedding,
            ({score_sql}) AS score_textual
        FROM chunks_embeddings_rag ce
        JOIN documentos_upload_rag du
            ON du.id = ce.documento_id
        WHERE COALESCE(
            du.ativo,
            TRUE
        ) = TRUE
          AND NULLIF(
                BTRIM(
                    COALESCE(
                        du.nome_logico,
                        ''
                    )
                ),
                ''
              ) IS NOT NULL
          AND ({where_sql})
        ORDER BY
            score_textual DESC,
            ce.documento_id ASC,
            ce.chunk_index ASC
        LIMIT %s;
    """

    parametros = (
        score_params
        + where_params
        + [limite_busca]
    )

    try:
        with cursor_postgres(
            dict_cursor=True,
            commit_automatico=False,
        ) as cursor:
            cursor.execute(
                sql,
                tuple(parametros),
            )

            registros = cursor.fetchall()

        resultados: list[dict] = []

        categorias_prioritarias = (
            inferir_categorias_pergunta(
                pergunta
            )
        )

        for registro in registros:
            item = dict(
                registro
            )

            texto = (
                item.get("texto")
                or ""
            )

            categoria = (
                classificar_chunk(texto)
                or item.get(
                    "categoria_documento"
                )
                or "geral"
            )

            score_textual = float(
                item.get(
                    "score_textual"
                )
                or 0
            )

            prioridade_categoria = int(
                categoria
                in categorias_prioritarias
            )

            item.update({
                "chunk_text": texto,
                "categoria": categoria,
                "score": score_textual,
                "score_textual": (
                    score_textual
                ),
                "prioridade_categoria": (
                    prioridade_categoria
                ),
                "categorias_prioritarias": (
                    categorias_prioritarias
                ),
                "modo_busca": (
                    "rag_estruturado_3072_textual"
                ),
            })

            resultados.append(
                item
            )

        resultados = sorted(
            resultados,
            key=lambda item: (
                float(
                    item.get(
                        "score_textual"
                    )
                    or 0
                ),
                int(
                    item.get(
                        "prioridade_categoria"
                    )
                    or 0
                ),
            ),
            reverse=True,
        )[:limite_final]

        return {
            "ok": True,
            "message": (
                f"{len(resultados)} chunks "
                "textuais encontrados."
            ),
            "resultados": resultados,
            "limite_utilizado": limite_final,
            "total_candidatos": len(
                registros
            ),
        }

    except Exception as exc:
        return {
            "ok": False,
            "message": (
                "Erro na busca textual "
                f"estruturada: {exc}"
            ),
            "resultados": [],
        }


__all__ = [
    "inferir_categorias_pergunta",
    "buscar_chunks_semanticos",
    "buscar_chunks_textuais",
]
