"""
Tests for integrations/llamaindex — graceful degradation when llama-index-core
is absent, plus adapter behavior against a real ContextGraph.
"""

import unittest
from unittest.mock import MagicMock

from integrations.llamaindex import LLAMAINDEX_AVAILABLE, __version__
from integrations.llamaindex.graph_store import SemanticaPropertyGraphStore
from integrations.llamaindex.retriever import SemanticaRetriever
from integrations.llamaindex.tools import semantica_kg_tools
from semantica.context import ContextGraph


class TestModule(unittest.TestCase):
    def test_version_exists(self):
        self.assertRegex(__version__, r"^\d+\.\d+\.\d+$")

    def test_llamaindex_available_flag_is_bool(self):
        self.assertIsInstance(LLAMAINDEX_AVAILABLE, bool)


class TestPropertyGraphStore(unittest.TestCase):
    def setUp(self):
        self.graph = ContextGraph()
        self.store = SemanticaPropertyGraphStore(self.graph)

    def test_upsert_nodes_and_get(self):
        from types import SimpleNamespace

        self.store.upsert_nodes(
            [
                SimpleNamespace(name="n1", label="person", properties={"content": "Alice"}),
                SimpleNamespace(name="n2", label="person", properties={"content": "Bob"}),
            ]
        )
        # upsert_nodes should have added real nodes via add_node
        nodes = self.graph.find_nodes(limit=10)
        self.assertTrue(any(str(n.get("id")) == "n1" for n in nodes))

    def test_get_triplets_empty_graph(self):
        self.assertEqual(self.store.get_triplets(), [])

    def test_structured_query_returns_nodes(self):
        self.graph.add_node("q1", node_type="entity", content="query target")
        result = self.store.structured_query("MATCH (n) RETURN n")
        self.assertIsInstance(result, list)
        self.assertGreaterEqual(len(result), 1)


class TestRetriever(unittest.TestCase):
    def setUp(self):
        self.graph = ContextGraph()
        self.retriever = SemanticaRetriever(self.graph, top_k=5, hops=1)

    def test_retrieve_returns_scored_nodes(self):
        from types import SimpleNamespace

        self.graph.add_node("r1", node_type="entity", content="retrieval seed")
        result = self.retriever._retrieve(SimpleNamespace(query_str="seed"))
        # graceful: without llama-index-core, _retrieve builds scored objects
        self.assertIsInstance(result, list)
        self.assertGreaterEqual(len(result), 1)


class TestTools(unittest.TestCase):
    def setUp(self):
        self.graph = ContextGraph()

    def test_semantica_kg_tools_returns_list(self):
        tools = semantica_kg_tools(self.graph)
        self.assertIsInstance(tools, list)
        if LLAMAINDEX_AVAILABLE:
            self.assertGreaterEqual(len(tools), 1)
        else:
            self.assertEqual(tools, [])

    def test_graph_query_returns_json(self):
        from integrations.llamaindex.tools import _graph_query

        self.graph.add_node("t1", node_type="entity", content="tool target")
        out = _graph_query(self.graph, "target", limit=5)
        import json

        parsed = json.loads(out)
        self.assertIsInstance(parsed, list)
        self.assertGreaterEqual(len(parsed), 1)

    def test_record_decision_returns_json(self):
        from integrations.llamaindex.tools import _record_decision

        out = _record_decision(
            self.graph,
            category="test",
            scenario="unit test",
            reasoning="verify adapter",
            outcome="success",
            confidence=0.9,
        )
        import json

        parsed = json.loads(out)
        self.assertIn("decision_id", parsed)


if __name__ == "__main__":
    unittest.main()
