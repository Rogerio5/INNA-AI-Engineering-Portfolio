from __future__ import annotations


class HumanReviewServiceError(
    RuntimeError
):
    """
    Erro sanitizado da camada de aplicação
    responsável pelas revisões humanas.
    """


class HumanReviewValidationError(
    HumanReviewServiceError
):
    """
    Os dados recebidos para a revisão humana
    são inválidos.
    """


class HumanReviewNotFoundError(
    HumanReviewServiceError
):
    """
    A revisão humana solicitada não foi encontrada.
    """


class HumanReviewConflictError(
    HumanReviewServiceError
):
    """
    A revisão já foi processada ou sofreu uma
    alteração concorrente.
    """


class HumanReviewRepositoryError(
    HumanReviewServiceError
):
    """
    Erro sanitizado durante acesso ao PostgreSQL.
    """


class HumanReviewResumeError(
    HumanReviewServiceError
):
    """
    Não foi possível retomar a execução interrompida
    no LangGraph.
    """


__all__ = [
    "HumanReviewConflictError",
    "HumanReviewNotFoundError",
    "HumanReviewRepositoryError",
    "HumanReviewResumeError",
    "HumanReviewServiceError",
    "HumanReviewValidationError",
]
