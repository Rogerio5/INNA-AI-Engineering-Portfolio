# Indice de Evidencias - Semana 4

| Evidencia | Classificacao |
|---|---|
| [Agentic RAG](01-agentic-rag.md) | APLICADO / VALIDADO |
| [Router Agents e Tool Calling](02-router-agents-e-tool-calling.md) | VALIDADO |
| [Pesquisa multi-documento](03-pesquisa-multidocumento.md) | VALIDADO |
| [RAG Triad](04-rag-triad.md) | APLICADO / VALIDADO |
| [RAGAS](05-ragas.md) | ESTUDADO / COMPATIBILIDADE |
| [DeepEval e Quality Gates](06-deepeval-quality-gates.md) | APLICADO / VALIDADO |
| [TruLens e observabilidade](07-trulens-e-observabilidade.md) | TruLens ESTUDADO; observabilidade APLICADA |
| [CI/CD e avaliacao](08-ci-cd-e-avaliacao.md) | VALIDADO |
| [Aplicacao na INNA](09-aplicacao-na-inna.md) | VALIDADO |

[Voltar para a Semana 4](../README.md)

<!-- WEEK4-FINAL-VALIDATED-2026-08-11 -->
## Fechamento tecnico validado

Status da Semana 4: **conteudo aplicado, integrado, testado e versionado**.

Evidencias finais:
- Agentic RAG e Tool Calling formal integrados ao fluxo da INNA.
- RAG Triad e DeepEval usados como validacao automatizada e quality gate.
- RAGAS integrado em ambiente isolado, com execucao real via Gemini.
- TruLens integrado em ambiente isolado para observabilidade e experimentacao OTEL.
- CI/CD validado no PR #38 com 5 checks aprovados, 0 falhas e 0 pendencias.
- Regressao completa final: **4291 passed, 3 skipped**.
- Merge do PR #38 na `main`: `82fd5f061420ad995450015f61d93cc8a66149ee`.
- Nenhum deploy foi executado durante este fechamento documental.

Principais commits:
- RAGAS: `c1ddd300f31309c0bb1f37f38b2d52a5e655a334`
- TruLens: `0b227182cbef84cb2544120e0fa78d2222657a09`
- Correcao CI cross-platform: `74a1764a6eaaefc6dd224b0b86674d10c954116c`

- ⚡ [LlamaIndex em Produção e Otimização](10-llamaindex-producao-e-otimizacao.md)
