"""
Schemas do Context Engineering da INNA.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ContextMessage(BaseModel):
    role: str
    content: str

    original_characters: int = 0
    sanitized: bool = False


class ContextBudget(BaseModel):
    max_tokens: int = Field(default=4000, ge=256)
    reserved_output_tokens: int = Field(default=800, ge=0)

    available_input_tokens: int = Field(default=3200, ge=128)
    estimated_input_tokens: int = Field(default=0, ge=0)

    within_budget: bool = True
    utilization_percent: float = Field(
        default=0.0,
        ge=0,
    )


class PrivacyReport(BaseModel):
    sensitive_items_found: int = 0
    email_addresses_masked: int = 0
    phone_numbers_masked: int = 0
    cpf_numbers_masked: int = 0
    card_numbers_masked: int = 0


class ContextMetrics(BaseModel):
    history_messages_received: int = 0
    history_messages_selected: int = 0
    history_messages_removed: int = 0

    tool_results_received: int = 0
    tool_results_selected: int = 0

    sources_received: int = 0
    sources_selected: int = 0

    characters_before: int = 0
    characters_after: int = 0

    privacy: PrivacyReport = Field(
        default_factory=PrivacyReport
    )

    budget: ContextBudget = Field(
        default_factory=ContextBudget
    )


class BuiltAgentContext(BaseModel):
    current_message: str
    language: str = "pt"
    currency: str = "BRL"

    conversation_summary: str = ""

    selected_history: list[ContextMessage] = Field(
        default_factory=list
    )

    financial_profile: dict[str, Any] = Field(
        default_factory=dict
    )

    selected_tool_results: list[dict[str, Any]] = Field(
        default_factory=list
    )

    sources: list[str] = Field(
        default_factory=list
    )

    instructions: list[str] = Field(
        default_factory=list
    )

    metrics: ContextMetrics = Field(
        default_factory=ContextMetrics
    )


__all__ = [
    "ContextMessage",
    "ContextBudget",
    "PrivacyReport",
    "ContextMetrics",
    "BuiltAgentContext",
]
