# INNA AI Engineering Portfolio

Portfólio público de Engenharia de Inteligência Artificial aplicado a um domínio demonstrativo de educação financeira.

O projeto reúne componentes de agentes de IA, LangGraph, Agentic RAG, Tool Calling, memória, Human-in-the-Loop, GraphRAG, avaliação, observabilidade e resiliência em uma arquitetura Python modular.

> Este repositório é um portfólio técnico. Ele não contém a lógica comercial completa da plataforma Sabino.AI nem dados reais de clientes.

## Objetivo

Demonstrar práticas de Engenharia de IA para aplicações com LLMs e sistemas multiagentes por meio de código executável e testável.

O domínio financeiro é utilizado apenas como cenário educacional.

## Principais capacidades

- LangGraph e arquitetura multiagente
- Agent Registry e Tool Registry
- Supervisor, roteamento e handoffs
- Context Engineering
- Memória e checkpoints
- Tool Calling governado
- Human-in-the-Loop
- RAG híbrido
- Agentic RAG
- LlamaIndex
- GraphRAG com Neo4j
- MCP e A2A
- Gemini / Google GenAI
- OpenTelemetry e Phoenix
- Avaliação de sistemas RAG/LLM
- Circuit Breaker, retry e backoff
- Testes estruturais e Quality Gates

## Estrutura

    src/inna_ai/
    |-- agents/
    |-- context/
    |-- demo/
    |-- evaluation/
    |-- governance/
    |-- integrations/
    |-- llm/
    |-- memory/
    |-- observability/
    |-- orchestration/
    |-- persistence/
    |-- resilience/
    |-- retrieval/
    -- tools/

Veja também:

- docs/ARCHITECTURE.md
- docs/PUBLIC_BOUNDARY.md
- SECURITY.md

## Fronteira pública

Esta versão:

- não contém dados de clientes;
- não envia e-mails reais;
- não envia mensagens Telegram reais;
- não contém credenciais;
- não possui billing, planos ou assinaturas;
- não contém o motor financeiro comercial completo da Sabino.AI;
- utiliza adapters demonstrativos para o domínio financeiro.

## Requisitos

- Python 3.11 ou 3.12
- PostgreSQL somente para funcionalidades que exigem persistência
- Neo4j somente quando GraphRAG estiver habilitado

## Instalação

Windows / PowerShell:

    py -3.12 -m venv .venv
    .\.venv\Scripts\Activate.ps1
    python -m pip install --upgrade pip
    python -m pip install -r requirements/runtime.txt
    python -m pip install -r requirements/dev.txt
    python -m pip install -e .

Para criar a configuração local:

    Copy-Item .env.example .env

Nunca publique o arquivo .env.

## Testes

    python -m pytest tests -q

A suíte estrutural pode ser executada sem Gemini real, PostgreSQL real ou Neo4j real.

## Segurança

Nenhuma chave ou credencial é necessária para os testes estruturais offline.

Consulte SECURITY.md.

## Aviso financeiro

Os recursos financeiros deste repositório existem exclusivamente para educação e demonstração técnica.

Não constituem recomendação financeira, de crédito ou investimento.