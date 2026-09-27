# Bootcamp 2026 - Engenharia de IA aplicada a INNA

Esta area conecta os conteudos estudados no Bootcamp 2026 com implementacoes,
testes, auditorias, relatorios e Quality Gates reais da INNA Financial Coach AI.

## Navegacao

| Semana | Tema oficial | Situacao na INNA |
|---|---|---|
| [Semana 1](semana-01/) | Agentes, fundamentos | Conteudo concluido e fundamentos aplicados |
| [Semana 2](semana-02/) | Agentes, multi-agente e producao | Conteudo concluido e arquitetura aplicada |
| [Semana 3](semana-03/) | RAG, fundamentos e retrieval avancado | Conteudo principal aplicado e validado |
| [Semana 4](semana-04/) | RAG agentico e avaliacao | Agentic RAG e avaliacao aplicados; RAGAS/TruLens sem runtime dedicado |
| [Semana 5](semana-05/) | Aguardando conteudo oficial | Estrutura reservada |

## Como ler as evidencias

A documentacao utiliza as seguintes classificacoes:

- **ESTUDADO**: conteudo coberto pelo Bootcamp, sem afirmar implementacao no runtime;
- **EXPERIMENTADO**: prova de conceito, laboratorio ou compatibilidade tecnica;
- **APLICADO**: existe implementacao real no repositorio;
- **VALIDADO**: existe implementacao acompanhada por testes, metricas, auditorias ou Quality Gates;
- **ROADMAP**: ainda nao implementado como parte oficial do runtime.

## Principio

Os arquivos desta pasta nao duplicam o codigo da INNA.

Eles funcionam como uma camada de rastreabilidade:

`conteudo estudado -> competencia -> codigo -> teste -> relatorio -> decisao tecnica`

O codigo permanece em `src/`, os testes em `tests/`, os relatorios em `reports/`
e as auditorias nas pastas tecnicas originais.

---
