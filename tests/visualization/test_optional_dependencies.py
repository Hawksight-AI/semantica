import importlib
import sys
import unittest
from contextlib import contextmanager
from unittest.mock import patch

import numpy as np

from tests.visualization._plotly_doubles import plotly_doubles


@contextmanager
def import_without(module_name, *dependencies):
    """Import a module with selected optional dependencies unavailable."""
    package_name, attribute = module_name.rsplit(".", 1)
    package = importlib.import_module(package_name)
    missing = object()
    original_module = sys.modules.pop(module_name, missing)
    original_attribute = getattr(package, attribute, missing)

    try:
        with patch.dict(sys.modules, {name: None for name in dependencies}):
            yield importlib.import_module(module_name)
    finally:
        sys.modules.pop(module_name, None)
        if original_module is not missing:
            sys.modules[module_name] = original_module
        if original_attribute is missing:
            package.__dict__.pop(attribute, None)
        else:
            setattr(package, attribute, original_attribute)


class TestOptionalDependencies(unittest.TestCase):

    def test_embedding_visualizer_without_umap(self):
        """Test EmbeddingVisualizer behavior when umap is missing."""
        with import_without(
            "semantica.visualization.embedding_visualizer", "umap"
        ) as module:
            with plotly_doubles(module), patch.object(module, "PCA") as mock_pca_class:
                mock_pca_class.return_value.fit_transform.return_value = np.zeros((4, 2))

                viz = module.EmbeddingVisualizer()
                embeddings = np.array([[0, 1, 2], [1, 0, 3], [0, 0, 0], [1, 1, 1]])
                viz.visualize_2d_projection(embeddings, method="umap")

            mock_pca_class.assert_called()

    def test_ontology_visualizer_without_graphviz(self):
        """Test OntologyVisualizer behavior when graphviz is missing."""
        with import_without(
            "semantica.visualization.ontology_visualizer", "graphviz"
        ) as module:
            viz = module.OntologyVisualizer()
            ontology = {
                "classes": [
                    {"name": "A", "label": "A"},
                    {"name": "B", "label": "B", "parent": "A"},
                ]
            }

            with self.assertRaises(module.ProcessingError) as cm:
                viz.visualize_hierarchy(ontology, output="dot", file_path="test.dot")

            self.assertIn("Graphviz is required for DOT export", str(cm.exception))

    def test_analytics_visualizer_without_plotly(self):
        """Test AnalyticsVisualizer behavior when plotly is missing."""
        with import_without(
            "semantica.visualization.analytics_visualizer",
            "plotly",
            "plotly.express",
            "plotly.graph_objects",
        ) as module:
            viz = module.AnalyticsVisualizer()

            with self.assertRaises(module.ProcessingError) as cm:
                viz.visualize_centrality_rankings({})

            self.assertIn("Plotly is required", str(cm.exception))

    def test_semantic_network_visualizer_without_plotly(self):
        """Test SemanticNetworkVisualizer behavior when plotly is missing."""
        with import_without(
            "semantica.visualization.semantic_network_visualizer",
            "plotly",
            "plotly.express",
            "plotly.graph_objects",
        ) as module:
            viz = module.SemanticNetworkVisualizer()

            with self.assertRaises(module.ProcessingError) as cm:
                viz.visualize_network({})

            self.assertIn("Plotly is required", str(cm.exception))

    def test_temporal_visualizer_without_plotly(self):
        """Test TemporalVisualizer behavior when plotly is missing."""
        with import_without(
            "semantica.visualization.temporal_visualizer",
            "plotly",
            "plotly.express",
            "plotly.graph_objects",
        ) as module:
            viz = module.TemporalVisualizer()

            with self.assertRaises(module.ProcessingError) as cm:
                viz.visualize_timeline({"events": []})

            self.assertIn("Plotly is required", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
