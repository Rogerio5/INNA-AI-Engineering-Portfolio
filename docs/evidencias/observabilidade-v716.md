# INNA V7.16 — Evidência de Observabilidade

Data: 2026-11-03

## Escopo

Validação local de tracing com Phoenix desativado e
OpenTelemetry utilizando InMemorySpanExporter.

## Ambiente

- Python 3.12.1
- Pytest 9.1.1
- LangGraph 1.2.9
- Pydantic 2.13.4
- arize-phoenix-otel 0.16.1
- opentelemetry-api 1.45.0
- opentelemetry-sdk 1.45.0

## Resultados

| Verificação | Resultado |
|---|---|
| Pytest público | 15/15 PASS |
| Importações Phoenix | PASS |
| Phoenix desativado | PASS |
| Tracing de sucesso | PASS |
| Propagação de exceção | PASS |
| Spans em memória | 2 capturados |
| Status OK/ERROR | PASS |
| Duração da operação | PASS |
| Tipo técnico do erro | PASS |
| Privacidade básica | PASS |

## Limitações

- Não foi validada exportação remota ao Phoenix.
- Não foi realizada chamada real ao Gemini.
- Não foi validada persistência PostgreSQL.
- Os testes funcionais locais de tracing não foram
  adicionados à suíte Pytest versionada.
- O teste de privacidade verificou a ausência da
  mensagem fictícia nos atributos e de eventos
  de exceção dos spans capturados.

## Conclusão

A observabilidade local da INNA V7.16 foi validada
nos cenários descritos, sem habilitar exportação
remota de telemetria.
