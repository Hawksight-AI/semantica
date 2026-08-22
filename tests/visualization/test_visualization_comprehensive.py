import unittest
from unittest.mock import MagicMock, patch
import numpy as np
from pathlib import Path

import pytest

# Import visualizers
from semantica.visualization.kg_visualizer import KGVisualizer
from semantica.visualization.ontology_visualizer import OntologyVisualizer
from semantica.visualization.embedding_visualizer import EmbeddingVisualizer
from semantica.visualization.semantic_network_visualizer import SemanticNetworkVisualizer
from semantica.visualization.analytics_visualizer import AnalyticsVisualizer
from semantica.visualization.temporal_visualizer import TemporalVisualizer
from semantica.visualization.utils.color_schemes import ColorScheme

pytestmark = pytest.mark.integration
class TestVisualizationComprehensive(unittest.TestCase):

    def setUp(self):
        self.mock_logger = MagicMock()
        self.mock_tracker = MagicMock()
        
        # Patch dependencies for all visualizers
        self.patchers = [
            patch('semantica.visualization.kg_visualizer.get_logger', return_value=self.mock_logger),
            patch('semantica.visualization.kg_visualizer.get_progress_tracker', return_value=self.mock_tracker),
            patch('semantica.visualization.ontology_visualizer.get_logger', return_value=self.mock_logger),
            patch('semantica.visualization.ontology_visualizer.get_progress_tracker', return_value=self.mock_tracker),
            patch('semantica.visualization.embedding_visualizer.get_logger', return_value=self.mock_logger),
            patch('semantica.visualization.embedding_visualizer.get_progress_tracker', return_value=self.mock_tracker),
            patch('semantica.visualization.semantic_network_visualizer.get_logger', return_value=self.mock_logger),
            patch('semantica.visualization.semantic_network_visualizer.get_progress_tracker', return_value=self.mock_tracker),
            patch('semantica.visualization.analytics_visualizer.get_logger', return_value=self.mock_logger),
            patch('semantica.visualization.analytics_visualizer.get_progress_tracker', return_value=self.mock_tracker),
            patch('semantica.visualization.temporal_visualizer.get_logger', return_value=self.mock_logger),
            patch('semantica.visualization.temporal_visualizer.get_progress_tracker', return_value=self.mock_tracker),
            patch('semantica.visualization.kg_visualizer.go', MagicMock()),
            patch('semantica.visualization.kg_visualizer.px', MagicMock()),
            patch('semantica.visualization.ontology_visualizer.go', MagicMock()),
            patch('semantica.visualization.ontology_visualizer.make_subplots', MagicMock()),
            patch('semantica.visualization.embedding_visualizer.go', MagicMock()),
            patch('semantica.visualization.embedding_visualizer.px', MagicMock()),
            patch('semantica.visualization.semantic_network_visualizer.go', MagicMock()),
            patch('semantica.visualization.semantic_network_visualizer.px', MagicMock()),
            patch('semantica.visualization.analytics_visualizer.go', MagicMock()),
            patch('semantica.visualization.analytics_visualizer.px', MagicMock()),
            patch('semantica.visualization.analytics_visualizer.make_subplots', MagicMock()),
            patch('semantica.visualization.temporal_visualizer.go', MagicMock()),
            patch('semantica.visualization.temporal_visualizer.px', MagicMock()),
        ]
        
        for p in self.patchers:
            p.start()
            
    def tearDown(self):
        for p in self.patchers:
            p.stop()

    # --- KGVisualizer Tests ---
    def test_kg_visualizer(self):
        viz = KGVisualizer()
        graph = {
            "entities": [{"id": "e1", "label": "E1", "type": "T1"}, {"id": "e2", "label": "E2", "type": "T2"}],
            "relationships": [{"source": "e1", "target": "e2", "type": "R1"}]
        }
        
        # Test visualize_network
        viz.visualize_network(graph)
        
        # Test visualize_communities
        communities = {"node_assignments": {"e1": 0, "e2": 1}, "num_communities": 2}
        viz.visualize_communities(graph, communities)
        
        # Test visualize_centrality
        centrality = {"centrality": {"e1": 0.5, "e2": 0.3}}
        viz.visualize_centrality(graph, centrality)
        
        # Test visualize_entity_types
        viz.visualize_entity_types(graph)
        
        # Test visualize_relationship_matrix
        viz.visualize_relationship_matrix(graph)

    # --- OntologyVisualizer Tests ---
    def test_ontology_visualizer(self):
        viz = OntologyVisualizer()
        ontology = {
            "classes": [
                {"name": "C1", "label": "Class 1", "parent": None},
                {"name": "C2", "label": "Class 2", "parent": "C1"}
            ],
            "properties": [
                {"name": "P1", "label": "Prop 1", "domain": "C1", "range": "C2"}
            ]
        }
        
        # Test visualize_hierarchy
        viz.visualize_hierarchy(ontology)
        
        # Test visualize_properties
        viz.visualize_properties(ontology)
        
        # Test visualize_structure
        viz.visualize_structure(ontology)
        
        # Test visualize_class_property_matrix
        viz.visualize_class_property_matrix(ontology)
        
        # Test visualize_metrics
        viz.visualize_metrics(ontology)
        
        # Test visualize_semantic_model (mocking extract classes)
        semantic_model = {"nodes": [{"id": "n1", "type": "T1"}], "edges": []}
        viz.visualize_semantic_model(semantic_model)

    # --- SemanticNetworkVisualizer Tests ---
    def test_semantic_network_visualizer(self):
        viz = SemanticNetworkVisualizer()
        semantic_network = {
            "nodes": [{"id": "n1", "label": "N1", "type": "T1"}],
            "edges": [{"source": "n1", "target": "n1", "label": "R1"}]
        }
        
        # Test visualize_network
        with patch('semantica.visualization.kg_visualizer.KGVisualizer') as MockKG:
            viz.visualize_network(semantic_network)
            MockKG.return_value.visualize_network.assert_called()
            
        # Test visualize_node_types
        viz.visualize_node_types(semantic_network)
        
        # Test visualize_edge_types
        viz.visualize_edge_types(semantic_network)

    # --- AnalyticsVisualizer Tests ---
    def test_analytics_visualizer(self):
        viz = AnalyticsVisualizer()
        graph = {"entities": [], "relationships": []}
        
        # Test visualize_centrality_rankings
        centrality = {"rankings": [{"node": "n1", "score": 0.9}]}
        viz.visualize_centrality_rankings(centrality)
        
        # Test visualize_community_structure
        communities = {"node_assignments": {}}
        with patch('semantica.visualization.kg_visualizer.KGVisualizer') as MockKG:
             viz.visualize_community_structure(graph, communities)
        
        # Test visualize_connectivity
        connectivity = {"is_connected": True, "num_components": 1, "component_sizes": [10]}
        viz.visualize_connectivity(connectivity)
        
        # Test visualize_degree_distribution
        viz.visualize_degree_distribution(graph)
        
        # Test visualize_metrics_dashboard
        metrics = {"num_nodes": 10, "num_edges": 20, "density": 0.1}
        viz.visualize_metrics_dashboard(metrics)
        
        # Test visualize_centrality_comparison
        results = {"degree": {"rankings": [{"node": "n1", "score": 0.9}]}}
        viz.visualize_centrality_comparison(results)

    # --- TemporalVisualizer Tests ---
    def test_temporal_visualizer(self):
        viz = TemporalVisualizer()
        
        # Test visualize_timeline
        temporal_data = {"events": [{"timestamp": "2023-01-01", "type": "create", "label": "E1"}], "timestamps": ["2023-01-01"]}
        viz.visualize_timeline(temporal_data)
        
        # Test visualize_temporal_patterns
        patterns = [{"pattern_type": "trend", "start_time": "2023", "end_time": "2024", "entities": ["e1"]}]
        viz.visualize_temporal_patterns(patterns)
        
        # Test visualize_snapshot_comparison
        snapshots = {"2023": {"entities": ["e1"], "relationships": []}}
        viz.visualize_snapshot_comparison(snapshots)
        
        # Test visualize_version_history
        history = [{"version": "v1", "date": "2023-01-01"}]
        viz.visualize_version_history(history)
        
        # Test visualize_metrics_evolution
        metrics_history = {"nodes": [10, 20]}
        timestamps = ["2023", "2024"]
        viz.visualize_metrics_evolution(metrics_history, timestamps)

    # --- EmbeddingVisualizer Tests ---
    def test_embedding_visualizer(self):
        viz = EmbeddingVisualizer()
        embeddings = np.random.rand(10, 10)
        
        # Test visualize_2d_projection (mock UMAP/PCA)
        with patch('semantica.visualization.embedding_visualizer.umap', MagicMock()) as mock_umap:
             mock_umap.UMAP.return_value.fit_transform.return_value = np.random.rand(10, 2)
             viz.visualize_2d_projection(embeddings)
             
        # Test visualize_similarity_heatmap
        viz.visualize_similarity_heatmap(embeddings[:5]) # smaller for heatmap
        
        # Test visualize_clustering
        clusters = [0, 1, 0, 1, 0, 1, 0, 1, 0, 1]
        with patch('semantica.visualization.embedding_visualizer.umap', MagicMock()) as mock_umap:
             mock_umap.UMAP.return_value.fit_transform.return_value = np.random.rand(10, 2)
             viz.visualize_clustering(embeddings, clusters)

if __name__ == '__main__':
    unittest.main()
