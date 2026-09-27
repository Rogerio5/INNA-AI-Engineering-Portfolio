# RRF, Reranking e Grounding

## Classificacao

**VALIDADO**

## O que esta evidencia demonstra

A INNA aplica Reciprocal Rank Fusion e reranking no pipeline hibrido. A avaliacao de grounding/faithfulness faz parte dos Quality Gates.

## Implementacao e arquitetura

- [src/rag_engine.py](../../../../src/rag_engine.py)

## Testes

- [tests/unit/test_rag_rerank_relevance_gate.py](../../../../tests/unit/test_rag_rerank_relevance_gate.py)

## Relatorios, auditorias e evidencias

- [docs/reranking_inna.md](../../../../docs/reranking_inna.md)
- [reports/auto_merging_phase527d_debt_live_revalidation_001.json](../../../../reports/auto_merging_phase527d_debt_live_revalidation_001.json)

---

> Esta pagina diferencia conteudo estudado de implementacao comprovada no repositorio.
