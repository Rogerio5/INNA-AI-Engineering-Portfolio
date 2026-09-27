# RAG Triad

## Classificacao

**APLICADO / VALIDADO**

## O que esta evidencia demonstra

A INNA utiliza RAG Triad como contrato de qualidade para avaliar relevancia da resposta, fidelidade e relevancia contextual.

## Implementacao e arquitetura

- [src/evaluation/rag_triad.py](../../../../src/evaluation/rag_triad.py)

## Testes

- [tests/evaluations/test_deepeval_metrics.py](../../../../tests/evaluations/test_deepeval_metrics.py)

## Relatorios, auditorias e evidencias

- [reports/auto_merging_part3_live_validation_001.json](../../../../reports/auto_merging_part3_live_validation_001.json)
- [reports/auto_merging_phase527d_debt_live_revalidation_001.json](../../../../reports/auto_merging_phase527d_debt_live_revalidation_001.json)

---

> Esta pagina diferencia conteudo estudado de implementacao comprovada no repositorio.

<!-- WEEK4-FINAL-RAG-TRIAD-2026-08-11 -->
## Fechamento validado

Na INNA, o RAG Triad foi usado como estrutura de avaliacao para verificar a relacao entre pergunta, contexto recuperado e resposta final.

A avaliacao automatizada foi materializada principalmente com DeepEval e os eixos:
- relevancia da resposta;
- fidelidade/groundedness da resposta ao contexto;
- relevancia contextual.

No gate LIVE final do RAG com `top_k=2`, os casos canonicos avaliados atingiram aprovacao integral dos eixos configurados, sem reducao dos thresholds definidos.

O RAG Triad permanece como referencia conceitual de qualidade; DeepEval e o mecanismo principal de automacao/gate e RAGAS complementa a analise com metricas especializadas.
