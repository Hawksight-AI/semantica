"""
Semantica × LangChain Integration
=============================

First-class integration between the Semantica semantic intelligence stack and
the `LangChain <https://github.com/langchain-ai/langchain>`_ framework.

Public surface
--------------
SemanticaRetriever    — GraphRAG-style retrieval over ContextGraph or AgentContext
SemanticaVectorStore  — Thin adapter over semantica.vector_store.VectorStore
SemanticaKGTool       — LangChain tools exposing Semantica KG features
SemanticaDecisionTool — LangChain tools exposing decision-intelligence features

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
Requires ``langchain-core >= 0.3``. All classes degrade gracefully when ``langchain-core``
is not installed.
"""

from .retriever import LANGCHAIN_AVAILABLE, SemanticaRetriever
from .vectorstore import SemanticaVectorStore
from .tools import SemanticaDecisionTool, SemanticaKGTool

__all__ = [
    "SemanticaRetriever",
    "SemanticaVectorStore",
    "SemanticaKGTool",
    "SemanticaDecisionTool",
    "LANGCHAIN_AVAILABLE",
]

__version__ = "0.1.0"
