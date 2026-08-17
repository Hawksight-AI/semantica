"""
Tests for integrations/langchain — graceful degradation when langchain-core
is absent, plus adapter behavior with lightweight stubs.
"""

import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, "integrations")

from integrations.langchain import (  # noqa: E402
    LANGCHAIN_AVAILABLE,
    SemanticaDecisionTool,
    SemanticaKGTool,
    SemanticaRetriever,
    SemanticaVectorStore,
)


class TestImports(unittest.TestCase):
    def test_exports_exist(self):
        self.assertTrue(callable(SemanticaRetriever))
        self.assertTrue(callable(SemanticaVectorStore))
        self.assertTrue(callable(SemanticaKGTool))
        self.assertTrue(callable(SemanticaDecisionTool))

    def test_version(self):
        from integrations.langchain import __version__

        self.assertEqual(__version__, "0.1.0")


class TestGracefulDegradation(unittest.TestCase):
    """Without langchain-core, classes import but build() returns None.

    These tests only run when langchain-core is NOT installed.
    """

    @unittest.skipIf(LANGCHAIN_AVAILABLE, "langchain-core is installed")
    def test_tools_build_returns_none_without_langchain(self):
        graph = MagicMock()
        self.assertIsNone(SemanticaKGTool(graph).build())
        self.assertIsNone(SemanticaDecisionTool(graph).build())

    @unittest.skipIf(LANGCHAIN_AVAILABLE, "langchain-core is installed")
    def test_document_helper_raises_clear_error(self):
        from integrations.langchain.retriever import _get_document

        with self.assertRaises(RuntimeError) as ctx:
            _get_document(page_content="x")
        self.assertIn("langchain-core", str(ctx.exception))

    @unittest.skipIf(LANGCHAIN_AVAILABLE, "langchain-core is installed")
    def test_retriever_init_without_langchain(self):
        """Finding: init must not fail when langchain-core is absent."""
        from types import SimpleNamespace

        from integrations.langchain.retriever import SemanticaRetriever

        retriever = SemanticaRetriever(graph=SimpleNamespace(), hops=2)
        self.assertEqual(retriever.hops, 2)


class TestToolsWithLangchain(unittest.TestCase):
    """Adapter behavior when langchain-core IS available."""

    @unittest.skipUnless(LANGCHAIN_AVAILABLE, "langchain-core not installed")
    def test_kg_tool_builds_structured_tool(self):
        from semantica.context import ContextGraph

        graph = ContextGraph()
        graph.add_node(node_id="alice", node_type="person", content="Alice is a developer")
        tool = SemanticaKGTool(graph).build()
        self.assertIsNotNone(tool)
        self.assertEqual(tool.name, "semantica_query_graph")
        result = tool.invoke({"query": "Alice", "limit": 5})
        self.assertIn("Alice", result)

    @unittest.skipUnless(LANGCHAIN_AVAILABLE, "langchain-core not installed")
    def test_decision_tool_builds_structured_tool(self):
        from semantica.context import ContextGraph

        graph = ContextGraph()
        tool = SemanticaDecisionTool(graph).build()
        self.assertIsNotNone(tool)
        self.assertEqual(tool.name, "semantica_query_decisions")
        result = tool.invoke({"category": "test", "limit": 5})
        self.assertIsInstance(result, str)


class TestRetrieverBehavior(unittest.TestCase):
    def test_empty_seed_returns_empty(self):
        graph = MagicMock()
        graph.query.return_value = []
        retriever = SemanticaRetriever(graph=graph, top_k=5)
        self.assertEqual(retriever._seed_results("query"), [])
        # _get_relevant_documents needs langchain to build Documents; the
        # graph walk itself is testable via _seed_results.
        self.assertEqual(retriever.hops, 2)

    def test_seed_uses_hybrid_when_provided(self):
        graph = MagicMock()
        hybrid = MagicMock()
        hybrid.search.return_value = [{"node_id": "n1", "content": "c1", "score": 0.9}]
        retriever = SemanticaRetriever(graph=graph, hybrid=hybrid)
        results = retriever._seed_results("query")
        self.assertEqual(len(results), 1)
        hybrid.search.assert_called_once_with("query", k=10)

    def test_graph_fallback_when_hybrid_fails(self):
        graph = MagicMock()
        graph.query.return_value = [{"node_id": "n1", "content": "c1"}]
        hybrid = MagicMock()
        hybrid.search.side_effect = RuntimeError("down")
        retriever = SemanticaRetriever(graph=graph, hybrid=hybrid)
        results = retriever._seed_results("query")
        self.assertEqual(len(results), 1)
        graph.query.assert_called_once()


class TestVectorStoreBehavior(unittest.TestCase):
    def test_add_texts_delegates_to_vector_store(self):
        vs = MagicMock()
        vs.add_documents.return_value = ["id1"]
        hybrid = MagicMock()
        store = SemanticaVectorStore(hybrid=hybrid, vector_store=vs)
        ids = store.add_texts(["hello"])
        self.assertEqual(ids, ["id1"])
        vs.add_documents.assert_called_once()

    def test_add_texts_raises_without_vector_store(self):
        from types import SimpleNamespace

        # A real object without a vector_store attr (MagicMock auto-creates
        # every attr, so it can't simulate the missing store)
        hybrid = SimpleNamespace(vector_store=None)
        store = SemanticaVectorStore(hybrid=hybrid)
        with self.assertRaises(ValueError):
            store.add_texts(["hello"])

    def test_from_texts_requires_hybrid_kwarg(self):
        with self.assertRaises(ValueError):
            SemanticaVectorStore.from_texts(["hello"], embedding=None)


if __name__ == "__main__":
    unittest.main()
