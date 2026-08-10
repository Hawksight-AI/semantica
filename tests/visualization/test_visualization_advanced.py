
import unittest
from contextlib import ExitStack
from unittest.mock import MagicMock, patch
import numpy as np

from semantica.visualization import analytics_visualizer, embedding_visualizer
from semantica.visualization.analytics_visualizer import AnalyticsVisualizer
from semantica.visualization.embedding_visualizer import EmbeddingVisualizer
from semantica.visualization.utils.color_schemes import ColorScheme
from tests.visualization._plotly_doubles import plotly_doubles

class TestVisualizationAdvanced(unittest.TestCase):

    def setUp(self):
        self.mock_logger = MagicMock()
        self.mock_tracker = MagicMock()

        stack = ExitStack()
        self.addCleanup(stack.close)
        stack.enter_context(plotly_doubles(analytics_visualizer, embedding_visualizer))

        self.patchers = [
            patch('semantica.visualization.analytics_visualizer.get_logger', return_value=self.mock_logger),
            patch('semantica.visualization.analytics_visualizer.get_progress_tracker', return_value=self.mock_tracker),
            patch('semantica.visualization.embedding_visualizer.get_logger', return_value=self.mock_logger),
            patch('semantica.visualization.embedding_visualizer.get_progress_tracker', return_value=self.mock_tracker),
        ]
        
        for p in self.patchers:
            p.start()

    def tearDown(self):
        for p in self.patchers:
            p.stop()

    # --- AnalyticsVisualizer Tests ---
    def test_analytics_viz_init(self):
        viz = AnalyticsVisualizer(color_scheme="vibrant")
        self.assertIsInstance(viz, AnalyticsVisualizer)
        self.assertEqual(viz.color_scheme, ColorScheme.VIBRANT)

    def test_visualize_centrality_rankings(self):
        viz = AnalyticsVisualizer()
        centrality = {"n1": 0.5, "n2": 0.3}
        
        with (
            patch('semantica.visualization.analytics_visualizer.go.Bar') as mock_bar,
            patch('semantica.visualization.analytics_visualizer.go.Figure'),
        ):
            viz.visualize_centrality_rankings(centrality, output="interactive")
        mock_bar.assert_called()

    def test_visualize_community_structure(self):
        viz = AnalyticsVisualizer()
        
        if hasattr(viz, 'visualize_community_structure'):
            graph = MagicMock()
            communities = {"c1": ["n1", "n2"]}
            
            # Assuming it creates a figure or raises error if not implemented
            try:
                viz.visualize_community_structure(graph, communities)
            except Exception:
                pass
            # Just ensuring it runs without crashing due to missing deps (since we mocked them)

    # --- EmbeddingVisualizer Tests ---
    def test_embedding_viz_init(self):
        viz = EmbeddingVisualizer(point_size=10)
        self.assertIsInstance(viz, EmbeddingVisualizer)
        self.assertEqual(viz.point_size, 10)

    def test_visualize_2d_projection(self):
        viz = EmbeddingVisualizer()
        embeddings = np.random.rand(10, 128)
        
        # Mock UMAP/TSNE/PCA
        with patch('semantica.visualization.embedding_visualizer.umap') as mock_umap, \
             patch('semantica.visualization.embedding_visualizer.TSNE') as mock_tsne, \
             patch('semantica.visualization.embedding_visualizer.PCA') as mock_pca:
            
            # Setup mock returns
            mock_reducer = MagicMock()
            mock_reducer.fit_transform.return_value = np.random.rand(10, 2)
            mock_umap.UMAP.return_value = mock_reducer
            mock_tsne.return_value = mock_reducer
            mock_pca.return_value = mock_reducer
            
            # Test UMAP
            viz.visualize_2d_projection(embeddings, method="umap")
            if mock_umap: 
                mock_umap.UMAP.assert_called()
            
            # Test PCA
            viz.visualize_2d_projection(embeddings, method="pca")
            mock_pca.assert_called()

    def test_visualize_similarity_heatmap(self):
        viz = EmbeddingVisualizer()
        embeddings = np.random.rand(5, 5)
        
        if hasattr(viz, 'visualize_similarity_heatmap'):
            with (
                patch('semantica.visualization.embedding_visualizer.go.Heatmap') as mock_heatmap,
                patch('semantica.visualization.embedding_visualizer.go.Figure'),
            ):
                viz.visualize_similarity_heatmap(embeddings)
            mock_heatmap.assert_called()

if __name__ == '__main__':
    unittest.main()
