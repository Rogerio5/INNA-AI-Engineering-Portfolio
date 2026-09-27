# Architecture

## Visão geral

O INNA AI Engineering Portfolio separa agentes, orquestração, retrieval, ferramentas, memória, governança, avaliação e observabilidade.

## Agents

A camada agents contém:

- Agent Registry
- roteamento
- supervisor
- handoffs
- task completion
- identidades operacionais

## Orchestration

Responsável por:

- estado do fluxo;
- contratos;
- LangGraph;
- gateways;
- ReAct;
- fallback.

## Tools

O Tool Registry mantém contratos explícitos para:

- schemas de entrada;
- schemas de saída;
- handlers;
- permissões;
- timeout;
- propriedades de segurança.

## Retrieval

A camada retrieval inclui:

- Hybrid RAG
- Agentic RAG
- embeddings
- GraphRAG
- armazenamento vetorial

## Governance

Inclui:

- Human-in-the-Loop
- políticas de revisão
- Blackboard
- execution governance

## Memory e Context Engineering

Responsáveis por histórico, resumo, seleção de contexto, orçamento de tokens e privacidade.

## Evaluation

Contém contratos e integrações para avaliação de sistemas RAG e LLM.

## Observability

Inclui OpenTelemetry, Phoenix e tracing do LangGraph.

## Resilience

Inclui retry, backoff, circuit breaker e deadlines.

## Integrações

O projeto possui interfaces para MCP e A2A.

## Public Demo

O domínio financeiro é exclusivamente educacional e demonstrativo.