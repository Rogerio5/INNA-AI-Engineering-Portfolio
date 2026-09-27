# Aplicacao da Semana 2 na INNA

## Classificacao

**VALIDADO**

## O que esta evidencia demonstra

A Semana 2 esta representada por uma arquitetura multiagente real, com supervisao, roteamento, handoffs, HITL, persistencia e observabilidade.

## Implementacao e arquitetura

- [src/agents/supervisor.py](../../../../src/agents/supervisor.py)
- [src/agents/team_router.py](../../../../src/agents/team_router.py)
- [src/agents/handoff.py](../../../../src/agents/handoff.py)
- [src/agents/human_review_interrupt_node.py](../../../../src/agents/human_review_interrupt_node.py)

## Testes

- [tests/unit/test_langgraph_topology.py](../../../../tests/unit/test_langgraph_topology.py)
- [tests/unit/test_handoff_contract.py](../../../../tests/unit/test_handoff_contract.py)

## Relatorios, auditorias e evidencias

- [docs/architecture/HIERARCHICAL_AGENT_TEAMS.md](../../../../docs/architecture/HIERARCHICAL_AGENT_TEAMS.md)
- [docs/architecture/MULTI_AGENT_HANDOFFS.md](../../../../docs/architecture/MULTI_AGENT_HANDOFFS.md)

---

> Esta pagina diferencia conteudo estudado de implementacao comprovada no repositorio.
