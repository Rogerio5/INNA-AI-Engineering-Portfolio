# Handoffs entre Agentes

## Classificacao

**VALIDADO**

## O que esta evidencia demonstra

Handoffs sao tratados por contratos e coordenacao explicita, com testes de estado, grafo e roteamento.

## Implementacao e arquitetura

- [src/agents/handoff.py](../../../../src/agents/handoff.py)
- [src/agents/handoff_coordinator_node.py](../../../../src/agents/handoff_coordinator_node.py)
- [src/agents/graph.py](../../../../src/agents/graph.py)

## Testes

- [tests/unit/test_handoff_contract.py](../../../../tests/unit/test_handoff_contract.py)
- [tests/unit/test_handoff_graph_contract.py](../../../../tests/unit/test_handoff_graph_contract.py)
- [tests/unit/test_handoff_state.py](../../../../tests/unit/test_handoff_state.py)
- [tests/unit/test_handoff_coordinator_node.py](../../../../tests/unit/test_handoff_coordinator_node.py)

## Relatorios, auditorias e evidencias

- [docs/architecture/MULTI_AGENT_HANDOFFS.md](../../../../docs/architecture/MULTI_AGENT_HANDOFFS.md)
- [docs/audits/HANDOFF_IMPLEMENTATION_AUDIT.md](../../../../docs/audits/HANDOFF_IMPLEMENTATION_AUDIT.md)

---

> Esta pagina diferencia conteudo estudado de implementacao comprovada no repositorio.
