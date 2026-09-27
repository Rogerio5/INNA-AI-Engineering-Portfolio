# Week 3 — Sentence-Window Production Decision

## Status

**DECISION=APPROVED**

O Sentence-Window Retrieval foi aprovado tecnicamente para
**rollout controlado em produção**.

A decisão é baseada nos experimentos da Semana 3,
na validação ponta a ponta com cinco perguntas oficiais,
nos testes locais de integração e regressão e na
validação operacional definitiva realizada após merge,
deploy e smoke test real em produção.

---

## Configuração aprovada para produção

```env
INNA_RAG_SENTENCE_WINDOW_ENABLED=true
INNA_RAG_SENTENCE_WINDOW_SIZE=5
INNA_RAG_SENTENCE_WINDOW_CHUNK_RADIUS=1
INNA_RAG_SENTENCE_WINDOW_MAX_CHARACTERS=4000
INNA_RAG_SENTENCE_WINDOW_ALLOWED_DOCUMENT_KEYS=inna-edu-orcamento-002
INNA_RAG_TOP_K=2
```

### Interpretação

A configuração de produção utiliza:

- Sentence-Window habilitado;
- window size igual a 5;
- raio de chunks igual a 1;
- limite máximo de contexto expandido de 4000 caracteres;
- rollout seletivo inicialmente limitado ao documento
  `inna-edu-orcamento-002`;
- `TOP_K` global de produção igual a 2.

---

## Estratégia de rollout

O rollout inicial é controlado e seletivo.

Somente o documento:

```text
inna-edu-orcamento-002
```

está autorizado inicialmente para expansão por Sentence-Window.

Resultados pertencentes a documentos fora da allowlist continuam
utilizando o comportamento normal do RAG, sem expansão
Sentence-Window.

O runtime principal permanece no pipeline estruturado de 3072
dimensões e não utiliza fallback silencioso para o retrieval
legado de 768 dimensões.

---

## Resultado consolidado

```text
QUESTION_COUNT=5
COMPLETED_COUNT=5
FAILED_COUNT=0
QUESTIONS_APPROVED=5_DE_5
END_TO_END_5_QUESTIONS=APPROVED
RECOMMENDATION=promote_sentence_window
```

Na validação ponta a ponta, as cinco perguntas oficiais obtiveram:

```text
Answer Relevancy=1.0000
Faithfulness=1.0000
Contextual Relevancy=1.0000
```

Todos os Quality Gates consolidados foram aprovados.

---

## Configuração final do Sentence-Window

```text
WINDOW_SIZE=5
CHUNK_RADIUS=1
MAX_CHARACTERS=4000
ROLLOUT=CONTROLLED
INITIAL_DOCUMENT_KEY=inna-edu-orcamento-002
GLOBAL_TOP_K=2
```

---

## Pergunta 4

A execução definitiva da Pergunta 4 utilizou:

```text
TOP_K=1
ANSWER_RELEVANCY=1.0000
FAITHFULNESS=1.0000
CONTEXTUAL_RELEVANCY=1.0000
RAG_TRIAD_AVERAGE=1.0000
MAXIMUM_REGRESSION=0.0000
QUALITY_GATE_COMPLETE=True
QUALITY_GATE_PASSED=True
RECOMMENDATION=promote_sentence_window
```

O `TOP_K=1` pertence exclusivamente à execução experimental
definitiva da Pergunta 4.

Ele **não altera o `TOP_K` global de produção**.

A configuração global permanece:

```env
INNA_RAG_TOP_K=2
```

Execuções anteriores da Pergunta 4 utilizando `TOP_K=2`
são preservadas como evidência intermediária do processo
experimental.

---

## Resultado de desempenho consolidado

```text
MEDIAN_LATENCY_DELTA_MS=-322.0
AVERAGE_LATENCY_DELTA_MS=-895.6
AVERAGE_CONTEXT_CHARACTER_DELTA=-89.8
```

Os valores indicam que, na consolidação final, o Sentence-Window
não introduziu regressão de qualidade e apresentou redução média
de latência e de tamanho de contexto no conjunto avaliado.

Esses números representam deltas experimentais entre as
configurações comparadas durante a suíte de avaliação.

Eles devem ser analisados separadamente da latência absoluta
observada posteriormente em produção.

---

## Testes de integração do Sentence-Window

A restauração e integração inicial do Sentence-Window no RAG
foi validada localmente com:

```text
28 passed
WEEK3_TESTS=OK
WEEK3_RUFF=OK
WEEK3_DIFF_CHECK=OK
```

Foram verificados:

- feature flag habilitada;
- feature flag desabilitada;
- configuração de window size;
- configuração de chunk radius;
- limite máximo de caracteres;
- allowlist por documento;
- aplicação do Sentence-Window ao documento permitido;
- comportamento seguro para documentos não autorizados;
- preservação do RAG baseline quando a feature flag está desligada;
- integração com `search_knowledge_base_hybrid`;
- ausência de regressão nos testes do RAG Engine.

---

## Implementação técnica

Os principais componentes envolvidos no estado final da
arquitetura são:

```text
src/rag_engine.py
src/services/rag/retrieval.py
src/services/rag/retrieval_trace.py
src/services/rag/sentence_window.py
src/services/embeddings/gemini.py

tests/unit/test_sentence_window.py
tests/unit/test_rag_engine_sentence_window_integration.py
tests/unit/test_retrieval_trace_sentence_window.py
tests/unit/simulacao/test_structured_retrieval_3072.py
tests/unit/simulacao/test_rag_engine_hybrid_3072.py
tests/unit/simulacao/test_rag_engine_retrieval_trace_behavior.py
```

A implementação possui telemetria para registrar:

```text
document_key
sentence_window_applied
sentence_window_policy
sentence_window_skip_reason
sentence_window_document_key
```

O rollout seletivo utiliza a política:

```text
selective_allowlist
```

---

## Histórico técnico e commits principais

### Restauração do Sentence-Window

```text
5dc6b20
feat(rag): restore sentence-window retrieval with controlled rollout
```

### Finalização documental inicial da Semana 3

```text
38a3b5a
docs(rag): finalize Week 3 sentence-window production decision
```

### Telemetria de produção do Sentence-Window

```text
a257ee4
fix(rag): expose sentence-window production telemetry
```

### Retrieval estruturado 3072

```text
69052ef
feat(rag): add structured 3072 retrieval
```

### Runtime híbrido estruturado 3072 + RRF

```text
017fe8c
feat(rag): migrate hybrid runtime to structured 3072 retrieval
```

### Alinhamento do contrato de runtime 3072-only

```text
d1deb70
test(rag): align retrieval trace with 3072-only runtime
```

### Merge da migração estruturada

```text
eb38164
Merge pull request #28 from Rogerio5/feat/rag-3072-structured-migration
```

---

## Migração para Structured Retrieval 3072

Durante a validação operacional do Sentence-Window foi
identificado que o retrieval legado não preservava de forma
estruturada a identidade documental necessária para a allowlist.

O pipeline legado não entregava de forma confiável:

```text
documento_id
documento_key
```

Sem essa identidade, o Sentence-Window não conseguia confirmar
de maneira segura se o resultado pertencia ao documento
autorizado.

A arquitetura principal foi então migrada para o retrieval
estruturado com embeddings de 3072 dimensões.

O fluxo passou a operar como:

```text
Query
→ Gemini Query Embedding 3072
→ Structured Vector Retrieval
→ Structured Text Retrieval
→ Reciprocal Rank Fusion
→ Rerank
→ Native Document Identity
→ Controlled Allowlist
→ Sentence-Window
```

A identidade documental agora é obtida diretamente das estruturas
documentais utilizadas pelo retrieval.

---

## Hybrid Retrieval e Reciprocal Rank Fusion

O runtime principal utiliza duas fontes de recuperação:

```text
vetorial
textual
```

Os rankings produzidos pelas duas estratégias são combinados
por:

```text
Reciprocal Rank Fusion (RRF)
```

Após a fusão, o pipeline executa o rerank.

A sequência lógica é:

```text
Vector Retrieval
        +
Text Retrieval
        ↓
       RRF
        ↓
      Rerank
        ↓
 Sentence-Window
```

A telemetria preserva os sinais necessários para observar esse
pipeline em execução.

---

## Validação local do Structured Retrieval 3072

O teste real do retrieval estruturado confirmou embeddings de
consulta com 3072 dimensões e recuperação documental no Neon.

Foram confirmados:

```text
QUERY_EMBEDDING_DIMENSION=3072
QUERY_EMBEDDING_3072=OK
DOCUMENT_IDENTITY_3072=OK
ORCAMENTO_DOCUMENT_RETRIEVAL=OK
LIVE_STRUCTURED_RAG_3072=APPROVED
RAG_3072_LIVE_NEON_TEST=COMPLETE
```

O documento de orçamento foi recuperado com identidade nativa:

```text
DOCUMENT_ID=28
DOCUMENT_KEY=inna-edu-orcamento-002
```

---

## Validação local do Hybrid 3072 + RRF + Sentence-Window

Após a migração do runtime híbrido, foi executado teste real
contra Gemini e Neon.

Foram recuperados dois resultados do documento de orçamento:

```text
DOCUMENT_ID=28
DOCUMENT_KEY=inna-edu-orcamento-002
```

### Resultado 1

```text
SEARCH_ORIGINS=textual,vetorial
RRF_SCORE=0.03278688524590164
RRF_VECTOR_RANK=1
RRF_TEXT_RANK=1
RERANK_SCORE=0.822787
SENTENCE_WINDOW_APPLIED=True
```

### Resultado 2

```text
SEARCH_ORIGINS=textual,vetorial
RRF_SCORE=0.031754032258064516
RRF_VECTOR_RANK=2
RRF_TEXT_RANK=4
RERANK_SCORE=0.701754
SENTENCE_WINDOW_APPLIED=True
```

O runtime local final foi confirmado como:

```text
rag_hibrido_estruturado_3072_rrf_rerank_sentence_window
```

Resultado:

```text
STRUCTURED_3072_CONFIRMED=True
RRF_CONFIRMED=True
SEARCH_MODE_CONFIRMED=True
SENTENCE_WINDOW_CONFIRMED=True

HYBRID_3072_RRF_LIVE=APPROVED
SENTENCE_WINDOW_3072_LIVE=APPROVED
RAG_3072_RUNTIME_LIVE=APPROVED
```

---

## Regressão pós-migração

### Regressão ampliada do RAG

Após o alinhamento do runtime principal para o contrato
estruturado 3072-only:

```text
425 passed
RAG_3072_EXPANDED_REGRESSION=OK
```

Também foram confirmados:

```text
RAG_3072_COMPILE=OK
RAG_3072_RUFF=OK
```

### Regressão completa

A suíte completa foi executada com:

```text
4115 passed
3 skipped
FULL_REGRESSION=OK
RAG_3072_REGRESSION_GATE=APPROVED
```

Os três testes ignorados correspondem a testes live controlados
por variáveis de ambiente:

```text
RUN_HITL_E2E_TESTS
RUN_LIVE_EVALUATION_TESTS
RUN_LIVE_GEMINI_TESTS
```

Esses skips não representam falha funcional ou regressão.

---

## Runtime principal 3072-only

O runtime RAG principal não utiliza fallback silencioso para o
retrieval legado de 768 dimensões quando o Hybrid Structured
Retrieval não encontra resultados.

O contrato atual é:

```text
Hybrid Structured 3072 com resultados
→ continua o pipeline RAG

Hybrid Structured 3072 sem resultados
→ sem_resultados
```

O storage legado pode permanecer fisicamente existente, mas não
faz parte do fallback do retrieval principal.

Essa decisão mantém consistência dimensional e identidade
documental no runtime.

---

## Custo

A suíte experimental registrou:

```text
TOTAL_ESTIMATED_COST=0.0
```

Esse valor **não significa que o custo real da API foi zero**.

A telemetria utilizada durante a avaliação não possuía preços de
entrada e saída disponíveis para o modelo avaliador:

```text
MODEL_INPUT_PRICE=None
MODEL_OUTPUT_PRICE=None
COST_CALCULATION_AVAILABLE=False
REAL_BILLED_COST=NOT_VERIFIED
EQUIVALENT_ESTIMATED_COST=NOT_AVAILABLE
```

Portanto:

```text
REAL_API_COST_ZERO=NOT_CONFIRMED
REAL_BILLED_COST=NOT_VERIFIED
```

O valor `0.0` representa somente o acumulador técnico disponível
na suíte durante os experimentos.

A verificação do custo efetivamente cobrado deve ser realizada
diretamente na fonte de faturamento da API caso seja necessária
uma análise financeira definitiva.

---

## Privacidade das evidências

Os relatórios técnicos públicos devem preservar somente:

- métricas;
- hashes;
- configurações;
- resultados agregados;
- decisões técnicas;
- indicadores de qualidade;
- informações operacionais não sensíveis.

Não devem ser publicados:

- respostas completas dos usuários;
- contextos brutos recuperados pelo RAG;
- segredos;
- tokens;
- chaves de API;
- credenciais;
- conteúdo privado de usuários.

---

## Técnicas futuras

Auto-Merging Retrieval, Knowledge Graph e GraphRAG ficam
classificados como evoluções posteriores à Semana 3.

Esses itens não bloqueiam o fechamento técnico e operacional do
Sentence-Window.

---

## Validação operacional definitiva em produção

Após o merge da migração estruturada 3072 na branch principal e
o deploy da `inna-api`, foi executado o smoke test definitivo no
ambiente de produção através do endpoint:

```text
POST /rag/ask
```

A requisição foi concluída com sucesso:

```text
PRODUCTION_REQUEST=OK
```

O retrieval trace registrou:

```text
TRACE_ID=041e8ff9-5582-4db2-97dd-a9cecc1a64ea
SEARCH_MODE=rag_hibrido_estruturado_3072_rrf_rerank_sentence_window
TOP_K=2
RESULTS_TOTAL=2
TOTAL_TIME_MS=6261
```

### Resultado 1

```text
DOCUMENT_ID=28
DOCUMENT_KEY=inna-edu-orcamento-002
CHUNK_ID=inna-edu-orcamento-002::tuned-001::8fc6b0bf0dd9417f8c94

SEARCH_ORIGINS=textual,vetorial

HYBRID_SCORE=0.0327868852459016
RERANK_SCORE=0.822787

SENTENCE_WINDOW_APPLIED=True
SENTENCE_WINDOW_POLICY=selective_allowlist
SENTENCE_WINDOW_DOCUMENT_KEY=inna-edu-orcamento-002
```

### Resultado 2

```text
DOCUMENT_ID=28
DOCUMENT_KEY=inna-edu-orcamento-002
CHUNK_ID=inna-edu-orcamento-002::tuned-002::0d938ccf01407def4da6

SEARCH_ORIGINS=textual,vetorial

HYBRID_SCORE=0.0317540322580645
RERANK_SCORE=0.701754

SENTENCE_WINDOW_APPLIED=True
SENTENCE_WINDOW_POLICY=selective_allowlist
SENTENCE_WINDOW_DOCUMENT_KEY=inna-edu-orcamento-002
```

### Gates operacionais

```text
STRUCTURED_IDENTITY_3072=True
RRF_RERANK_TELEMETRY=True
SEARCH_MODE_3072_RRF=True
SENTENCE_WINDOW_PRODUCTION=True
TOP_K_PRODUCTION_2=True
```

Resultado operacional:

```text
RAG_3072_PRODUCTION=APPROVED
SENTENCE_WINDOW_PRODUCTION_CONFIRMED=True
WEEK3_PRODUCTION_VALIDATION=APPROVED
```

---

## TOP_K experimental versus TOP_K de produção

As duas configurações devem permanecer formalmente separadas:

```text
GLOBAL_TOP_K=2
QUESTION_4_FINAL_TOP_K=1
```

`QUESTION_4_FINAL_TOP_K=1` pertence exclusivamente ao experimento
definitivo da Pergunta 4.

Ele não altera:

```text
INNA_RAG_TOP_K=2
```

utilizado como configuração global do runtime de produção.

---

## Latência operacional observada

Na validação definitiva de produção foi registrado:

```text
TOTAL_TIME_MS=6261
```

Esse valor representa uma execução específica no ambiente de
produção.

Ele **não invalida a aprovação funcional** do pipeline.

Também não deve ser comparado diretamente com:

```text
MEDIAN_LATENCY_DELTA_MS=-322.0
AVERAGE_LATENCY_DELTA_MS=-895.6
```

porque esses números representam deltas experimentais entre
estratégias, enquanto `6261 ms` representa uma medição absoluta
de uma execução real de produção.

A latência de produção permanece como métrica operacional de
monitoramento.

Antes de uma decisão de otimização devem ser executadas múltiplas
medições para calcular:

- mínimo;
- média;
- mediana / p50;
- p95;
- máximo.

Quando necessário, a análise poderá separar os tempos de:

- geração do embedding da consulta;
- retrieval vetorial no Neon;
- retrieval textual;
- Reciprocal Rank Fusion;
- rerank;
- Sentence-Window;
- geração final da resposta.

---

## Estado final da Semana 3

```text
WEEK3_FINAL_DECISION=APPROVED

SENTENCE_WINDOW_PRODUCTION_APPROVED=True
SENTENCE_WINDOW_PRODUCTION_CONFIRMED=True
SENTENCE_WINDOW_ROLLOUT=CONTROLLED
SENTENCE_WINDOW_ENABLED=True

WINDOW_SIZE=5
CHUNK_RADIUS=1
MAX_CHARACTERS=4000
INITIAL_DOCUMENT_KEY=inna-edu-orcamento-002

GLOBAL_TOP_K=2
QUESTION_4_FINAL_TOP_K=1

QUALITY_GATE=5/5_APPROVED
FAILED_QUESTIONS=0
RECOMMENDATION=promote_sentence_window

RAG_STRUCTURED_3072=OPERATIONAL
RAG_3072_PRODUCTION=APPROVED
RRF=OPERATIONAL
RERANK=OPERATIONAL
DOCUMENT_IDENTITY=APPROVED

RAG_3072_EXPANDED_REGRESSION=425_PASSED
FULL_REGRESSION=4115_PASSED_3_SKIPPED

WEEK3_PRODUCTION_VALIDATION=APPROVED
WEEK3_COMPLETE=True

IMPLEMENTATION_COMMIT=5dc6b20
STRUCTURED_3072_COMMIT=69052ef
HYBRID_3072_COMMIT=017fe8c
RUNTIME_CONTRACT_COMMIT=d1deb70
PRODUCTION_MERGE_COMMIT=eb38164
```

---

## Encerramento operacional da Semana 3

Com a conclusão de:

- experimentos de Sentence-Window;
- cinco perguntas oficiais;
- RAG Triad;
- Quality Gates;
- validação ponta a ponta;
- migração para Structured Retrieval 3072;
- Hybrid Retrieval vetorial + textual;
- Reciprocal Rank Fusion;
- rerank;
- identidade documental nativa;
- rollout controlado;
- regressão ampliada;
- regressão completa;
- merge;
- deploy;
- smoke test real em produção;

a Semana 3 está tecnicamente e operacionalmente encerrada.

Estado definitivo:

```text
QUESTIONS_APPROVED=5_DE_5

RAG_TRIAD_ANSWER_RELEVANCY=1.0000
RAG_TRIAD_FAITHFULNESS=1.0000
RAG_TRIAD_CONTEXTUAL_RELEVANCY=1.0000

QUALITY_GATE=APPROVED
RECOMMENDATION=promote_sentence_window

RAG_3072=APPROVED
RRF=APPROVED
RERANK=APPROVED
DOCUMENT_IDENTITY=APPROVED
SENTENCE_WINDOW=APPROVED
CONTROLLED_ROLLOUT=APPROVED

GLOBAL_TOP_K=2
QUESTION_4_FINAL_TOP_K=1

RAG_3072_PRODUCTION=APPROVED
SENTENCE_WINDOW_PRODUCTION_CONFIRMED=True
WEEK3_PRODUCTION_VALIDATION=APPROVED

WEEK3_COMPLETE=True
```

Auto-Merging Retrieval, Knowledge Graph e GraphRAG permanecem no
roadmap pós-Semana 3 e não bloqueiam este encerramento.
