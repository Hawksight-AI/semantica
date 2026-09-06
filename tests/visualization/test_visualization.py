import unittest
from unittest.mock import MagicMock, patch

from semantica.visualization.kg_visualizer import KGVisualizer
from semantica.visualization.ontology_visualizer import OntologyVisualizer
from semantica.visualization.utils.color_schemes import ColorScheme

class TestVisualization(unittest.TestCase):

    def setUp(self):
        self.mock_logger = MagicMock()
        self.mock_tracker = MagicMock()
        
        self.logger_patcher = patch('semantica.visualization.kg_visualizer.get_logger', return_value=self.mock_logger)
        self.tracker_patcher = patch('semantica.visualization.kg_visualizer.get_progress_tracker', return_value=self.mock_tracker)
        
        self.logger_patcher_ov = patch('semantica.visualization.ontology_visualizer.get_logger', return_value=self.mock_logger)
        self.tracker_patcher_ov = patch('semantica.visualization.ontology_visualizer.get_progress_tracker', return_value=self.mock_tracker)
        
        self.logger_patcher.start()
        self.tracker_patcher.start()
        self.logger_patcher_ov.start()
        self.tracker_patcher_ov.start()

    def tearDown(self):
        self.logger_patcher.stop()
        self.tracker_patcher.stop()
        self.logger_patcher_ov.stop()
        self.tracker_patcher_ov.stop()

    def test_kg_visualizer_initialization(self):
        viz = KGVisualizer(layout="force", color_scheme="default")
        self.assertIsInstance(viz, KGVisualizer)
        self.assertEqual(viz.layout_type, "force")
        self.assertEqual(viz.color_scheme, ColorScheme.DEFAULT)

    def test_ontology_visualizer_initialization(self):
        viz = OntologyVisualizer(color_scheme="default")
        self.assertIsInstance(viz, OntologyVisualizer)
        self.assertEqual(viz.color_scheme, ColorScheme.DEFAULT)

    @patch('semantica.visualization.kg_visualizer.ForceDirectedLayout')
    @patch('semantica.visualization.kg_visualizer.HierarchicalLayout')
    @patch('semantica.visualization.kg_visualizer.CircularLayout')
    def test_kg_visualizer_layouts_init(self, mock_circ, mock_hier, mock_force):
        viz = KGVisualizer()
        mock_force.assert_called()
        mock_hier.assert_called()
        mock_circ.assert_called()

    # We can add more specific tests if we know the methods. 
    # Since we mocked the heavy libraries, we can try calling visualize methods
    # provided we mock the internal data processing or if they handle empty data gracefully.
    
    def test_kg_visualizer_methods_existence(self):
        viz = KGVisualizer()
        self.assertTrue(hasattr(viz, 'visualize_network'))
        # Add other methods based on file reading: 
        # visualize_communities, visualize_centrality, visualize_entity_types, visualize_relationship_matrix

    def test_ontology_visualizer_methods_existence(self):
        viz = OntologyVisualizer()
        self.assertTrue(hasattr(viz, 'visualize_hierarchy'))
        # visualize_properties, visualize_structure, visualize_class_property_matrix, visualize_metrics, visualize_semantic_model

    @patch(
        'semantica.visualization.kg_visualizer.KGVisualizer._visualize_network_plotly'
    )
    def test_ontology_property_visualization_expands_multi_value_edges(
        self, mock_visualize
    ):
        viz = OntologyVisualizer()
        properties = [
            {
                "name": "name",
                "domain": ["Person", "Organization"],
                "range": ["string", "normalizedString"],
            }
        ]

        viz._visualize_properties_plotly(properties, [], "interactive", None)

        nodes, edges = mock_visualize.call_args.args[:2]
        self.assertEqual(nodes, [{"id": "name", "label": "name", "type": "property"}])
        self.assertEqual(
            edges,
            [
                {"source": "name", "target": "Person", "type": "domain"},
                {"source": "name", "target": "Organization", "type": "domain"},
                {"source": "name", "target": "string", "type": "range"},
                {
                    "source": "name",
                    "target": "normalizedString",
                    "type": "range",
                },
            ],
        )

    def test_class_property_matrix_marks_every_domain_of_a_multi_domain_property(self):
        viz = OntologyVisualizer()
        ontology = {
            "classes": [{"name": "Person"}, {"name": "Place"}],
            "properties": [
                {"name": "name", "domain": ["Person", "Place"]},
                {"name": "label", "domain": "Person"},
            ],
        }

        fig = viz.visualize_class_property_matrix(ontology)

        self.assertEqual([list(row) for row in fig.data[0].z], [[1, 1], [1, 0]])

if __name__ == '__main__':
    unittest.main()
