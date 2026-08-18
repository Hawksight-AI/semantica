"""
Tests for AgnoKGToolkit — knowledge graph Agno Toolkit.
"""

from __future__ import annotations

import json
import unittest
from unittest.mock import MagicMock, patch


from integrations.agno.kg_toolkit import AgnoKGToolkit  # noqa: E402


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
    """Fake ContextGraph whose signatures match the real ContextGraph API."""

    def __init__(self):
        self._node_store: dict = {}   # node_id -> {"node_id": ..., "node_type": ...}
        self._edge_store: list = []

    # ContextGraph.find_nodes(node_type=None) -> List[Dict]
    def find_nodes(self, node_type=None):
        nodes = list(self._node_store.values())
        if node_type:
            nodes = [n for n in nodes if n.get("node_type") == node_type]
        return nodes

    # ContextGraph.add_node(node_id, node_type, content=None, **props) -> bool
    def add_node(self, node_id, node_type="Entity", content=None, **props):
        self._node_store[node_id] = {"node_id": node_id, "node_type": node_type}
        return True

    # ContextGraph.add_edge(source_id, target_id, edge_type, **props) -> bool
    def add_edge(self, source_id, target_id, edge_type="related_to", **props):
        self._edge_store.append((source_id, target_id, edge_type))
        return True

    # ContextGraph.get_neighbors(node_id, hops=1, ...) -> List[Dict]
    def get_neighbors(self, node_id, hops=1, relationship_types=None, min_weight=0.0):
        return [{"node_id": f"Neighbour_of_{node_id}", "node_type": "Entity"}]


class TestAgnoKGToolkitInit(unittest.TestCase):

    def test_creates_with_defaults(self):
        kit = AgnoKGToolkit()
        self.assertIsNotNone(kit)

    def test_creates_with_custom_components(self):
        kit = AgnoKGToolkit(
            ner_extractor=_FakeNER(),
            relation_extractor=_FakeRelExtractor(),
            reasoner=_FakeReasoner(),
        )
        self.assertIsNotNone(kit)

    def test_tools_registered(self):
        kit = AgnoKGToolkit()
        self.assertEqual(len(kit._tools), 7)
        self.assertEqual(len(kit._tools), len(set(kit._tools)))

    def test_registration_invoked(self):
        with patch.object(AgnoKGToolkit, "register") as mock_register:
            AgnoKGToolkit()
            self.assertEqual(mock_register.call_count, 7)

    def test_registration_failure_propagates(self):
        with patch.object(AgnoKGToolkit, "register", side_effect=RuntimeError("Registration failed")):
            with self.assertRaises(RuntimeError):
                AgnoKGToolkit()

    def test_graceful_degradation_when_agno_unavailable(self):
        with patch("integrations.agno.kg_toolkit.AGNO_AVAILABLE", False):
            with patch.object(AgnoKGToolkit, "register") as mock_register:
                kit = AgnoKGToolkit()
                mock_register.assert_not_called()
                self.assertEqual(len(kit._tools), 7)
                self.assertEqual(len(kit._tools), len(set(kit._tools)))

    def test_no_duplicate_tools(self):
        kit = AgnoKGToolkit()
        self.assertEqual(len(kit._tools), len(set(kit._tools)))
        self.assertEqual(len(kit._tools), 7)

    def test_context_graph_attached(self):
        ctx = MagicMock()
        ctx.knowledge_graph = _FakeGraph()
        kit = AgnoKGToolkit(context=ctx)
        self.assertIs(kit._graph, ctx.knowledge_graph)


class TestExtractEntities(unittest.TestCase):

    def setUp(self):
        self.kit = AgnoKGToolkit(
            ner_extractor=_FakeNER(),
            relation_extractor=_FakeRelExtractor(),
            reasoner=_FakeReasoner(),
        )

    def test_returns_json(self):
        result = json.loads(self.kit.extract_entities("Tesla was founded by Elon Musk."))
        self.assertIn("entities", result)
        self.assertIn("count", result)

    def test_entity_shape(self):
        result = json.loads(self.kit.extract_entities("some text"))
        for ent in result["entities"]:
            self.assertIn("name", ent)
            self.assertIn("type", ent)
            self.assertIn("confidence", ent)

    def test_count_matches_entities(self):
        result = json.loads(self.kit.extract_entities("text"))
        self.assertEqual(result["count"], len(result["entities"]))

    def test_handles_ner_failure(self):
        bad_ner = MagicMock()
        bad_ner.extract_entities.side_effect = RuntimeError("NER crashed")
        kit = AgnoKGToolkit(
            ner_extractor=bad_ner,
            relation_extractor=_FakeRelExtractor(),
            reasoner=_FakeReasoner(),
        )
        result = json.loads(kit.extract_entities("text"))
        self.assertEqual(result["count"], 0)
        self.assertIn("error", result)


class TestExtractRelations(unittest.TestCase):

    def setUp(self):
        self.kit = AgnoKGToolkit(
            ner_extractor=_FakeNER(),
            relation_extractor=_FakeRelExtractor(),
            reasoner=_FakeReasoner(),
        )

    def test_returns_json(self):
        result = json.loads(self.kit.extract_relations("Tesla was founded by Elon Musk."))
        self.assertIn("relations", result)
        self.assertIn("count", result)

    def test_relation_shape(self):
        result = json.loads(self.kit.extract_relations("text"))
        for rel in result["relations"]:
            self.assertIn("source", rel)
            self.assertIn("relation", rel)
            self.assertIn("target", rel)
            self.assertIn("confidence", rel)

    def test_entities_filter_parsed_from_json(self):
        self.kit.extract_relations("text", entities='["Tesla", "Elon Musk"]')
        # Should not raise

    def test_entities_filter_parsed_from_csv(self):
        self.kit.extract_relations("text", entities="Tesla, Elon Musk")
        # Should not raise

    def test_handles_failure_gracefully(self):
        bad_rel = MagicMock()
        bad_rel.extract_relations.side_effect = RuntimeError("fail")
        kit = AgnoKGToolkit(
            ner_extractor=_FakeNER(),
            relation_extractor=bad_rel,
            reasoner=_FakeReasoner(),
        )
        result = json.loads(kit.extract_relations("text"))
        self.assertEqual(result["count"], 0)
        self.assertIn("error", result)


class TestAddToGraph(unittest.TestCase):

    def setUp(self):
        self.graph = _FakeGraph()
        self.kit = AgnoKGToolkit(
            ner_extractor=_FakeNER(),
            relation_extractor=_FakeRelExtractor(),
            reasoner=_FakeReasoner(),
        )
        self.kit._graph = self.graph

    def test_add_entities_json(self):
        entities = json.dumps([{"name": "Alice", "type": "PERSON"}])
        result = json.loads(self.kit.add_to_graph(entities=entities))
        self.assertEqual(result["nodes_added"], 1)

    def test_add_relations_json(self):
        relations = json.dumps([{"source": "Alice", "relation": "WORKS_AT", "target": "ACME"}])
        result = json.loads(self.kit.add_to_graph(relations=relations))
        self.assertEqual(result["edges_added"], 1)

    def test_add_both(self):
        entities = json.dumps([{"name": "Bob", "type": "PERSON"}])
        relations = json.dumps([{"source": "Bob", "relation": "WORKS_AT", "target": "Corp"}])
        result = json.loads(self.kit.add_to_graph(entities=entities, relations=relations))
        self.assertEqual(result["nodes_added"], 1)
        self.assertEqual(result["edges_added"], 1)

    def test_empty_call(self):
        result = json.loads(self.kit.add_to_graph())
        self.assertEqual(result["nodes_added"], 0)
        self.assertEqual(result["edges_added"], 0)


class TestQueryGraph(unittest.TestCase):

    def setUp(self):
        self.graph = _FakeGraph()
        self.kit = AgnoKGToolkit(
            ner_extractor=_FakeNER(),
            relation_extractor=_FakeRelExtractor(),
            reasoner=_FakeReasoner(),
        )
        self.kit._graph = self.graph

    def test_keyword_query_returns_results(self):
        result = json.loads(self.kit.query_graph("Tesla"))
        self.assertIn("results", result)
        self.assertEqual(result["query_type"], "keyword")

    def test_cypher_query_without_backend(self):
        result = json.loads(self.kit.query_graph("MATCH (n) RETURN n LIMIT 5"))
        # Without a real neo4j backend, should return an error
        self.assertEqual(result["query_type"], "cypher")

    def test_handles_exception(self):
        bad_graph = MagicMock()
        bad_graph.find_nodes.side_effect = RuntimeError("graph error")
        self.kit._graph = bad_graph
        result = json.loads(self.kit.query_graph("anything"))
        self.assertIn("error", result)


class TestFindRelated(unittest.TestCase):

    def setUp(self):
        self.graph = _FakeGraph()
        self.kit = AgnoKGToolkit(
            ner_extractor=_FakeNER(),
            relation_extractor=_FakeRelExtractor(),
            reasoner=_FakeReasoner(),
        )
        self.kit._graph = self.graph

    def test_returns_json(self):
        result = json.loads(self.kit.find_related("Tesla"))
        self.assertIn("entity", result)
        self.assertIn("related", result)
        self.assertIn("count", result)

    def test_entity_preserved(self):
        result = json.loads(self.kit.find_related("Elon"))
        self.assertEqual(result["entity"], "Elon")

    def test_hops_parameter(self):
        result = json.loads(self.kit.find_related("Tesla", hops=2))
        self.assertIsInstance(result["related"], list)


class TestInferFacts(unittest.TestCase):

    def setUp(self):
        self.kit = AgnoKGToolkit(
            ner_extractor=_FakeNER(),
            relation_extractor=_FakeRelExtractor(),
            reasoner=_FakeReasoner(),
        )
        self.kit._graph = _FakeGraph()
        self.kit._graph._nodes = {"n1": MagicMock(label="EthicalAI", node_type="AI")}

    def test_returns_inferred_facts(self):
        result = json.loads(self.kit.infer_facts(rules='["IF AI(?x) THEN System(?x)"]'))
        self.assertIn("inferred_facts", result)
        self.assertIsInstance(result["inferred_facts"], list)

    def test_count_correct(self):
        result = json.loads(self.kit.infer_facts(rules='["IF X(?a) THEN Y(?a)"]'))
        self.assertEqual(result["count"], len(result["inferred_facts"]))

    def test_rules_as_csv(self):
        result = json.loads(self.kit.infer_facts(rules="IF AI(?x) THEN System(?x)"))
        self.assertIn("inferred_facts", result)

    def test_facts_passed_explicitly(self):
        result = json.loads(self.kit.infer_facts(
            rules='["IF Person(?x) THEN Human(?x)"]',
            facts='["Person(Alice)"]',
        ))
        self.assertIn("inferred_facts", result)


class TestExportSubgraph(unittest.TestCase):

    def setUp(self):
        self.kit = AgnoKGToolkit(
            ner_extractor=_FakeNER(),
            relation_extractor=_FakeRelExtractor(),
            reasoner=_FakeReasoner(),
        )
        self.kit._graph = _FakeGraph()

    def test_returns_json(self):
        result_str = self.kit.export_subgraph()
        result = json.loads(result_str)
        self.assertIn("format", result)

    def test_format_passed(self):
        result = json.loads(self.kit.export_subgraph(format="turtle"))
        self.assertIn("format", result)

    def test_fallback_to_json_on_import_error(self):
        # RDFExporter may not be available in test env; should fall back gracefully
        result_str = self.kit.export_subgraph()
        result = json.loads(result_str)
        # Either the real export or the fallback JSON — both are valid
        self.assertIsInstance(result, dict)


if __name__ == "__main__":
    unittest.main()
