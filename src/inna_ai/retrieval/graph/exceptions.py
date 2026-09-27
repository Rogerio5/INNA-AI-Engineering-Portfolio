"""ExceÃ§Ãµes especÃ­ficas da infraestrutura do Knowledge Graph."""


class KnowledgeGraphConfigurationError(RuntimeError):
    """ConfiguraÃ§Ã£o invÃ¡lida ou incompleta do Knowledge Graph."""


class KnowledgeGraphConnectionError(RuntimeError):
    """Falha ao inicializar ou validar conexÃ£o com o banco de grafos."""


class KnowledgeGraphPersistenceError(RuntimeError):
    """Falha segura de persist??ncia ou leitura do Knowledge Graph."""
