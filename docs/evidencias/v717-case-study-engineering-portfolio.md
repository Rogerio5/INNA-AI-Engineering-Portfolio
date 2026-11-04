# INNA Financial Coach AI — Engineering Case Study V7.17

## Visao geral

Evolucao da observabilidade de uma aplicacao financeira
baseada em inteligencia artificial.

## Arquitetura demonstrada

- FastAPI
- Gemini / LLMs
- Retrieval-Augmented Generation (RAG)
- LangGraph
- OpenTelemetry
- Phoenix
- GitHub Actions
- Docker
- Render

## Engenharia de observabilidade

- Span dedicado para operacoes RAG
- Rastreamento opcional com estrategia fail-open
- Preservacao de erros reais da aplicacao
- Instrumentacao com atributos tecnicos limitados
- Testes automatizados de regressao e privacidade

## Resultados verificados

- 66 testes automatizados aprovados
- 2 checks GitHub Actions aprovados
- API e RAG responderam HTTP 200 em producao
- Span inna.rag.ask validado com exportador local em memoria
- Status, duracao e atributos sinteticos verificados

## Limitacoes

A exportacao especifica do span RAG para o Phoenix Cloud
ainda nao foi comprovada em producao.

O teste com exportador em memoria nao representa
homologacao da exportacao remota.

## Privacidade

Este estudo de caso apresenta somente informacoes
tecnicas resumidas e resultados de testes.

Nao inclui credenciais, prompts privados, dados
financeiros de usuarios nem codigo-fonte proprietario.