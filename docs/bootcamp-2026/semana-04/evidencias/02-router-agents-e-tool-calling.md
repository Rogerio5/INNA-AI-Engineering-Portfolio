# Router Agents e Tool Calling

## Classificacao

**VALIDADO**

## O que esta evidencia demonstra

O projeto possui roteador no Agentic RAG e ferramentas formais para acesso ao RAG e a outras capacidades.

## Implementacao e arquitetura

- [src/agentic_rag/router.py](../../../../src/agentic_rag/router.py)
- [src/agent_tools/rag_tools.py](../../../../src/agent_tools/rag_tools.py)
- [src/agent_tools/catalog.py](../../../../src/agent_tools/catalog.py)
- [src/agent_tools/core/contracts.py](../../../../src/agent_tools/core/contracts.py)

## Testes

- [tests/unit/test_agentic_rag_phase2_router.py](../../../../tests/unit/test_agentic_rag_phase2_router.py)
- [tests/unit/simulacao/test_formal_rag_tool.py](../../../../tests/unit/simulacao/test_formal_rag_tool.py)

## Relatorios, auditorias e evidencias

- [docs/audits/week4_tool_calling_persistence_integration.md](../../../../docs/audits/week4_tool_calling_persistence_integration.md)

---

> Esta pagina diferencia conteudo estudado de implementacao comprovada no repositorio.
