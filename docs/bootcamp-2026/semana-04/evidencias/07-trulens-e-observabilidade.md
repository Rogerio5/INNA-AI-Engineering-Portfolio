# TruLens e Observabilidade

## Classificacao

**TRULENS: ESTUDADO / OBSERVABILIDADE: APLICADA**

## O que esta evidencia demonstra

A auditoria encontrou referencias a TruLens em payloads de benchmark, mas nao um runtime dedicado. Observabilidade, por outro lado, possui implementacoes e testes proprios na INNA.

## Implementacao e arquitetura

- [src/evaluation/agentic_benchmark/framework_payloads.py](../../../../src/evaluation/agentic_benchmark/framework_payloads.py)

## Testes

- [tests/evaluations/test_agentic_benchmark_framework_payloads.py](../../../../tests/evaluations/test_agentic_benchmark_framework_payloads.py)
- [tests/unit/simulacao/test_phoenix_langgraph_tracing.py](../../../../tests/unit/simulacao/test_phoenix_langgraph_tracing.py)

## Observacao

TruLens permanece classificado como estudado/compatibilidade de benchmark, nao como ferramenta operacional ativa.

---

> Esta pagina diferencia conteudo estudado de implementacao comprovada no repositorio.

<!-- WEEK4-FINAL-TRULENS-2026-08-11 -->
## Fechamento validado

O TruLens deixou de ser apenas item de estudo/compatibilidade e passou a possuir integracao real e isolada na INNA para observabilidade e experimentacao.

Arquitetura validada:
- ambiente separado `.venv-trulens`;
- dependencias fixadas em `requirements-trulens.txt`;
- bridge em `src/evaluation/trulens_bridge.py`;
- runner em `scripts/run_trulens_isolated_record.py`;
- persistencia temporaria em SQLite;
- execucao offline, sem inserir TruLens no runtime principal da INNA.

Instrumentacao OTEL real validada:
- `record_root`
- `retrieval`
- `generation`

Resultado do smoke real:
- **3 eventos persistidos**
- `force_flush=True`
- **0 network attempts**
- cleanup do SQLite validado no Windows apos encerramento do subprocesso.

O top-level instrumentado nao forca explicitamente `RECORD_ROOT`; o `TruApp` cria a raiz e os atributos de input/output sao anexados ao fluxo, preservando a semantica correta do TruLens 2.12.0.

O resolver do ambiente isolado suporta Windows (`Scripts/python.exe`) e Linux/POSIX (`bin/python`).

Phoenix permaneceu inalterado e nenhum export Phoenix foi executado nesta integracao, evitando duplicacao de telemetria em producao.

Commit principal: `0b227182cbef84cb2544120e0fa78d2222657a09`.
