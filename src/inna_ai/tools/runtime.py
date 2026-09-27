"""
Runtime das ferramentas autorizadas da INNA.

Centraliza a construção do catálogo, das políticas
de permissão e do executor de ferramentas.
"""

from __future__ import annotations

from dataclasses import dataclass

from inna_ai.tools.catalog import criar_registro_ferramentas_inna
from inna_ai.tools.core import ToolCall, ToolExecutor, ToolPermissionPolicy, ToolRegistry, ToolResult


@dataclass(slots=True)
class InnaToolRuntime:
    """
    Runtime injetável e testável das ferramentas.

    Em aplicações web de maior escala poderá ser mantido
    durante o ciclo de vida da aplicação. Nesta primeira
    integração, cada chamada utiliza um runtime isolado.
    """

    registry: ToolRegistry
    executor: ToolExecutor

    @classmethod
    def create(
        cls,
        *,
        registry: ToolRegistry | None = None,
        permission_policy: (
            ToolPermissionPolicy | None
        ) = None,
        max_workers: int = 1,
    ) -> "InnaToolRuntime":
        resolved_registry = (
            registry
            or criar_registro_ferramentas_inna()
        )

        executor = ToolExecutor(
            registry=resolved_registry,
            permission_policy=permission_policy,
            max_workers=max_workers,
        )

        return cls(
            registry=resolved_registry,
            executor=executor,
        )

    def execute(
        self,
        call: ToolCall,
    ) -> ToolResult:
        return self.executor.execute(call)

    def close(
        self,
        *,
        wait: bool = False,
    ) -> None:
        self.executor.close(
            wait=wait,
        )

    def __enter__(
        self,
    ) -> "InnaToolRuntime":
        return self

    def __exit__(
        self,
        exc_type,
        exc_value,
        traceback,
    ) -> None:
        self.close(
            wait=False,
        )


def executar_ferramenta_inna(
    call: ToolCall,
    *,
    registry: ToolRegistry | None = None,
    permission_policy: (
        ToolPermissionPolicy | None
    ) = None,
) -> ToolResult:
    """
    Executa uma ferramenta usando um runtime isolado.

    Essa função facilita o uso pelo LangGraph e permite
    substituir o runtime nos testes sem acessar banco,
    rede ou Gemini.
    """
    runtime = InnaToolRuntime.create(
        registry=registry,
        permission_policy=permission_policy,
        max_workers=1,
    )

    try:
        return runtime.execute(call)
    finally:
        # Não aguarda uma tarefa que já excedeu o timeout.
        # Os clientes de banco e rede ainda devem possuir
        # seus próprios timeouts nativos.
        runtime.close(
            wait=False,
        )


__all__ = [
    "InnaToolRuntime",
    "executar_ferramenta_inna",
]
