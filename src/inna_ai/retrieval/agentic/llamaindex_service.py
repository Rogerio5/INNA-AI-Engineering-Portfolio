"""Compatibilidade temporaria para o runtime LlamaIndex Agentic RAG.

Implementacao oficial:
inna_ai.retrieval.agentic.llamaindex_runtime
"""

import sys

from inna_ai.retrieval.agentic import llamaindex_runtime as _implementation

sys.modules[__name__] = _implementation
