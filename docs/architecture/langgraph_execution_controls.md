# Controles profissionais do LangGraph

## Objetivo

Definir limites operacionais, proteção contra ciclos e rastreabilidade das decisões do núcleo agentic da INNA.

## Limite global de execução

Toda execução do grafo utiliza:

    recursion_limit = 25

O limite é centralizado em:

    DEFAULT_LANGGRAPH_RECURSION_LIMIT

As execuções persistentes e não persistentes utilizam o mesmo controle.

## Helper seguro

As chamadas públicas não executam `graph.invoke()` diretamente.

Toda execução passa por:

    _invocar_grafo_seguro

Esse helper:

- envia a configuração centralizada;
- captura `GraphRecursionError`;
- converte a falha em `LangGraphExecutionLimitError`;
- não devolve estado parcial como resultado válido;
- preserva a exceção original como causa.

## Rotas permitidas

As rotas válidas são declaradas em:

    ALLOWED_AGENT_ROUTES

Rotas aceitas:

- financial_agent;
- education_agent;
- rag_agent;
- report_agent;
- fallback_agent.

Qualquer rota ausente ou desconhecida é convertida em:

    fallback_agent


## Prevenção de loops

A topologia atual do núcleo LangGraph é acíclica por projeto:

    START
    → context_builder
    → supervisor
    → agente especializado
    → END

Os agentes especializados não retornam ao supervisor e não possuem transições entre si.

Essa propriedade é validada por testes automatizados de topologia.

Além da garantia estrutural, toda execução utiliza:

    recursion_limit = 25

O limite de recursão funciona como proteção defensiva caso novas transições cíclicas sejam adicionadas futuramente.

Não foi criada uma detecção semântica baseada em repetição de rotas porque o grafo atual executa apenas uma decisão de roteamento por invocação.

## Roteamento auditável

Cada decisão do supervisor registra:

- `intent`;
- `next_node`;
- `route_source`;
- `routing_reason`;
- `confidence`;
- `fallback_used`;
- `gemini_called`.

O histórico estruturado fica em:

    route_history

## Compatibilidade do trace

O formato histórico do trace foi preservado:

    supervisor:<origem>:<intenção>

Exemplos:

    supervisor:rule:relatorio
    supervisor:gemini:consulta_rag
    supervisor:fallback:desconhecido

Os detalhes adicionais foram colocados em campos próprios para evitar quebra de compatibilidade.

## Retry

Não existe retry global do grafo.

Essa decisão evita repetição de operações que podem ter efeitos colaterais, como:

- persistência;
- ferramentas financeiras;
- geração de relatórios;
- chamadas externas;
- escrita de histórico.

Retries devem existir apenas nas integrações externas idempotentes e com orçamento controlado.

## Timeout

Os nós determinísticos não possuem timeout próprio.

As integrações externas possuem timeout específico, incluindo:

- Gemini;
- ferramentas RAG;
- ferramentas financeiras;
- PostgreSQL;
- APIs internas;
- readiness checks.

## Evidências

- auditoria dos controles profissionais;
- testes do limite global;
- teste de falha segura;
- testes das rotas permitidas;
- testes de fallback para rota inválida;
- testes do histórico estruturado;
- regressão do supervisor e do grafo.
