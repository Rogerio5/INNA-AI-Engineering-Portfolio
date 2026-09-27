# Aplicacao da Semana 3 na INNA

## Classificacao

**VALIDADO**

## O que esta evidencia demonstra

A Semana 3 esta representada por um pipeline RAG avancado com Hybrid Retrieval, RRF, reranking, Sentence-Window, Auto-Merging, RAG Triad, DeepEval e benchmarks.

## Implementacao e arquitetura

- [src/rag_engine.py](../../../../src/rag_engine.py)
- [src/services/rag/auto_merging.py](../../../../src/services/rag/auto_merging.py)
- [src/evaluation/rag_triad.py](../../../../src/evaluation/rag_triad.py)

## Testes

- [tests/unit/test_auto_merging_retrieval.py](../../../../tests/unit/test_auto_merging_retrieval.py)
- [tests/evaluations/test_deepeval_metrics.py](../../../../tests/evaluations/test_deepeval_metrics.py)

## Relatorios, auditorias e evidencias

- [docs/audits/week3_sentence_window_production_decision.md](../../../../docs/audits/week3_sentence_window_production_decision.md)
- [reports/auto_merging_part3_live_validation_001.json](../../../../reports/auto_merging_part3_live_validation_001.json)

---

> Esta pagina diferencia conteudo estudado de implementacao comprovada no repositorio.
