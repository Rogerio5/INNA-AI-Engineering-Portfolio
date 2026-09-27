# CI/CD e Avaliacao

## Classificacao

**VALIDADO**

## O que esta evidencia demonstra

A avaliacao faz parte do GitHub Actions, com regressao deterministica, fixtures offline, Quality Gates e validacoes de seguranca.

## Implementacao e arquitetura

- [src/evaluation/final_regression/runner.py](../../../../src/evaluation/final_regression/runner.py)

## Relatorios, auditorias e evidencias

- [.github/workflows/evaluation-ci.yml](../../../../.github/workflows/evaluation-ci.yml)
- [.github/workflows/live-evaluation-e2e.yml](../../../../.github/workflows/live-evaluation-e2e.yml)
- [.github/workflows/security-compliance.yml](../../../../.github/workflows/security-compliance.yml)

---

> Esta pagina diferencia conteudo estudado de implementacao comprovada no repositorio.

<!-- WEEK4-FINAL-CICD-2026-08-11 -->
## Fechamento validado

A integracao de avaliacao foi validada tambem no GitHub Actions.

O primeiro CI do PR #38 identificou corretamente uma incompatibilidade de ambiente: os testes RAGAS procuravam apenas `.venv-ragas/Scripts/python.exe`, caminho de Windows, enquanto o runner do GitHub Actions executava Linux.

Correcao aplicada:
- resolver cross-platform para RAGAS;
- resolver cross-platform preventivo para TruLens;
- criacao de `.venv-ragas` no workflow `evaluation-ci.yml`;
- instalacao isolada de `requirements-ragas.txt`;
- manutencao de RAGAS/TruLens fora do `requirements.txt` principal.

Validacao final do PR #38:
- **5 checks successful**
- **0 failing**
- **0 pending**
- `INNA LLMOps Evaluation CI` aprovado apos a correcao.

Regressao local pre-merge:
- **4291 passed**
- **3 skipped**

Seguranca:
- Gitleaks do changeset: **0 leaks**
- nenhum secret impresso;
- sem force push;
- sem deploy.

Merge do PR #38:
`82fd5f061420ad995450015f61d93cc8a66149ee`.
