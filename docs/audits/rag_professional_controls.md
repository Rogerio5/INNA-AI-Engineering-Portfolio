# Auditoria profissional do RAG

| Controle | Situação |
|---|---|
| `hybrid_retrieval` | FOUND |
| `reranking` | FOUND |
| `vector_database` | FOUND |
| `document_metadata` | FOUND |
| `document_id` | FOUND |
| `chunk_id` | FOUND |
| `document_version` | FOUND |
| `content_checksum` | FOUND |
| `file_type_validation` | FOUND |
| `file_size_validation` | FOUND |
| `prompt_injection_defense` | FOUND |
| `retrieval_trace` | FOUND |
| `retrieval_scores` | FOUND |
| `source_citations` | FOUND |

## Controles implementados

### Segurança documental

- validação de extensão `.md` e `.txt`;
- limite de tamanho configurável;
- bloqueio de arquivos vazios;
- validação UTF-8;
- cálculo de SHA-256;
- detecção de padrões de prompt injection em português e inglês.

### Versionamento documental

- identificação por nome lógico;
- versão inicial e versões incrementais;
- rejeição de conteúdo duplicado por hash;
- vínculo entre documento raiz e versão anterior;
- migração retrocompatível da tabela de documentos.

### Rastreabilidade da recuperação

- `trace_id` por execução;
- modo de busca utilizado;
- duração da recuperação;
- quantidade de resultados;
- IDs de documento e chunk;
- origem vetorial e textual;
- score original, híbrido e de reranking;
- persistência opcional do trace no log RAG.

## Validação

A implementação foi validada por testes unitários, estruturais,
comportamentais, de compatibilidade e regressão completa.
