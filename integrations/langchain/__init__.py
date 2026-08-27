"""
Semantica × LangChain Integration
=================================

First-class integration between the Semantica semantic intelligence stack and
the `LangChain <https://github.com/langchain-ai/langchain>`_ / LangGraph
ecosystem.

Public surface
--------------
SemanticaRetriever  — ``BaseRetriever`` with multi-hop GraphRAG (walks graph
                      edges from hybrid-search hits)
SemanticaVectorStore — ``VectorStore`` adapter over Semantica's hybrid search
                      (drop-in for RetrievalQA / LCEL chains)
SemanticaKGTool     — ``BaseTool`` for querying the context graph
SemanticaDecisionTool — ``BaseTool`` exposing the recorded decision log

Quick start
-----------
    pip install semantica[langchain]

    >>> from integrations.langchain import (
    ...     SemanticaRetriever,
    ...     SemanticaVectorStore,
    ...     SemanticaKGTool,
    ...     SemanticaDecisionTool,
    ... )

Compatibility
-------------
Requires ``langchain-core >= 0.3``. All classes degrade gracefully when
``langchain-core`` is not installed — they are still importable and carry the
full Semantica API, but cannot be bound to LangChain chains/agents.
"""

from .retriever import LANGCHAIN_AVAILABLE, SemanticaRetriever
from .tools import SemanticaDecisionTool, SemanticaKGTool
from .vectorstore import SemanticaVectorStore

__all__ = [
    "SemanticaRetriever",
    "SemanticaVectorStore",
    "SemanticaKGTool",
    "SemanticaDecisionTool",
    "LANGCHAIN_AVAILABLE",
]

__version__ = "0.1.0"
