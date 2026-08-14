"""
Tests for SemanticaKGTool — knowledge graph CrewAI tool.

Runs with the crewai stubs installed by conftest, so ``CREWAI_AVAILABLE`` is
``True`` and the real Pydantic/BaseTool subclassing path is exercised.
"""

from __future__ import annotations

import asyncio
import json
import unittest
from unittest.mock import MagicMock

from integrations.crewai import SemanticaKGTool as ImportedSemanticaKGTool
from integrations.crewai.kg_tool import (
    CREWAI_AVAILABLE,
    CREWAI_IMPORT_ERROR,
    SemanticaKGTool,
    SemanticaKGToolInput,
)
from semantica.context import ContextGraph


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


class TestSemanticaKGToolInit(unittest.TestCase):

    def test_crewai_available_via_stub(self):
        self.assertTrue(CREWAI_AVAILABLE)
        self.assertIsNone(CREWAI_IMPORT_ERROR)

    def test_is_base_tool_subclass(self):
        from crewai.tools import BaseTool

        self.assertTrue(issubclass(SemanticaKGTool, BaseTool))

    def test_exposed_from_package_init(self):
        self.assertIs(ImportedSemanticaKGTool, SemanticaKGTool)

    def test_creates_with_explicit_graph(self):
        graph = ContextGraph()
        tool = SemanticaKGTool(graph=graph)
        self.assertIs(tool.graph, graph)

    def test_creates_fresh_graph_when_none(self):
        tool = SemanticaKGTool(
            ner_extractor=_FakeNER(), relation_extractor=_FakeRelExtractor()
        )
        self.assertIsNotNone(tool.graph)
        self.assertIsInstance(tool.graph, ContextGraph)

    def test_default_metadata(self):
        tool = SemanticaKGTool(
            ner_extractor=_FakeNER(), relation_extractor=_FakeRelExtractor()
        )
        self.assertEqual(tool.name, "semantica_knowledge_graph")
        self.assertTrue(tool.description)
        self.assertEqual(tool.args_schema, SemanticaKGToolInput)

    def test_input_schema_validates(self):
        inp = SemanticaKGToolInput(action="query_graph", query="privacy", hops=2)
        self.assertEqual(inp.hops, 2)
        with self.assertRaises(Exception):
            SemanticaKGToolInput(action="bogus")

    def test_custom_kwargs_forwarded(self):
        tool = SemanticaKGTool(
            ner_extractor=_FakeNER(),
            relation_extractor=_FakeRelExtractor(),
            result_as_answer=True,
        )
        self.assertTrue(tool.result_as_answer)


class TestSemanticaKGToolActions(unittest.TestCase):

    def setUp(self):
        self.graph = ContextGraph()
        self.tool = SemanticaKGTool(
            graph=self.graph,
            ner_extractor=_FakeNER(),
            relation_extractor=_FakeRelExtractor(),
        )

    def test_extract_entities(self):
        result = json.loads(
            self.tool._run(
                action="extract_entities", text="Tesla was founded by Elon Musk"
            )
        )
        self.assertEqual(result["count"], 2)
        self.assertEqual(result["entities"][0]["name"], "Tesla")
        self.assertEqual(result["entities"][0]["type"], "ORG")

    def test_extract_relations(self):
        result = json.loads(
            self.tool._run(
                action="extract_relations", text="Tesla was founded by Elon Musk"
            )
        )
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["relations"][0]["source"], "Tesla")
        self.assertEqual(result["relations"][0]["target"], "Elon Musk")

    def test_add_to_graph_populates_graph(self):
        result = json.loads(
            self.tool._run(action="add_to_graph", text="Tesla was founded by Elon Musk")
        )
        self.assertGreaterEqual(result["nodes_added"], 2)
        self.assertGreaterEqual(result["edges_added"], 1)
        nodes = self.graph.find_nodes()
        node_ids = {n["id"] for n in nodes}
        self.assertIn("Tesla", node_ids)
        self.assertIn("Elon Musk", node_ids)

    def test_add_to_graph_is_idempotent(self):
        self.tool._run(action="add_to_graph", text="Tesla was founded by Elon Musk")
        second = json.loads(
            self.tool._run(action="add_to_graph", text="Tesla was founded by Elon Musk")
        )
        self.assertEqual(second["nodes_added"], 0)
        self.assertEqual(second["edges_added"], 0)

    def test_query_graph_finds_matching_node(self):
        self.graph.add_node(
            node_id="privacy", node_type="policy", content="privacy policy doc"
        )
        result = json.loads(self.tool._run(action="query_graph", query="privacy"))
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["results"][0]["id"], "privacy")

    def test_query_graph_no_match(self):
        result = json.loads(
            self.tool._run(action="query_graph", query="nothing-matches")
        )
        self.assertEqual(result["count"], 0)
        self.assertEqual(result["results"], [])

    def test_find_related_multi_hop(self):
        self.graph.add_node(node_id="A", node_type="concept")
        self.graph.add_node(node_id="B", node_type="concept")
        self.graph.add_node(node_id="C", node_type="concept")
        self.graph.add_edge(source_id="A", target_id="B", edge_type="related_to")
        self.graph.add_edge(source_id="B", target_id="C", edge_type="related_to")
        result = json.loads(self.tool._run(action="find_related", entity="A", hops=2))
        self.assertEqual(result["count"], 2)
        self.assertIn("B", result["related"])
        self.assertIn("C", result["related"])

    def test_find_related_unknown_entity(self):
        result = json.loads(
            self.tool._run(action="find_related", entity="Ghost", hops=1)
        )
        self.assertEqual(result["count"], 0)
        self.assertEqual(result["related"], [])

    def test_unknown_action_returns_error(self):
        result = json.loads(self.tool._run(action="do_something_else"))
        self.assertIn("error", result)
        self.assertIn("do_something_else", result["error"])

    def test_extract_entities_empty_text_is_graceful(self):
        result = json.loads(self.tool._run(action="extract_entities", text=""))
        self.assertIn("entities", result)


class TestSemanticaKGToolCrewAIEntrypoints(unittest.TestCase):

    def setUp(self):
        self.tool = SemanticaKGTool(
            graph=ContextGraph(),
            ner_extractor=_FakeNER(),
            relation_extractor=_FakeRelExtractor(),
        )

    def test_run_delegates_to_run(self):
        result = json.loads(
            self.tool.run(action="extract_entities", text="Tesla led by Elon Musk")
        )
        self.assertEqual(result["count"], 2)

    def test_arun_async(self):
        async def _call():
            return await self.tool.arun(action="query_graph", query="x")

        result = json.loads(asyncio.run(_call()))
        self.assertIn("results", result)

    def test_run_returns_string(self):
        out = self.tool.run(action="extract_entities", text="hello world")
        self.assertIsInstance(out, str)


if __name__ == "__main__":
    unittest.main()
