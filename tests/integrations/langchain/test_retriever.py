"""
Unit tests for SemanticaRetriever.
"""

from __future__ import annotations

import pytest

# Skip tests if langchain_core is not installed
pytest.importorskip("langchain_core")

import unittest
from unittest.mock import MagicMock
from integrations.langchain import SemanticaRetriever
from langchain_core.documents import Document


class _FakeGraph:
    """Fake ContextGraph/AgentContext with retrieve and get_neighbors methods."""

    def __init__(self) -> None:
        self.nodes = {
            "node_1": {"id": "node_1", "type": "Framework", "content": "LangChain builds chains."},
            "node_2": {"id": "node_2", "type": "Framework", "content": "Semantica brings accountability."},
        }

    def retrieve(self, query: str, max_results: int = 5) -> list[dict]:
        # Return mock search results matching semantica retrieve structure
        return [
            {
                "id": "node_1",
                "content": "LangChain builds chains.",
                "score": 0.9,
                "metadata": {"node_id": "node_1"},
            },
            {
                "id": "node_2",
                "content": "Semantica brings accountability.",
                "score": 0.85,
                "metadata": {"node_id": "node_2"},
            },
        ]

    def find_node(self, node_id: str) -> dict | None:
        return self.nodes.get(node_id)

    def get_neighbors(self, node_id: str, hops: int = 2) -> list[dict]:
        if node_id == "node_1":
            return [
                {"id": "node_3", "type": "Concept", "content": "GraphRAG is powerful."},
            ]
        return []


class TestSemanticaRetriever(unittest.TestCase):

    def test_retriever_initialisation(self) -> None:
        graph = _FakeGraph()
        retriever = SemanticaRetriever(graph=graph, hops=2, top_k=5)
        self.assertIsNotNone(retriever)
        self.assertEqual(retriever.hops, 2)
        self.assertEqual(retriever.top_k, 5)

    def test_get_relevant_documents(self) -> None:
        graph = _FakeGraph()
        retriever = SemanticaRetriever(graph=graph, hops=1, top_k=2)

        # Invoke retrieval
        docs = retriever._get_relevant_documents("AI")

        # We expect:
        # - "node_1" (seed node)
        # - "node_3" (neighbor of node_1)
        # - "node_2" (seed node)
        self.assertGreaterEqual(len(docs), 2)

        # Verify page content mapping
        contents = [doc.page_content for doc in docs]
        self.assertIn("LangChain builds chains.", contents)
        self.assertIn("Semantica brings accountability.", contents)
        self.assertIn("GraphRAG is powerful.", contents)

        # Verify metadata mapping
        meta_ids = [doc.metadata.get("node_id") for doc in docs]
        self.assertIn("node_1", meta_ids)
        self.assertIn("node_2", meta_ids)
        self.assertIn("node_3", meta_ids)


if __name__ == "__main__":
    unittest.main()
