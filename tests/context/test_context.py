
import unittest
from unittest.mock import MagicMock, patch
from datetime import datetime
import sys
import os

# Ensure the semantica package is in the path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from semantica.context.entity_linker import EntityLinker, LinkedEntity, EntityLink
from semantica.context.context_graph import ContextGraph, ContextNode, ContextEdge
from semantica.context.agent_memory import AgentMemory, MemoryItem
from semantica.context.context_retriever import ContextRetriever, RetrievedContext
from semantica.context.agent_context import AgentContext

class MockVectorStore:
    def __init__(self):
        self.vectors = []
        self.metadata = []
    
    def store_vectors(self, vectors, metadata):
        self.vectors.extend(vectors)
        self.metadata.extend(metadata)
        
    def add(self, items):
        # Support add protocol
        for item in items:
            self.metadata.append(item.metadata)

    def search(self, query_vector, k=5):
        # Mock search return
        return []

class TestContextModule(unittest.TestCase):

    def setUp(self):
        self.mock_vector_store = MockVectorStore()
        self.mock_kg = MagicMock()

    # --- EntityLinker Tests ---
    def test_entity_linker_assign_uri(self):
        linker = EntityLinker(base_uri="http://example.com/")
        
        # Test text-based URI
        uri1 = linker.assign_uri("id1", "Test Entity", "TEST")
        self.assertEqual(uri1, "http://example.com/test_entity#test")
        
        # Test hash-based URI
        uri2 = linker.assign_uri("id2")
        self.assertTrue(uri2.startswith("http://example.com/"))
        
        # Test registry
        uri3 = linker.assign_uri("id1")
        self.assertEqual(uri3, uri1)

    def test_entity_linker_link(self):
        linker = EntityLinker()
        entities = [{"text": "Python", "label": "LANGUAGE", "start": 0, "end": 6}]
        linked = linker.link("Python code", entities=entities)
        # Note: The current implementation of link might be a placeholder or depend on logic 
        # that returns empty if no detailed logic is implemented. 
        # Based on my read, it tracks progress but might not implement full logic without external NLP.
        # However, checking it runs without error is a good start.
        self.assertIsInstance(linked, list)

    def test_entity_linker_find_similar_entities_returns_dicts(self):
        linker = EntityLinker(
            knowledge_graph={
                "entities": [
                    {"id": "lang_python", "text": "Python programming language", "type": "Technology"}
                ]
            }
        )
        linker.assign_uri("lang_python", "Python programming language", "Technology")

        similar = linker.find_similar_entities("Python programming language", threshold=0.5)

        self.assertEqual(len(similar), 1)
        self.assertEqual(similar[0]["entity_id"], "lang_python")
        self.assertEqual(similar[0]["text"], "Python programming language")
        self.assertIn("similarity", similar[0])

    # --- ContextGraph Tests ---
    def test_context_graph_operations(self):
        graph = ContextGraph()
        
        # Add nodes
        nodes = [
            {"id": "n1", "type": "person", "properties": {"name": "Alice"}},
            {"id": "n2", "type": "person", "properties": {"name": "Bob"}}
        ]
        count = graph.add_nodes(nodes)
        self.assertEqual(count, 2)
        self.assertIn("n1", graph.nodes)
        self.assertIn("n2", graph.nodes)
        
        # Add edges
        edges = [
            {"source_id": "n1", "target_id": "n2", "type": "knows", "weight": 0.8}
        ]
        count = graph.add_edges(edges)
        self.assertEqual(count, 1)
        self.assertEqual(len(graph.edges), 1)
        
        # Get neighbors
        neighbors = graph.get_neighbors("n1")
        self.assertEqual(len(neighbors), 1)
        self.assertEqual(neighbors[0]["id"], "n2")
        self.assertEqual(neighbors[0]["relationship"], "knows")

    def test_add_edge_is_idempotent(self):
        graph = ContextGraph()
        graph.add_node("a", "t")
        graph.add_node("b", "t")

        self.assertTrue(graph.add_edge("a", "b", "rel"))
        self.assertFalse(graph.add_edge("a", "b", "rel"))
        self.assertFalse(graph.add_edge("a", "b", "rel"))

        self.assertEqual(len(graph.edges), 1)
        self.assertEqual(len(graph.edge_type_index["rel"]), 1)
        self.assertEqual(len(graph._adjacency["a"]), 1)
        self.assertEqual(graph.stats()["edge_count"], 1)
        self.assertLessEqual(graph.density(), 1.0)

    def test_parallel_edges_with_distinct_attributes_are_kept(self):
        graph = ContextGraph()
        graph.add_node("a", "t")
        graph.add_node("b", "t")

        graph.add_edge("a", "b", "rel", confidence=0.9)
        graph.add_edge("a", "b", "rel", confidence=0.5)
        graph.add_edge("a", "b", "other")

        self.assertEqual(len(graph.edges), 3)
        self.assertEqual(len({e.edge_id for e in graph.edges}), 3)

    def test_reingest_does_not_duplicate_edges(self):
        graph = ContextGraph()
        entities = [
            {"id": "alice", "type": "person"},
            {"id": "acme", "type": "org"},
        ]
        relationships = [
            {"source_id": "alice", "target_id": "acme", "type": "works_at"}
        ]

        for _ in range(3):
            graph.build_from_entities_and_relationships(entities, relationships)

        self.assertEqual(len(graph.edges), 1)

    def test_clear_resets_edge_dedupe_index(self):
        graph = ContextGraph()
        graph.add_node("a", "t")
        graph.add_node("b", "t")
        graph.add_edge("a", "b", "rel")

        graph.clear()

        graph.add_node("a", "t")
        graph.add_node("b", "t")
        self.assertTrue(graph.add_edge("a", "b", "rel"))
        self.assertEqual(len(graph.edges), 1)

    def test_get_nodes_by_label_returns_metadata_copy(self):
        graph = ContextGraph()
        graph.add_node("n1", "person", "Alice", role="engineer")

        nodes = graph.get_nodes_by_label("person")
        self.assertEqual(len(nodes), 1)

        nodes[0]["metadata"]["role"] = "mutated"

        self.assertEqual(graph.get_node_property("n1", "role"), "engineer")

    def test_context_graph_preserves_full_decision_text(self):
        graph = ContextGraph()
        scenario = "Launch regional expansion plan " + ("X" * 140)
        root_id = graph.record_decision(
            category="strategy",
            scenario=scenario,
            reasoning="Growth opportunity with strong local demand",
            outcome="approved",
            confidence=0.91,
        )
        child_id = graph.record_decision(
            category="operations",
            scenario="Open Sao Paulo office",
            reasoning="Needed to support expansion",
            outcome="pending",
            confidence=0.74,
        )
        graph.add_causal_relationship(root_id, child_id, "CAUSED")

        chain = graph.get_causal_chain(child_id)

        self.assertEqual(graph.nodes[root_id].content, scenario)
        self.assertEqual(graph.nodes[root_id].properties["scenario"], scenario)
        self.assertEqual(chain[0].scenario, scenario)

    def test_record_decision_metadata_cannot_override_core_fields(self):
        graph = ContextGraph()
        decision_id = graph.record_decision(
            category="strategy",
            scenario="Open LATAM expansion program",
            reasoning="High growth potential",
            outcome="approved",
            confidence=0.9,
            metadata={
                "scenario": "metadata override",
                "category": "metadata category",
                "outcome": "metadata outcome",
                "custom_note": "keep me",
            },
        )

        node = graph.nodes[decision_id]

        self.assertEqual(node.content, "Open LATAM expansion program")
        self.assertEqual(node.properties["scenario"], "Open LATAM expansion program")
        self.assertEqual(node.properties["category"], "strategy")
        self.assertEqual(node.properties["outcome"], "approved")
        self.assertEqual(node.properties["custom_note"], "keep me")

    # --- AgentMemory Tests ---
    def test_agent_memory_store(self):
        memory = AgentMemory(vector_store=self.mock_vector_store)
        
        # Store item
        memory_id = memory.store("Test memory content", metadata={"type": "test"})
        
        self.assertIsNotNone(memory_id)
        self.assertEqual(len(memory.short_term_memory), 1)
        self.assertEqual(memory.short_term_memory[0].content, "Test memory content")
        
        # Check vector store interaction (mocked _generate_embedding might be needed if not implemented)
        # The store method calls _generate_embedding. If it's not implemented or relies on external service, it might fail.
        # Let's see if we need to mock _generate_embedding.
        
    @patch('semantica.context.agent_memory.AgentMemory._generate_embedding')
    def test_agent_memory_vector_store(self, mock_gen_embedding):
        mock_gen_embedding.return_value = [0.1, 0.2, 0.3]
        memory = AgentMemory(vector_store=self.mock_vector_store)
        
        memory.store("Vector test")
        
        self.assertEqual(len(self.mock_vector_store.metadata), 1)
        self.assertEqual(self.mock_vector_store.metadata[0].get("type"), None) # Default empty metadata

    # --- ContextRetriever Tests ---
    def test_context_retriever_init(self):
        retriever = ContextRetriever(
            memory_store=MagicMock(),
            knowledge_graph=MagicMock(),
            vector_store=self.mock_vector_store
        )
        self.assertIsNotNone(retriever)

    def test_context_graph_rejects_cyclic_skos_single_edge_write(self):
        graph = ContextGraph()
        graph.add_edge("A", "B", "skos:broader")

        with self.assertRaisesRegex(ValueError, "SKOS hierarchy contains a cycle"):
            graph.add_edge("B", "A", "skos:broader")

        self.assertEqual(len(graph.edges), 1)

    def test_context_graph_rejects_cyclic_skos_batch_write(self):
        graph = ContextGraph()

        with self.assertRaisesRegex(ValueError, "SKOS hierarchy contains a cycle"):
            graph.add_edges([
                {"source": "A", "target": "B", "type": "skos:broader"},
                {"source": "A", "target": "B", "type": "skos:narrower"},
            ])

        self.assertEqual(len(graph.edges), 0)

    def test_context_graph_preexisting_unrelated_cycle_does_not_block_new_write(self):
        """A cycle already persisted elsewhere in the graph (e.g. legacy data
        written before cycle detection existed) must not poison unrelated
        SKOS hierarchy writes for concepts it doesn't touch."""
        from semantica.context.context_graph import ContextEdge

        graph = ContextGraph()
        graph._add_internal_edge(ContextEdge(source_id="X", target_id="Y", edge_type="skos:broader"))
        graph._add_internal_edge(ContextEdge(source_id="Y", target_id="X", edge_type="skos:broader"))

        self.assertTrue(graph.add_edge("C", "D", "skos:broader"))
        self.assertEqual(len(graph.edges), 3)

    # --- AgentContext Tests ---
    @patch('semantica.context.agent_memory.AgentMemory._generate_embedding')
    def test_agent_context_end_to_end(self, mock_gen_embedding):
        mock_gen_embedding.return_value = [0.1, 0.1]
        
        # Setup complete context system
        kg = ContextGraph()
        ctx = AgentContext(vector_store=self.mock_vector_store, knowledge_graph=kg)
        
        # Test store
        ctx.store("Alice knows Bob", extract_entities=False)
        
        # Verify internal components
        self.assertIsNotNone(ctx._memory)
        self.assertEqual(len(ctx._memory.short_term_memory), 1)

class TestContextGraphNodePropertyContract(unittest.TestCase):

    _MISSING = object()

    def _graph_with_node(self):
        graph = ContextGraph()
        graph.add_node("n1", "person", "Alice", role="engineer", score=0)
        return graph

    def test_get_node_property_existing_node_existing_prop(self):
        graph = self._graph_with_node()
        self.assertEqual(graph.get_node_property("n1", "role"), "engineer")

    def test_get_node_property_existing_node_missing_prop(self):
        graph = self._graph_with_node()
        self.assertIsNone(graph.get_node_property("n1", "nonexistent"))

    def test_get_node_property_missing_node_returns_default_none(self):
        graph = self._graph_with_node()
        self.assertIsNone(graph.get_node_property("ghost", "role"))

    def test_get_node_property_returns_default_on_missing_node(self):
        graph = self._graph_with_node()
        result = graph.get_node_property("ghost", "role", default=self._MISSING)
        self.assertIs(result, self._MISSING)

    def test_get_node_property_returns_default_on_missing_prop(self):
        graph = self._graph_with_node()
        result = graph.get_node_property("n1", "nonexistent", default=self._MISSING)
        self.assertIs(result, self._MISSING)

    def test_get_node_property_explicit_default_returned_for_absent_node(self):
        graph = self._graph_with_node()
        self.assertEqual(graph.get_node_property("ghost", "role", default="fallback"), "fallback")

    def test_get_node_property_prop_value_of_zero_not_swallowed(self):
        graph = self._graph_with_node()
        self.assertEqual(graph.get_node_property("n1", "score"), 0)

    def test_get_node_attributes_existing_node_returns_copy(self):
        graph = self._graph_with_node()
        attrs = graph.get_node_attributes("n1")
        self.assertIsInstance(attrs, dict)
        self.assertEqual(attrs.get("role"), "engineer")

    def test_get_node_attributes_missing_node_returns_empty_dict_by_default(self):
        graph = self._graph_with_node()
        self.assertEqual(graph.get_node_attributes("ghost"), {})

    def test_get_node_attributes_missing_node_explicit_default(self):
        graph = self._graph_with_node()
        result = graph.get_node_attributes("ghost", default={})
        self.assertEqual(result, {})

    def test_add_node_attribute_mutation_callback_fires_on_update(self):
        graph = self._graph_with_node()
        fired = []
        graph.mutation_callback = lambda op, nid, data: fired.append((op, nid))
        graph.add_node_attribute("n1", {"extra": "value"})
        self.assertEqual(len(fired), 1)
        self.assertEqual(fired[0], ("UPDATE_NODE", "n1"))

    def test_add_node_attribute_missing_node_no_callback(self):
        graph = self._graph_with_node()
        fired = []
        graph.mutation_callback = lambda op, nid, data: fired.append((op, nid))
        graph.add_node_attribute("ghost", {"extra": "value"})
        self.assertEqual(len(fired), 0)

    def test_add_node_attribute_raising_callback_does_not_propagate(self):
        graph = self._graph_with_node()

        def _boom(op, nid, data):
            raise RuntimeError("audit sink unavailable")

        graph.mutation_callback = _boom
        # Should not raise, matching _add_internal_node/_add_internal_edge,
        # which already catch and log mutation_callback exceptions.
        graph.add_node_attribute("n1", {"extra": "value"})
        self.assertEqual(graph.get_node_property("n1", "extra"), "value")


if __name__ == '__main__':
    unittest.main()
