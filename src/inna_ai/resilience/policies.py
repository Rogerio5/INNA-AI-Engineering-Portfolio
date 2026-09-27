from __future__ import annotations

from inna_ai.resilience.contracts import OperationKind, ResiliencePolicy

GEMINI_EMBEDDING_POLICY = ResiliencePolicy(
    name="gemini.embedding",
    operation_kind=OperationKind.READ_ONLY,
    max_attempts=3,
    base_delay_seconds=0.25,
    max_delay_seconds=2.0,
    jitter_ratio=0.20,
    circuit_failure_threshold=5,
    circuit_recovery_seconds=30.0,
)


GEMINI_GENERATION_POLICY = ResiliencePolicy(
    name="gemini.generate_content",
    operation_kind=OperationKind.READ_ONLY,
    max_attempts=2,
    base_delay_seconds=0.50,
    max_delay_seconds=2.0,
    jitter_ratio=0.20,
    circuit_failure_threshold=5,
    circuit_recovery_seconds=30.0,
)


GEMINI_TEXT_GENERATION_POLICY = ResiliencePolicy(
    name="gemini.generate.text_service",
    operation_kind=OperationKind.READ_ONLY,
    max_attempts=2,
    base_delay_seconds=0.50,
    max_delay_seconds=2.0,
    jitter_ratio=0.20,
    circuit_failure_threshold=5,
    circuit_recovery_seconds=30.0,
)


SUPERVISOR_GENERATION_POLICY = ResiliencePolicy(
    name="gemini.generate.supervisor",
    operation_kind=OperationKind.READ_ONLY,
    max_attempts=2,
    base_delay_seconds=0.50,
    max_delay_seconds=2.0,
    jitter_ratio=0.20,
    circuit_failure_threshold=5,
    circuit_recovery_seconds=30.0,
)


AGENTIC_RAG_PLANNER_POLICY = ResiliencePolicy(
    name="rag.agentic.planner",
    operation_kind=OperationKind.READ_ONLY,
    max_attempts=2,
    base_delay_seconds=0.50,
    max_delay_seconds=1.50,
    jitter_ratio=0.20,
    circuit_failure_threshold=4,
    circuit_recovery_seconds=20.0,
)


RAG_QUERY_POLICY = ResiliencePolicy(
    name="rag.query",
    operation_kind=OperationKind.READ_ONLY,
    max_attempts=2,
    base_delay_seconds=0.25,
    max_delay_seconds=1.5,
    jitter_ratio=0.20,
    circuit_failure_threshold=4,
    circuit_recovery_seconds=20.0,
)


LLAMAINDEX_AGENTIC_RAG_POLICY = ResiliencePolicy(
    name="rag.llamaindex_agentic",
    operation_kind=OperationKind.READ_ONLY,
    max_attempts=2,
    base_delay_seconds=0.25,
    max_delay_seconds=1.5,
    jitter_ratio=0.20,
    circuit_failure_threshold=4,
    circuit_recovery_seconds=20.0,
)


__all__ = [
    "GEMINI_EMBEDDING_POLICY",
    "GEMINI_GENERATION_POLICY",
    "GEMINI_TEXT_GENERATION_POLICY",
    "AGENTIC_RAG_PLANNER_POLICY",
    "SUPERVISOR_GENERATION_POLICY",
    "LLAMAINDEX_AGENTIC_RAG_POLICY",
    "RAG_QUERY_POLICY",
]
