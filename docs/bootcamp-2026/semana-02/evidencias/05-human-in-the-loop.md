# Human-in-the-Loop

## Classificacao

**VALIDADO**

## O que esta evidencia demonstra

A INNA possui fluxo de revisao humana, politicas e nos de interrupcao/retomada, alem de workflow E2E dedicado.

## Implementacao e arquitetura

- [src/agents/human_review_interrupt_node.py](../../../../src/agents/human_review_interrupt_node.py)
- [src/agents/human_review_policy.py](../../../../src/agents/human_review_policy.py)
- [src/agents/human_review_policy_node.py](../../../../src/agents/human_review_policy_node.py)
- [src/agents/graph.py](../../../../src/agents/graph.py)

## Relatorios, auditorias e evidencias

- [.github/workflows/hitl-e2e.yml](../../../../.github/workflows/hitl-e2e.yml)
- [scripts/preflight_human_review_e2e.py](../../../../scripts/preflight_human_review_e2e.py)
- [scripts/test_human_review_e2e_resume.py](../../../../scripts/test_human_review_e2e_resume.py)

---

> Esta pagina diferencia conteudo estudado de implementacao comprovada no repositorio.
