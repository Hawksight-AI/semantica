"""
Simplified provenance workflow tests.

Tests provenance tracking workflows using only available methods.
"""

import pytest
import networkx as nx
import time
from datetime import datetime, timedelta
from typing import Dict, List, Any
import uuid

from semantica.kg import (
    GraphBuilderWithProvenance,
    AlgorithmTrackerWithProvenance,
    SimilarityCalculator,
    LinkPredictor,
    CentralityCalculator,
    CommunityDetector
)


def _stored(owner, entity_id):
    """Read a provenance record back. Fails if tracking only minted an ID."""
    record = owner._prov_manager.get_provenance(entity_id)
    assert record is not None, (
        f"no stored provenance for {entity_id!r} — an ID was generated without a write"
    )
    assert record.get("entity_id") == entity_id
    return record


def _assert_utc_iso(value, field="timestamp"):
    assert value, f"missing {field}"
    parsed = datetime.fromisoformat(value)
    assert parsed.tzinfo is not None, (
        f"{field}={value!r} is naive (datetime.utcnow leftover)"
    )
    assert parsed.utcoffset() == timedelta(0), f"{field}={value!r} is not UTC"
    return parsed


def _assert_tracked(owner, entity_id, source, **metadata):
    record = _stored(owner, entity_id)
    assert record["source_document"] == source
    actual = record.get("metadata") or {}
    for key, expected in metadata.items():
        assert actual.get(key) == expected, (
            f"{entity_id} metadata[{key!r}]={actual.get(key)!r}, expected {expected!r}"
        )
    _assert_utc_iso(record["timestamp"], "timestamp")
    if record.get("last_updated"):
        _assert_utc_iso(record["last_updated"], "last_updated")
    return record


class TestProvenanceWorkflowsSimple:
    """Test provenance tracking workflows with available methods."""
    
    @pytest.fixture
    def workflow_graph(self):
        """Create a graph for workflow testing."""
        graph = nx.Graph()
        graph.add_edges_from([
            ('A', 'B', {'weight': 1.0, 'type': 'friendship'}),
            ('B', 'C', {'weight': 0.8, 'type': 'friendship'}),
            ('C', 'D', {'weight': 0.9, 'type': 'friendship'}),
            ('D', 'E', {'weight': 0.7, 'type': 'friendship'}),
            ('E', 'F', {'weight': 0.6, 'type': 'friendship'}),
            ('F', 'A', {'weight': 0.5, 'type': 'friendship'})
        ])
        return graph
    
    @pytest.fixture
    def workflow_embeddings(self):
        """Create embeddings for workflow testing."""
        import numpy as np
        np.random.seed(42)
        
        nodes = ['A', 'B', 'C', 'D', 'E', 'F']
        embeddings = {}
        
        for node in nodes:
            # Generate 4-dimensional embeddings
            embedding = np.random.randn(4)
            embeddings[node] = embedding.tolist()
        
        return embeddings
    
    @pytest.fixture
    def workflow_data(self):
        """Create workflow data for graph building."""
        return {
            'entities': [
                {'id': 'user1', 'type': 'User', 'name': 'Alice', 'department': 'Engineering'},
                {'id': 'user2', 'type': 'User', 'name': 'Bob', 'department': 'Marketing'},
                {'id': 'project1', 'type': 'Project', 'name': 'AI Initiative'},
                {'id': 'skill1', 'type': 'Skill', 'name': 'Python'}
            ],
            'relationships': [
                {'source': 'user1', 'target': 'project1', 'type': 'WORKS_ON', 'role': 'Lead'},
                {'source': 'user2', 'target': 'project1', 'type': 'WORKS_ON', 'role': 'Developer'},
                {'source': 'user1', 'target': 'skill1', 'type': 'HAS_SKILL', 'level': 'Expert'}
            ]
        }
    
    def test_embedding_workflow_simple(self, workflow_graph, workflow_embeddings):
        """Test simple embedding workflow with provenance."""
        tracker = AlgorithmTrackerWithProvenance(provenance=True)
        
        workflow_id = f"embedding_workflow_{uuid.uuid4().hex[:8]}"
        
        # Track embedding computation
        embed_id = tracker.track_embedding_computation(
            graph=workflow_graph,
            algorithm='node2vec',
            embeddings=workflow_embeddings,
            parameters={
                'embedding_dimension': 4,
                'walk_length': 10,
                'num_walks': 5,
                'p': 1.0,
                'q': 1.0,
                'learning_rate': 0.025
            },
            source=workflow_id
        )
        
        _assert_tracked(
            tracker,
            embed_id,
            source=workflow_id,
            algorithm='node2vec',
            node_count=6,
            embedding_dimension=4,
        )
        assert embed_id.startswith('embedding_')
        for node_id in workflow_embeddings:
            node_record = _stored(tracker, f"embedding_{node_id}")
            assert node_record['metadata']['execution_id'] == embed_id
            assert node_record['metadata']['node_id'] == node_id
    
    def test_similarity_workflow_simple(self, workflow_embeddings):
        """Test simple similarity workflow with provenance."""
        tracker = AlgorithmTrackerWithProvenance(provenance=True)
        sim_calc = SimilarityCalculator()
        
        workflow_id = f"similarity_workflow_{uuid.uuid4().hex[:8]}"
        
        # Calculate similarities
        query_embedding = [0.5, 0.5, 0.5, 0.5]
        similarities = sim_calc.batch_similarity(
            embeddings=workflow_embeddings,
            query_embedding=query_embedding,
            method='cosine',
            top_k=3
        )
        
        # Track similarity calculation
        sim_id = tracker.track_similarity_calculation(
            embeddings=workflow_embeddings,
            query_embedding=query_embedding,
            similarities=similarities,
            method='cosine',
            source=workflow_id
        )
        
        _assert_tracked(
            tracker,
            sim_id,
            source=workflow_id,
            method='cosine',
            similarities_count=len(similarities),
        )
        assert sim_id.startswith('similarity_')
        assert len(similarities) == 3
    
    def test_link_prediction_workflow_simple(self, workflow_graph):
        """Test simple link prediction workflow with provenance."""
        tracker = AlgorithmTrackerWithProvenance(provenance=True)
        link_predictor = LinkPredictor()
        
        workflow_id = f"link_prediction_workflow_{uuid.uuid4().hex[:8]}"
        
        # Predict links
        predictions = link_predictor.predict_links(
            graph=workflow_graph,
            method='preferential_attachment',
            top_k=5
        )
        
        # Track link prediction
        link_id = tracker.track_link_prediction(
            graph=workflow_graph,
            predictions=predictions,
            method='preferential_attachment',
            parameters={'top_k': 5},
            source=workflow_id
        )
        
        _assert_tracked(
            tracker,
            link_id,
            source=workflow_id,
            method='preferential_attachment',
            predictions_count=len(predictions),
        )
        assert link_id.startswith('link_prediction_')
        assert len(predictions) >= 1
    
    def test_centrality_workflow_simple(self, workflow_graph):
        """Test simple centrality workflow with provenance."""
        tracker = AlgorithmTrackerWithProvenance(provenance=True)
        centrality_calc = CentralityCalculator()
        
        workflow_id = f"centrality_workflow_{uuid.uuid4().hex[:8]}"
        
        # Convert graph to dict format
        graph_dict = {
            'nodes': list(workflow_graph.nodes()),
            'edges': list(workflow_graph.edges())
        }
        
        # Calculate centrality
        degree_cent = centrality_calc.calculate_degree_centrality(graph_dict)
        
        # Track centrality calculation
        cent_id = tracker.track_centrality_calculation(
            graph=workflow_graph,
            centrality_scores=degree_cent['centrality'],
            method='degree',
            parameters={},
            source=workflow_id
        )
        
        _assert_tracked(
            tracker,
            cent_id,
            source=workflow_id,
            method='degree',
            scores_count=len(degree_cent['centrality']),
        )
        assert cent_id.startswith('centrality_')
        assert set(degree_cent['centrality']) == set(workflow_graph.nodes())
    
    def test_community_detection_workflow_simple(self, workflow_graph):
        """Test simple community detection workflow with provenance."""
        tracker = AlgorithmTrackerWithProvenance(provenance=True)
        community_detector = CommunityDetector()
        
        workflow_id = f"community_detection_workflow_{uuid.uuid4().hex[:8]}"
        
        # Convert graph to dict format
        graph_dict = {
            'nodes': list(workflow_graph.nodes()),
            'edges': list(workflow_graph.edges())
        }
        
        # Detect communities
        communities = community_detector.detect_communities(graph_dict, method='label_propagation')
        
        # Track community detection
        comm_id = tracker.track_community_detection(
            graph=workflow_graph,
            communities=communities['communities'],
            method='label_propagation',
            parameters={},
            source=workflow_id
        )
        
        _assert_tracked(
            tracker,
            comm_id,
            source=workflow_id,
            method='label_propagation',
            communities_count=len(communities['communities']),
        )
        assert comm_id.startswith('community_')
        assert len(communities['communities']) >= 1
    
    def test_graph_construction_workflow_simple(self, workflow_data):
        """Test simple graph construction workflow with provenance."""
        builder = GraphBuilderWithProvenance(provenance=True)
        tracker = AlgorithmTrackerWithProvenance(provenance=True)
        
        workflow_id = f"graph_construction_workflow_{uuid.uuid4().hex[:8]}"
        
        # Build graph
        graph_result = builder.build_single_source(workflow_data)
        
        # Verify graph construction
        assert 'entities' in graph_result
        assert 'relationships' in graph_result
        assert len(graph_result['entities']) == 4
        assert len(graph_result['relationships']) == 3
        
        construction_id = tracker.track_graph_construction(
            input_data=workflow_data,
            output_graph=graph_result,
            entities_count=len(graph_result['entities']),
            relationships_count=len(graph_result['relationships']),
            construction_time=0.0,
            source=workflow_id
        )
        _assert_tracked(
            tracker,
            construction_id,
            source=workflow_id,
            entity_type='graph_construction',
            entities_count=4,
            relationships_count=3,
        )
        assert construction_id.startswith('graph_construction_')
        for entity in graph_result['entities']:
            built = _stored(builder, entity['id'])
            assert built['metadata']['operation'] == 'build_entity'
            _assert_utc_iso(built['activity_started_at_time'], 'activity_started_at_time')
    
    def test_comprehensive_workflow_simple(self, workflow_data, workflow_graph, workflow_embeddings):
        """Test comprehensive workflow with all available methods."""
        # Initialize components
        builder = GraphBuilderWithProvenance(provenance=True)
        tracker = AlgorithmTrackerWithProvenance(provenance=True)
        sim_calc = SimilarityCalculator()
        link_predictor = LinkPredictor()
        centrality_calc = CentralityCalculator()
        community_detector = CommunityDetector()
        
        master_workflow_id = f"comprehensive_workflow_{uuid.uuid4().hex[:8]}"
        execution_ids = {}
        
        # Phase 1: Graph Construction
        graph_result = builder.build_single_source(workflow_data)
        
        construction_id = tracker.track_graph_construction(
            input_data=workflow_data,
            output_graph=graph_result,
            entities_count=len(graph_result['entities']),
            relationships_count=len(graph_result['relationships']),
            construction_time=0.0,
            source=master_workflow_id
        )
        execution_ids['construction'] = construction_id
        
        # Phase 2: Embedding Computation
        embed_id = tracker.track_embedding_computation(
            graph=workflow_graph,
            algorithm='node2vec',
            embeddings=workflow_embeddings,
            parameters={'dim': 4, 'walk_length': 10},
            source=master_workflow_id
        )
        execution_ids['embedding'] = embed_id
        
        # Phase 3: Similarity Analysis
        query_embedding = [0.5, 0.5, 0.5, 0.5]
        similarities = sim_calc.batch_similarity(
            embeddings=workflow_embeddings,
            query_embedding=query_embedding,
            method='cosine',
            top_k=3
        )
        
        sim_id = tracker.track_similarity_calculation(
            embeddings=workflow_embeddings,
            query_embedding=query_embedding,
            similarities=similarities,
            method='cosine',
            source=master_workflow_id
        )
        execution_ids['similarity'] = sim_id
        
        # Phase 4: Link Prediction
        predictions = link_predictor.predict_links(
            graph=workflow_graph,
            method='preferential_attachment',
            top_k=5
        )
        
        link_id = tracker.track_link_prediction(
            graph=workflow_graph,
            predictions=predictions,
            method='preferential_attachment',
            parameters={'top_k': 5},
            source=master_workflow_id
        )
        execution_ids['link_prediction'] = link_id
        
        # Phase 5: Centrality Analysis
        graph_dict = {
            'nodes': list(workflow_graph.nodes()),
            'edges': list(workflow_graph.edges())
        }
        
        degree_cent = centrality_calc.calculate_degree_centrality(graph_dict)
        cent_id = tracker.track_centrality_calculation(
            graph=workflow_graph,
            centrality_scores=degree_cent['centrality'],
            method='degree',
            parameters={},
            source=master_workflow_id
        )
        execution_ids['centrality'] = cent_id
        
        # Phase 6: Community Detection
        communities = community_detector.detect_communities(graph_dict, method='label_propagation')
        comm_id = tracker.track_community_detection(
            graph=workflow_graph,
            communities=communities['communities'],
            method='label_propagation',
            parameters={},
            source=master_workflow_id
        )
        execution_ids['community_detection'] = comm_id
        
        expected = {
            'construction': ('graph_construction_', 'graph_construction'),
            'embedding': ('embedding_', 'embedding_computation'),
            'similarity': ('similarity_', 'similarity_calculation'),
            'link_prediction': ('link_prediction_', 'link_prediction'),
            'centrality': ('centrality_', 'centrality_calculation'),
            'community_detection': ('community_', 'community_detection'),
        }
        assert len(execution_ids) == 6
        for phase, exec_id in execution_ids.items():
            prefix, entity_type = expected[phase]
            assert exec_id.startswith(prefix)
            _assert_tracked(
                tracker,
                exec_id,
                source=master_workflow_id,
                entity_type=entity_type,
            )
        assert len(set(execution_ids.values())) == len(execution_ids)
    
    def test_provenance_data_integrity_simple(self, workflow_graph, workflow_embeddings):
        """Test provenance data integrity with available methods."""
        tracker = AlgorithmTrackerWithProvenance(provenance=True)
        
        workflow_id = f"integrity_test_{uuid.uuid4().hex[:8]}"
        
        # Track multiple operations
        operations = []
        
        # Operation 1: Embedding computation
        embed_id = tracker.track_embedding_computation(
            graph=workflow_graph,
            algorithm='node2vec',
            embeddings=workflow_embeddings,
            parameters={'dim': 4},
            source=workflow_id
        )
        operations.append(('embedding', embed_id))
        
        # Operation 2: Similarity calculation
        sim_id = tracker.track_similarity_calculation(
            embeddings=workflow_embeddings,
            query_embedding=[0.5, 0.5, 0.5, 0.5],
            similarities={'A': 0.9, 'B': 0.8},
            method='cosine',
            source=workflow_id
        )
        operations.append(('similarity', sim_id))
        
        # Operation 3: Link prediction
        link_id = tracker.track_link_prediction(
            graph=workflow_graph,
            predictions=[('A', 'C', 0.7)],
            method='preferential_attachment',
            parameters={},
            source=workflow_id
        )
        operations.append(('link_prediction', link_id))
        
        expected = {
            'embedding': 'embedding_computation',
            'similarity': 'similarity_calculation',
            'link_prediction': 'link_prediction',
        }
        for op_type, op_id in operations:
            _assert_tracked(
                tracker,
                op_id,
                source=workflow_id,
                entity_type=expected[op_type],
            )
        assert len(set(op_id for _, op_id in operations)) == 3
    
    def test_provenance_error_recovery_simple(self):
        """Test provenance system error recovery."""
        # Test graceful degradation
        tracker_no_prov = AlgorithmTrackerWithProvenance(provenance=False)
        
        result = tracker_no_prov.track_embedding_computation(
            graph={'nodes': [], 'edges': []},
            algorithm='test',
            embeddings={},
            parameters={}
        )
        
        assert result is None
        assert tracker_no_prov._prov_manager is None

        tracker = AlgorithmTrackerWithProvenance(provenance=True)
        result = tracker.track_embedding_computation(
            graph=None,
            algorithm='test',
            embeddings={},
            parameters={},
            source='error_recovery'
        )
        _assert_tracked(
            tracker,
            result,
            source='error_recovery',
            algorithm='test',
            input_data_type='NoneType',
            node_count=0,
        )


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
