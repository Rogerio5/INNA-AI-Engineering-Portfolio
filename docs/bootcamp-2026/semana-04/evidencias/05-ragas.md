# RAGAS

## Classificacao

**ESTUDADO / COMPATIBILIDADE DE BENCHMARK**

## O que esta evidencia demonstra

A auditoria encontrou referencias a RAGAS em estruturas de benchmark/framework payloads, mas nao evidencia uma integracao RAGAS dedicada ao runtime principal.

## Implementacao e arquitetura

- [src/evaluation/agentic_benchmark/framework_payloads.py](../../../../src/evaluation/agentic_benchmark/framework_payloads.py)

## Testes

- [tests/evaluations/test_agentic_benchmark_framework_payloads.py](../../../../tests/evaluations/test_agentic_benchmark_framework_payloads.py)

## Observacao

RAGAS nao deve ser anunciado como framework operacional da INNA enquanto nao houver executor, metricas e Quality Gate dedicados.

---

> Esta pagina diferencia conteudo estudado de implementacao comprovada no repositorio.

<!-- WEEK4-FINAL-RAGAS-2026-08-11 -->
## Fechamento validado

O RAGAS deixou de ser apenas item de estudo/compatibilidade e passou a ter integracao real na INNA por meio de um bridge isolado.

Arquitetura validada:
- ambiente separado `.venv-ragas`;
- dependencias fixadas em `requirements-ragas.txt`;
- bridge principal em `src/evaluation/ragas_bridge.py`;
- runner isolado em `scripts/run_ragas_isolated_metric.py`;
- integracao com o payload real do benchmark agentic da INNA;
- execucao fora do runtime critico da aplicacao.

Resultados LIVE com Gemini:
- **Faithfulness = 1.0**
- **Context Precision = 0.9999999999**
- **Context Recall = 1.0**

Foram usados casos oficiais do dataset da INNA com resposta de referencia disponivel. A chave do modelo foi transmitida somente por ambiente para o subprocesso isolado e nao foi persistida em arquivo de configuracao ou saida de teste.

Apos o ajuste de CI, o resolver do Python isolado passou a suportar Windows (`Scripts/python.exe`) e Linux/POSIX (`bin/python`). O workflow de avaliacao cria `.venv-ragas` e instala `requirements-ragas.txt` antes dos testes deterministicos.

Commit principal: `c1ddd300f31309c0bb1f37f38b2d52a5e655a334`.

Correcao cross-platform/CI: `74a1764a6eaaefc6dd224b0b86674d10c954116c`.
