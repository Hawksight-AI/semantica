"""
Unit tests for SemanticaKGTool and SemanticaDecisionTool.
"""

from __future__ import annotations

import json
import pytest

# Skip tests if langchain_core is not installed
pytest.importorskip("langchain_core")

import unittest
from unittest.mock import MagicMock, patch
from integrations.langchain import SemanticaKGTool, SemanticaDecisionTool


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------
def _fake_entity(name="Tesla", etype="ORG", conf=0.9):
    e = MagicMock()
    e.name = name
    e.type = etype
    e.confidence = conf
    return e


def _fake_relation(src="Tesla", rel="FOUNDED_BY", tgt="Elon Musk", conf=0.85):
    r = MagicMock()
    r.source = src
    r.type = rel
    r.target = tgt
    r.confidence = conf
    return r


class _FakeNER:
    def extract_entities(self, text):
        return [_fake_entity("Tesla"), _fake_entity("Elon Musk", "PERSON")]


class _FakeRelExtractor:
    def extract_relations(self, text, entities=None):
        return [_fake_relation()]


class _FakeReasoner:
    def infer_facts(self, facts, rules):
        result = MagicMock()
        result.inferred_facts = ["Human(EthicalAI)"]
        return result


class _FakeGraph:
    def __init__(self):
        self._node_store: dict = {}
        self._edge_store: list = []

    def find_nodes(self, node_type=None):
        nodes = list(self._node_store.values())
        if node_type:
            nodes = [n for n in nodes if n.get("node_type") == node_type]
        return nodes

    def add_node(self, node_id, node_type="Entity", content=None, **props):
        self._node_store[node_id] = {"node_id": node_id, "node_type": node_type}
        return True

    def add_edge(self, source_id, target_id, edge_type="related_to", **props):
        self._edge_store.append((source_id, target_id, edge_type))
        return True

    def get_neighbors(self, node_id, hops=1, relationship_types=None, min_weight=0.0):
        return [{"node_id": f"Neighbour_of_{node_id}", "node_type": "Entity"}]


class TestSemanticaKGTool(unittest.TestCase):

    def setUp(self) -> None:
        self.graph = _FakeGraph()
        self.tool = SemanticaKGTool(
            ner_extractor=_FakeNER(),
            relation_extractor=_FakeRelExtractor(),
            reasoner=_FakeReasoner(),
            context=self.graph,
        )

    def test_get_tools(self) -> None:
        tools = self.tool.get_tools()
        self.assertEqual(len(tools), 7)
        tool_names = [t.name for t in tools]
        self.assertIn("extract_entities", tool_names)
        self.assertIn("extract_relations", tool_names)
        self.assertIn("add_to_graph", tool_names)
        self.assertIn("query_graph", tool_names)
        self.assertIn("find_related", tool_names)
        self.assertIn("infer_facts", tool_names)
        self.assertIn("export_subgraph", tool_names)

    def test_extract_entities(self) -> None:
        res = json.loads(self.tool.extract_entities("some text"))
        self.assertIn("entities", res)
        self.assertEqual(res["count"], 2)

    def test_extract_relations(self) -> None:
        res = json.loads(self.tool.extract_relations("some text"))
        self.assertIn("relations", res)
        self.assertEqual(res["count"], 1)

    def test_add_to_graph(self) -> None:
        res = json.loads(self.tool.add_to_graph(
            entities=json.dumps([{"name": "Alice", "type": "PERSON"}]),
            relations=json.dumps([{"source": "Alice", "relation": "KNOWS", "target": "Bob"}]),
        ))
        self.assertEqual(res["nodes_added"], 1)
        self.assertEqual(res["edges_added"], 1)


class TestSemanticaDecisionTool(unittest.TestCase):

    def setUp(self) -> None:
        self.ctx = MagicMock()
        self.tool = SemanticaDecisionTool(context=self.ctx)

    def test_get_tools(self) -> None:
        tools = self.tool.get_tools()
        self.assertGreaterEqual(len(tools), 5)
        tool_names = [t.name for t in tools]
        self.assertIn("record_decision", tool_names)
        self.assertIn("find_precedents", tool_names)
        self.assertIn("trace_causal_chain", tool_names)
        self.assertIn("analyze_impact", tool_names)
        self.assertIn("get_decision_summary", tool_names)

    def test_record_decision(self) -> None:
        self.ctx.record_decision.return_value = "dec_123"
        res = json.loads(self.tool.record_decision(
            category="finance",
            scenario="loan application",
            reasoning="excellent score",
            outcome="approved",
        ))
        self.assertEqual(res["decision_id"], "dec_123")
        self.assertEqual(res["status"], "recorded")

    def test_check_policy(self) -> None:
        res = json.loads(self.tool.check_policy(
            decision_data=json.dumps({"confidence": 0.85}),
            policy_rules=json.dumps(["confidence >= 0.7"]),
        ))
        self.assertTrue(res["compliant"])


if __name__ == "__main__":
    unittest.main()
