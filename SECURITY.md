# Security

## Secrets

Nunca publique:

- .env
- API keys
- tokens
- senhas
- certificados privados
- connection strings com credenciais

Use .env.example somente para documentar nomes de variáveis.

## Dados

Utilize somente dados fictícios ou sintéticos.

## Integrações externas

Gemini, PostgreSQL, Neo4j, Phoenix e MCP devem receber configuração por variáveis de ambiente.

## Vulnerabilidades

Não publique credenciais ou detalhes sensíveis em issues públicas.