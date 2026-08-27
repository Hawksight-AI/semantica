"""
Tests for KGVisualizer._normalize_graph() and the fix for issue #458:
  "KGVisualizer.visualize_network() does not accept a KnowledgeGraph object"

All public visualize_* methods must accept either:
  - a plain dict  {"entities": [...], "relationships": [...]}
  - any object exposing .entities / .relationships attributes
and must raise a clear ProcessingError for anything else.
"""

import contextlib
import unittest
from dataclasses import dataclass, field
from typing import List
from unittest.mock import MagicMock, patch

from semantica.utils.exceptions import ProcessingError  # noqa: E402
from semantica.visualization import kg_visualizer  # noqa: E402
from semantica.visualization.kg_visualizer import KGVisualizer  # noqa: E402
from tests.visualization._plotly_doubles import plotly_doubles  # noqa: E402


# ---------------------------------------------------------------------------
# Minimal fixtures
# ---------------------------------------------------------------------------
ENTITIES = [
    {"id": "e1", "text": "Alice", "type": "Person"},
    {"id": "e2", "text": "Bob", "type": "Person"},
]
RELATIONSHIPS = [
    {"source": "e1", "target": "e2", "type": "KNOWS"},
]
GRAPH_DICT = {"entities": ENTITIES, "relationships": RELATIONSHIPS}


@dataclass
class SimpleKG:
    """Minimal KnowledgeGraph-like dataclass (mimics GraphBuilder output)."""
    entities: List[dict] = field(default_factory=list)
    relationships: List[dict] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


class NamespaceKG:
    """Object-with-attributes variant (no dataclass decorator)."""
    def __init__(self, entities, relationships, metadata=None):
        self.entities = entities
        self.relationships = relationships
        self.metadata = metadata or {}


# ---------------------------------------------------------------------------
# Helper: build a KGVisualizer with all heavy internals mocked out
# ---------------------------------------------------------------------------

def _make_viz():
    mock_logger = MagicMock()
    mock_tracker = MagicMock()
    mock_tracker.enabled = True
    mock_tracker.start_tracking.return_value = "tid"

    patches = [
        patch("semantica.visualization.kg_visualizer.get_logger", return_value=mock_logger),
        patch("semantica.visualization.kg_visualizer.get_progress_tracker", return_value=mock_tracker),
        patch("semantica.visualization.kg_visualizer.ForceDirectedLayout", MagicMock()),
        patch("semantica.visualization.kg_visualizer.HierarchicalLayout", MagicMock()),
        patch("semantica.visualization.kg_visualizer.CircularLayout", MagicMock()),
    ]
    with contextlib.ExitStack() as stack:
        for p in patches:
            stack.enter_context(p)
        viz = KGVisualizer(layout="force")

    viz.logger = mock_logger
    viz.progress_tracker = mock_tracker
    return viz


# ---------------------------------------------------------------------------
# Tests for _normalize_graph directly
# ---------------------------------------------------------------------------

class TestNormalizeGraph(unittest.TestCase):
    """Unit tests for _normalize_graph — no Plotly calls needed."""

    def setUp(self):
        self.viz = _make_viz()

    # --- dict input ---

    def test_dict_passthrough(self):
        result = self.viz._normalize_graph(GRAPH_DICT)
        self.assertIs(result, GRAPH_DICT, "_normalize_graph should return the same dict unchanged")

    def test_dict_missing_keys_passthrough(self):
        """A dict without entities/relationships is still passed through; callers handle emptiness."""
        result = self.viz._normalize_graph({})
        self.assertIsInstance(result, dict)

    # --- object-with-attributes input ---

    def test_dataclass_kg(self):
        kg = SimpleKG(entities=ENTITIES, relationships=RELATIONSHIPS)
        result = self.viz._normalize_graph(kg)
        self.assertEqual(result["entities"], ENTITIES)
        self.assertEqual(result["relationships"], RELATIONSHIPS)

    def test_namespace_kg(self):
        kg = NamespaceKG(entities=ENTITIES, relationships=RELATIONSHIPS)
        result = self.viz._normalize_graph(kg)
        self.assertEqual(result["entities"], ENTITIES)
        self.assertEqual(result["relationships"], RELATIONSHIPS)

    def test_object_with_only_entities(self):
        """An object with only .entities (no .relationships) should still work."""
        class EntitiesOnly:
            entities = ENTITIES
        result = self.viz._normalize_graph(EntitiesOnly())
        self.assertEqual(result["entities"], ENTITIES)
        self.assertEqual(result["relationships"], [])

    def test_object_with_only_relationships(self):
        """An object with only .relationships (no .entities) should still work."""
        class RelsOnly:
            relationships = RELATIONSHIPS
        result = self.viz._normalize_graph(RelsOnly())
        self.assertEqual(result["entities"], [])
        self.assertEqual(result["relationships"], RELATIONSHIPS)

    def test_metadata_propagated(self):
        kg = SimpleKG(entities=ENTITIES, relationships=RELATIONSHIPS, metadata={"version": "1"})
        result = self.viz._normalize_graph(kg)
        self.assertEqual(result["metadata"], {"version": "1"})

    def test_metadata_defaults_to_empty_dict(self):
        kg = NamespaceKG(entities=ENTITIES, relationships=RELATIONSHIPS)
        kg.metadata = None
        result = self.viz._normalize_graph(kg)
        self.assertEqual(result["metadata"], {})

    # --- unsupported types ---

    def test_raises_for_string(self):
        with self.assertRaises(ProcessingError) as ctx:
            self.viz._normalize_graph("not a graph")
        self.assertIn("str", str(ctx.exception))

    def test_raises_for_integer(self):
        with self.assertRaises(ProcessingError):
            self.viz._normalize_graph(42)

    def test_raises_for_list(self):
        with self.assertRaises(ProcessingError):
            self.viz._normalize_graph([{"id": "e1"}])

    def test_raises_for_none(self):
        with self.assertRaises((ProcessingError, AttributeError)):
            self.viz._normalize_graph(None)

    def test_error_message_names_type(self):
        class WeirdThing:
            pass
        with self.assertRaises(ProcessingError) as ctx:
            self.viz._normalize_graph(WeirdThing())
        self.assertIn("WeirdThing", str(ctx.exception))


# ---------------------------------------------------------------------------
# Integration: visualize_network accepts KG objects end-to-end
# ---------------------------------------------------------------------------

class TestVisualizeNetworkAcceptsKGObject(unittest.TestCase):
    """
    Regression tests for issue #458.

    visualize_network() must produce the same result whether it receives a
    dict or an equivalent KG object.
    """

    def _run_visualize_network(self, graph_arg):
        """Run visualize_network with all Plotly internals mocked."""
        mock_fig = MagicMock()

        viz = _make_viz()

        # Mock layout to return deterministic positions
        fake_pos = {"e1": (0.0, 0.0), "e2": (1.0, 1.0)}
        viz.force_layout = MagicMock()
        viz.force_layout.compute_layout.return_value = fake_pos
        viz.hierarchical_layout = MagicMock()
        viz.circular_layout = MagicMock()

        # ColorPalette helpers
        with (
            plotly_doubles(kg_visualizer),
            patch("semantica.visualization.kg_visualizer.go.Figure", return_value=mock_fig),
            patch("semantica.visualization.kg_visualizer.go.Scatter"),
            patch("semantica.visualization.kg_visualizer.go.Layout"),
            patch(
                "semantica.visualization.kg_visualizer.ColorPalette.get_entity_type_colors",
                return_value={"Person": "#ff0000"},
            ),
            patch(
                "semantica.visualization.kg_visualizer.ColorPalette.get_colors",
                return_value=["#ff0000"],
            ),
        ):
            return viz.visualize_network(graph_arg, output="interactive")

    def test_dict_input_returns_figure(self):
        fig = self._run_visualize_network(GRAPH_DICT)
        self.assertIsNotNone(fig)

    def test_dataclass_kg_returns_figure(self):
        """Issue #458: passing a KnowledgeGraph dataclass must not be a silent no-op."""
        kg = SimpleKG(entities=ENTITIES, relationships=RELATIONSHIPS)
        fig = self._run_visualize_network(kg)
        self.assertIsNotNone(fig)

    def test_namespace_kg_returns_figure(self):
        kg = NamespaceKG(entities=ENTITIES, relationships=RELATIONSHIPS)
        fig = self._run_visualize_network(kg)
        self.assertIsNotNone(fig)

    def test_unsupported_type_raises_processing_error(self):
        viz = _make_viz()
        with self.assertRaises(ProcessingError):
            viz.visualize_network("not a graph")


# ---------------------------------------------------------------------------
# Integration: all other visualize_* methods also accept KG objects
# ---------------------------------------------------------------------------

class TestAllVisualizeMethodsAcceptKGObject(unittest.TestCase):
    """Each public visualize_* method must call _normalize_graph."""

    def setUp(self):
        self.viz = _make_viz()
        self.kg = SimpleKG(entities=ENTITIES, relationships=RELATIONSHIPS)

    def test_visualize_communities_accepts_kg_object(self):
        self.viz._normalize_graph = MagicMock(return_value=GRAPH_DICT)
        self.viz._visualize_network_plotly = MagicMock(return_value=MagicMock())
        communities = {"node_assignments": {"e1": 0, "e2": 1}, "num_communities": 2}
        with (
            plotly_doubles(kg_visualizer),
            patch(
                "semantica.visualization.kg_visualizer.ColorPalette.get_community_colors",
                return_value=["#ff0000", "#00ff00"],
            ),
        ):
            self.viz.visualize_communities(self.kg, communities=communities)
        self.viz._normalize_graph.assert_called_once_with(self.kg)

    def test_visualize_centrality_accepts_kg_object(self):
        self.viz._normalize_graph = MagicMock(return_value=GRAPH_DICT)
        self.viz._visualize_network_plotly = MagicMock(return_value=MagicMock())
        with plotly_doubles(kg_visualizer):
            self.viz.visualize_centrality(self.kg, centrality={"centrality": {}})
        self.viz._normalize_graph.assert_called_once_with(self.kg)

    def test_visualize_entity_types_accepts_kg_object(self):
        self.viz._normalize_graph = MagicMock(return_value=GRAPH_DICT)
        with plotly_doubles(kg_visualizer), patch("semantica.visualization.kg_visualizer.px.bar"):
            self.viz.visualize_entity_types(self.kg)
        self.viz._normalize_graph.assert_called_once_with(self.kg)

    def test_visualize_relationship_matrix_accepts_kg_object(self):
        self.viz._normalize_graph = MagicMock(return_value=GRAPH_DICT)
        with (
            plotly_doubles(kg_visualizer),
            patch("semantica.visualization.kg_visualizer.go.Figure"),
            patch("semantica.visualization.kg_visualizer.go.Heatmap"),
        ):
            self.viz.visualize_relationship_matrix(self.kg)
        self.viz._normalize_graph.assert_called_once_with(self.kg)


# ---------------------------------------------------------------------------
# Issue #471 — formal KnowledgeGraph type support
# ---------------------------------------------------------------------------

class TestFormalKnowledgeGraphType(unittest.TestCase):
    """
    Regression tests for issue #471.

    The formal ``semantica.kg.KnowledgeGraph`` dataclass must be accepted by
    every public visualize_* method without requiring any manual conversion.
    """

    @classmethod
    def setUpClass(cls):
        try:
            from semantica.kg.knowledge_graph import KnowledgeGraph
            cls.KnowledgeGraph = KnowledgeGraph
        except ImportError:
            cls.KnowledgeGraph = None

    def _make_kg(self):
        if self.KnowledgeGraph is None:
            self.skipTest("semantica.kg.KnowledgeGraph not available")
        return self.KnowledgeGraph(
            entities=ENTITIES,
            relationships=RELATIONSHIPS,
            metadata={"version": "test"},
        )

    def test_convert_knowledge_graph_entities(self):
        kg = self._make_kg()
        viz = _make_viz()
        result = viz._convert_knowledge_graph(kg)
        self.assertEqual(result["entities"], ENTITIES)

    def test_convert_knowledge_graph_relationships(self):
        kg = self._make_kg()
        viz = _make_viz()
        result = viz._convert_knowledge_graph(kg)
        self.assertEqual(result["relationships"], RELATIONSHIPS)

    def test_convert_knowledge_graph_metadata(self):
        kg = self._make_kg()
        viz = _make_viz()
        result = viz._convert_knowledge_graph(kg)
        self.assertEqual(result["metadata"], {"version": "test"})

    def test_convert_knowledge_graph_does_not_mutate(self):
        kg = self._make_kg()
        original_entities = list(kg.entities)
        original_relationships = list(kg.relationships)
        viz = _make_viz()
        viz._convert_knowledge_graph(kg)
        self.assertEqual(kg.entities, original_entities)
        self.assertEqual(kg.relationships, original_relationships)

    def test_convert_knowledge_graph_is_deterministic(self):
        kg = self._make_kg()
        viz = _make_viz()
        self.assertEqual(viz._convert_knowledge_graph(kg), viz._convert_knowledge_graph(kg))

    def test_normalize_graph_routes_kg_type(self):
        kg = self._make_kg()
        viz = _make_viz()
        viz._convert_knowledge_graph = MagicMock(return_value=GRAPH_DICT)
        viz._normalize_graph(kg)
        viz._convert_knowledge_graph.assert_called_once_with(kg)

    def test_normalize_graph_returns_dict_for_kg_type(self):
        kg = self._make_kg()
        viz = _make_viz()
        result = viz._normalize_graph(kg)
        self.assertIsInstance(result, dict)
        self.assertIn("entities", result)
        self.assertIn("relationships", result)

    def _run_visualize_network(self, graph_arg):
        mock_fig = MagicMock()
        viz = _make_viz()
        fake_pos = {"e1": (0.0, 0.0), "e2": (1.0, 1.0)}
        viz.force_layout = MagicMock()
        viz.force_layout.compute_layout.return_value = fake_pos
        viz.hierarchical_layout = MagicMock()
        viz.circular_layout = MagicMock()
        with (
            plotly_doubles(kg_visualizer),
            patch("semantica.visualization.kg_visualizer.go.Figure", return_value=mock_fig),
            patch("semantica.visualization.kg_visualizer.go.Scatter"),
            patch("semantica.visualization.kg_visualizer.go.Layout"),
            patch(
                "semantica.visualization.kg_visualizer.ColorPalette.get_entity_type_colors",
                return_value={"Person": "#ff0000"},
            ),
            patch(
                "semantica.visualization.kg_visualizer.ColorPalette.get_colors",
                return_value=["#ff0000"],
            ),
        ):
            return viz.visualize_network(graph_arg, output="interactive")

    def test_visualize_network_accepts_knowledge_graph(self):
        self.assertIsNotNone(self._run_visualize_network(self._make_kg()))

    def test_visualize_communities_accepts_knowledge_graph(self):
        kg = self._make_kg()
        viz = _make_viz()
        viz._normalize_graph = MagicMock(return_value=GRAPH_DICT)
        viz._visualize_network_plotly = MagicMock(return_value=MagicMock())
        communities = {"node_assignments": {"e1": 0, "e2": 1}, "num_communities": 2}
        with (
            plotly_doubles(kg_visualizer),
            patch(
                "semantica.visualization.kg_visualizer.ColorPalette.get_community_colors",
                return_value=["#ff0000", "#00ff00"],
            ),
        ):
            viz.visualize_communities(kg, communities=communities)
        viz._normalize_graph.assert_called_once_with(kg)

    def test_visualize_centrality_accepts_knowledge_graph(self):
        kg = self._make_kg()
        viz = _make_viz()
        viz._normalize_graph = MagicMock(return_value=GRAPH_DICT)
        viz._visualize_network_plotly = MagicMock(return_value=MagicMock())
        with plotly_doubles(kg_visualizer):
            viz.visualize_centrality(kg, centrality={"centrality": {}})
        viz._normalize_graph.assert_called_once_with(kg)

    def test_visualize_entity_types_accepts_knowledge_graph(self):
        kg = self._make_kg()
        viz = _make_viz()
        viz._normalize_graph = MagicMock(return_value=GRAPH_DICT)
        with plotly_doubles(kg_visualizer), patch("semantica.visualization.kg_visualizer.px.bar"):
            viz.visualize_entity_types(kg)
        viz._normalize_graph.assert_called_once_with(kg)

    def test_visualize_relationship_matrix_accepts_knowledge_graph(self):
        kg = self._make_kg()
        viz = _make_viz()
        viz._normalize_graph = MagicMock(return_value=GRAPH_DICT)
        with (
            plotly_doubles(kg_visualizer),
            patch("semantica.visualization.kg_visualizer.go.Figure"),
            patch("semantica.visualization.kg_visualizer.go.Heatmap"),
        ):
            viz.visualize_relationship_matrix(kg)
        viz._normalize_graph.assert_called_once_with(kg)

    def test_knowledge_graph_importable_from_kg_module(self):
        if self.KnowledgeGraph is None:
            self.skipTest("semantica.kg.KnowledgeGraph not available")
        try:
            import semantica.kg as _kg_module
            _ = _kg_module.KnowledgeGraph
        except (ImportError, AttributeError) as exc:
            self.fail(f"KnowledgeGraph not exported from semantica.kg: {exc}")

    def test_knowledge_graph_empty_defaults(self):
        kg = self.KnowledgeGraph()
        self.assertEqual(kg.entities, [])
        self.assertEqual(kg.relationships, [])
        self.assertFalse(bool(kg))

    def test_knowledge_graph_len(self):
        kg = self._make_kg()
        self.assertEqual(len(kg), len(ENTITIES))


if __name__ == "__main__":
    unittest.main()
