# DeepEval e Quality Gates

## Classificacao

**APLICADO / VALIDADO**

## O que esta evidencia demonstra

DeepEval esta integrado a executores, metricas, testes e pipelines de avaliacao, com gates automatizados.

## Implementacao e arquitetura

- [src/evaluation/deepeval_metrics.py](../../../../src/evaluation/deepeval_metrics.py)
- [src/evaluation/deepeval_executors.py](../../../../src/evaluation/deepeval_executors.py)
- [src/evaluation/final_regression/runner.py](../../../../src/evaluation/final_regression/runner.py)

## Testes

- [tests/evaluations/test_deepeval_metrics.py](../../../../tests/evaluations/test_deepeval_metrics.py)
- [tests/evaluations/test_deepeval_executors.py](../../../../tests/evaluations/test_deepeval_executors.py)
- [tests/evaluations/test_deepeval_runner.py](../../../../tests/evaluations/test_deepeval_runner.py)

## Relatorios, auditorias e evidencias

- [.github/workflows/evaluation-ci.yml](../../../../.github/workflows/evaluation-ci.yml)

---

> Esta pagina diferencia conteudo estudado de implementacao comprovada no repositorio.

<!-- WEEK4-FINAL-DEEPEVAL-2026-08-11 -->
## Fechamento validado

DeepEval permanece como o **quality gate principal** da estrategia de avaliacao da INNA.

Metricas configuradas:
- `answer-relevancy`
- `faithfulness`
- `contextual-relevancy`

Thresholds mantidos:
- Answer Relevancy: `0.80`
- Faithfulness: `0.80`
- Contextual Relevancy: `0.75`

Os thresholds nao foram reduzidos para fazer o GraphRAG/RAG passar. O processo de melhoria atuou no retrieval, incluindo ajuste do `top_k` padrao para 2 apos auditoria de precisao.

No fechamento da Semana 4:
- testes direcionados de RAGAS/TruLens: aprovados;
- regressao completa: **4291 passed, 3 skipped**;
- CI do PR #38: **5 successful, 0 failing, 0 pending**.

Estrategia final:
- DeepEval: automacao e quality gates;
- RAGAS: metricas complementares detalhadas;
- TruLens: observabilidade e experimentacao.
