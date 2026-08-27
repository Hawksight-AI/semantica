"""
End-to-end tests for provenance workflows.

Tests complete provenance tracking workflows across multiple algorithms.
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


class TestProvenanceWorkflows:
    """Test provenance tracking workflows."""
    
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
            ('F', 'A', {'weight': 0.5, 'type': 'friendship'}),
            ('A', 'C', {'weight': 0.4, 'type': 'colleague'}),
            ('B', 'D', {'weight': 0.3, 'type': 'colleague'}),
            ('C', 'E', {'weight': 0.2, 'type': 'colleague'}),
            ('D', 'F', {'weight': 0.1, 'type': 'colleague'})
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
                {'id': 'user2', 'type': 'User', 'name': 'Bob', 'department': 'Engineering'},
                {'id': 'user3', 'type': 'User', 'name': 'Charlie', 'department': 'Marketing'},
                {'id': 'user4', 'type': 'User', 'name': 'Diana', 'department': 'Marketing'},
                {'id': 'project1', 'type': 'Project', 'name': 'AI Initiative'},
                {'id': 'project2', 'type': 'Project', 'name': 'Data Pipeline'},
                {'id': 'skill1', 'type': 'Skill', 'name': 'Python'},
                {'id': 'skill2', 'type': 'Skill', 'name': 'Machine Learning'}
            ],
            'relationships': [
                {'source': 'user1', 'target': 'project1', 'type': 'WORKS_ON', 'role': 'Lead'},
                {'source': 'user2', 'target': 'project1', 'type': 'WORKS_ON', 'role': 'Developer'},
                {'source': 'user3', 'target': 'project2', 'type': 'WORKS_ON', 'role': 'Lead'},
                {'source': 'user4', 'target': 'project2', 'type': 'WORKS_ON', 'role': 'Developer'},
                {'source': 'user1', 'target': 'skill1', 'type': 'HAS_SKILL', 'level': 'Expert'},
                {'source': 'user2', 'target': 'skill1', 'type': 'HAS_SKILL', 'level': 'Advanced'},
                {'source': 'user2', 'target': 'skill2', 'type': 'HAS_SKILL', 'level': 'Intermediate'},
                {'source': 'user3', 'target': 'skill2', 'type': 'HAS_SKILL', 'level': 'Expert'},
                {'source': 'user1', 'target': 'user2', 'type': 'COLLABORATES_WITH'},
                {'source': 'user3', 'target': 'user4', 'type': 'COLLABORATES_WITH'},
                {'source': 'project1', 'target': 'project2', 'type': 'RELATED_TO'},
                {'source': 'skill1', 'target': 'skill2', 'type': 'RELATED_TO'}
            ]
        }
    
    def test_graph_construction_workflow(self, workflow_data):
        """Test complete graph construction workflow with provenance."""
        builder = GraphBuilderWithProvenance(provenance=True)
        tracker = AlgorithmTrackerWithProvenance(provenance=True)
        
        workflow_id = f"graph_construction_{uuid.uuid4().hex[:8]}"
        
        # Step 1: Build graph with provenance
        start_time = time.time()
        graph_result = builder.build_single_source(workflow_data)
        build_time = time.time() - start_time
        
        # Verify graph construction
        assert 'entities' in graph_result
        assert 'relationships' in graph_result
        assert len(graph_result['entities']) == 8
        assert len(graph_result['relationships']) == 12
        
        # Step 2: Track graph construction
        construction_id = tracker.track_graph_construction(
            input_data=workflow_data,
            output_graph=graph_result,
            entities_count=len(graph_result['entities']),
            relationships_count=len(graph_result['relationships']),
            construction_time=build_time,
            source=workflow_id
        )
        
        _assert_tracked(
            tracker,
            construction_id,
            source=workflow_id,
            entity_type="graph_construction",
            entities_count=8,
            relationships_count=12,
        )
        assert construction_id.startswith('graph_construction_')

        for entity in graph_result['entities']:
            built = _stored(builder, entity['id'])
            assert built['metadata']['operation'] == 'build_entity'
            assert built['metadata']['entity_type'] == entity['type']
            _assert_utc_iso(built['activity_started_at_time'], 'activity_started_at_time')
            _assert_utc_iso(built['activity_ended_at_time'], 'activity_ended_at_time')
        
        # Step 3: Track entity processing
        processed = []
        for entity in graph_result['entities']:
            entity_id = tracker.track_entity_processing(
                entity_id=entity['id'],
                entity_type=entity['type'],
                entity_data=entity,
                source=workflow_id
            )
            _assert_tracked(
                tracker,
                entity_id,
                source=workflow_id,
                processed_entity_id=entity['id'],
                processed_entity_type=entity['type'],
            )
            processed.append(entity_id)
        assert len(processed) == 8
        assert len(set(processed)) == 8
        
        # Step 4: Track relationship processing
        rel_ids = []
        for relationship in graph_result['relationships']:
            rel_id = tracker.track_relationship_processing(
                relationship_id=f"{relationship['source']}-{relationship['target']}",
                relationship_type=relationship['type'],
                relationship_data=relationship,
                source=workflow_id
            )
            _assert_tracked(
                tracker,
                rel_id,
                source=workflow_id,
                processed_relationship_type=relationship['type'],
            )
            rel_ids.append(rel_id)
        assert len(rel_ids) == 12
        assert len(set(rel_ids)) == 12
    
    def test_embedding_workflow(self, workflow_graph, workflow_embeddings):
        """Test complete embedding workflow with provenance."""
        tracker = AlgorithmTrackerWithProvenance(provenance=True)
        
        workflow_id = f"embedding_workflow_{uuid.uuid4().hex[:8]}"
        
        # Step 1: Track embedding computation
        start_time = time.time()
        
        # Simulate embedding computation
        computed_embeddings = {}
        for node, embedding in workflow_embeddings.items():
            # Simulate some processing time
            time.sleep(0.001)
            computed_embeddings[node] = embedding
        
        computation_time = time.time() - start_time
        
        embed_id = tracker.track_embedding_computation(
            graph=workflow_graph,
            algorithm='node2vec',
            embeddings=computed_embeddings,
            parameters={
                'embedding_dimension': 4,
                'walk_length': 10,
                'num_walks': 5,
                'p': 1.0,
                'q': 1.0,
                'learning_rate': 0.025,
                'computation_time': computation_time
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
        for node_id, vector in computed_embeddings.items():
            node_record = _stored(tracker, f"embedding_{node_id}")
            assert node_record['metadata']['node_id'] == node_id
            assert node_record['metadata']['execution_id'] == embed_id
            assert node_record['metadata']['embedding_dimension'] == len(vector)
        
        # Step 2: Track embedding quality metrics
        quality_metrics = {
            'mean_norm': 1.0,
            'variance': 0.5,
            'coverage': 1.0,
            'computation_time': computation_time
        }
        
        # Track quality using the same method with different parameters
        quality_id = tracker.track_embedding_computation(
            graph=workflow_graph,
            algorithm='node2vec_quality_check',
            embeddings=computed_embeddings,
            parameters=quality_metrics,
            source=workflow_id
        )
        
        _assert_tracked(
            tracker,
            quality_id,
            source=workflow_id,
            algorithm='node2vec_quality_check',
        )
        assert quality_id != embed_id
    
    def test_similarity_analysis_workflow(self, workflow_embeddings):
        """Test complete similarity analysis workflow with provenance."""
        tracker = AlgorithmTrackerWithProvenance(provenance=True)
        sim_calc = SimilarityCalculator()
        
        workflow_id = f"similarity_workflow_{uuid.uuid4().hex[:8]}"
        
        # Step 1: Track similarity calculation
        query_embedding = [0.5, 0.5, 0.5, 0.5]
        
        start_time = time.time()
        similarities = sim_calc.batch_similarity(
            embeddings=workflow_embeddings,
            query_embedding=query_embedding,
            method='cosine',
            top_k=3
        )
        calculation_time = time.time() - start_time
        
        sim_id = tracker.track_similarity_calculation(
            embeddings=workflow_embeddings,
            query_embedding=query_embedding,
            similarities=similarities,
            method='cosine',
            calculation_time=calculation_time,
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
        
        # Step 2: Track individual similarity results
        result_ids = []
        for node_id, similarity_score in similarities.items():
            result_id = tracker.track_similarity_result(
                node_id=node_id,
                similarity_score=similarity_score,
                method='cosine',
                execution_id=sim_id,
                source=workflow_id
            )
            record = _assert_tracked(
                tracker,
                result_id,
                source=workflow_id,
                node_id=node_id,
                method='cosine',
                execution_id=sim_id,
            )
            assert record['metadata']['similarity_score'] == similarity_score
            result_ids.append(result_id)
        assert len(result_ids) == len(similarities)
        
        # Step 3: Track similarity threshold analysis
        threshold = 0.7
        high_similarity = {k: v for k, v in similarities.items() if v > threshold}
        
        threshold_id = tracker.track_similarity_threshold_analysis(
            execution_id=sim_id,
            threshold=threshold,
            high_similarity_nodes=high_similarity,
            source=workflow_id
        )
        
        _assert_tracked(
            tracker,
            threshold_id,
            source=workflow_id,
            threshold=threshold,
            execution_id=sim_id,
        )
        assert _stored(tracker, threshold_id)['metadata']['high_similarity_count'] == len(high_similarity)
    
    def test_link_prediction_workflow(self, workflow_graph):
        """Test complete link prediction workflow with provenance."""
        tracker = AlgorithmTrackerWithProvenance(provenance=True)
        link_predictor = LinkPredictor()
        
        workflow_id = f"link_prediction_workflow_{uuid.uuid4().hex[:8]}"
        
        # Step 1: Track link prediction
        methods = ['preferential_attachment', 'jaccard', 'adamic_adar']
        
        for method in methods:
            start_time = time.time()
            predictions = link_predictor.predict_links(
                graph=workflow_graph,
                method=method,
                top_k=5
            )
            prediction_time = time.time() - start_time
            
            pred_id = tracker.track_link_prediction(
                graph=workflow_graph,
                predictions=predictions,
                method=method,
                parameters={'top_k': 5},
                prediction_time=prediction_time,
                source=workflow_id
            )
            
            _assert_tracked(
                tracker,
                pred_id,
                source=workflow_id,
                method=method,
                predictions_count=len(predictions),
            )
            assert pred_id.startswith('link_prediction_')
            
            # Step 2: Track individual predictions
            for i, (source, target, score) in enumerate(predictions):
                result_id = tracker.track_link_prediction_result(
                    source_node=source,
                    target_node=target,
                    prediction_score=score,
                    method=method,
                    execution_id=pred_id,
                    source=workflow_id
                )
                record = _assert_tracked(
                    tracker,
                    result_id,
                    source=workflow_id,
                    source_node=source,
                    target_node=target,
                    method=method,
                    execution_id=pred_id,
                )
                assert record['metadata']['prediction_score'] == score
        assert len(methods) == 3
    
    def test_centrality_analysis_workflow(self, workflow_graph):
        """Test complete centrality analysis workflow with provenance."""
        tracker = AlgorithmTrackerWithProvenance(provenance=True)
        centrality_calc = CentralityCalculator()
        
        workflow_id = f"centrality_workflow_{uuid.uuid4().hex[:8]}"
        
        # Convert graph to dict format
        graph_dict = {
            'nodes': list(workflow_graph.nodes()),
            'edges': list(workflow_graph.edges())
        }
        
        # Step 1: Track centrality calculations
        centrality_methods = [
            ('degree', centrality_calc.calculate_degree_centrality),
            ('betweenness', centrality_calc.calculate_betweenness_centrality),
            ('closeness', centrality_calc.calculate_closeness_centrality),
            ('eigenvector', centrality_calc.calculate_eigenvector_centrality)
        ]
        
        tracked_methods = []
        for method_name, method_func in centrality_methods:
            try:
                result = method_func(graph_dict)
            except Exception:
                # Algorithm failure is allowed for optional methods, not for degree.
                if method_name == 'degree':
                    raise
                continue

            calculation_time = 0.0
            cent_id = tracker.track_centrality_calculation(
                graph=workflow_graph,
                centrality_scores=result['centrality'],
                method=method_name,
                parameters={},
                calculation_time=calculation_time,
                source=workflow_id
            )
            _assert_tracked(
                tracker,
                cent_id,
                source=workflow_id,
                method=method_name,
                scores_count=len(result['centrality']),
            )
            assert cent_id.startswith('centrality_')
            for node_id, score in result['centrality'].items():
                score_record = _stored(tracker, f"centrality_{node_id}_{cent_id}")
                assert score_record['metadata']['node_id'] == node_id
                assert score_record['metadata']['method'] == method_name
                assert score_record['metadata']['centrality_score'] == score
            tracked_methods.append(method_name)

        assert 'degree' in tracked_methods
        assert len(tracked_methods) >= 1
    
    def test_community_detection_workflow(self, workflow_graph):
        """Test complete community detection workflow with provenance."""
        tracker = AlgorithmTrackerWithProvenance(provenance=True)
        community_detector = CommunityDetector()
        
        workflow_id = f"community_detection_workflow_{uuid.uuid4().hex[:8]}"
        
        # Convert graph to dict format
        graph_dict = {
            'nodes': list(workflow_graph.nodes()),
            'edges': list(workflow_graph.edges())
        }
        
        # Step 1: Track community detection
        methods = ['label_propagation', 'louvain']
        
        tracked_methods = []
        for method in methods:
            try:
                result = community_detector.detect_communities(graph_dict, method=method)
            except Exception:
                if method == 'label_propagation':
                    raise
                continue

            comm_id = tracker.track_community_detection(
                graph=workflow_graph,
                communities=result['communities'],
                method=method,
                parameters={},
                detection_time=0.0,
                source=workflow_id
            )
            _assert_tracked(
                tracker,
                comm_id,
                source=workflow_id,
                method=method,
                communities_count=len(result['communities']),
            )
            assert comm_id.startswith('community_')
            for i, community in enumerate(result['communities']):
                comm_record = _stored(tracker, f"community_{comm_id}_{i}")
                assert comm_record['metadata']['community_id'] == i
                assert comm_record['metadata']['method'] == method
                assert comm_record['metadata']['nodes'] == community
            tracked_methods.append(method)

        assert 'label_propagation' in tracked_methods
    
    def test_comprehensive_provenance_workflow(self, workflow_data, workflow_graph, workflow_embeddings):
        """Test comprehensive provenance workflow combining all algorithms."""
        # Initialize all components
        builder = GraphBuilderWithProvenance(provenance=True)
        tracker = AlgorithmTrackerWithProvenance(provenance=True)
        sim_calc = SimilarityCalculator()
        link_predictor = LinkPredictor()
        centrality_calc = CentralityCalculator()
        community_detector = CommunityDetector()
        
        master_workflow_id = f"comprehensive_workflow_{uuid.uuid4().hex[:8]}"
        execution_ids = {}
        
        # Phase 1: Graph Construction
        print("Phase 1: Graph Construction")
        graph_result = builder.build_single_source(workflow_data)
        
        construction_id = tracker.track_graph_construction(
            input_data=workflow_data,
            output_graph=graph_result,
            entities_count=len(graph_result['entities']),
            relationships_count=len(graph_result['relationships']),
            construction_time=0.1,
            source=master_workflow_id
        )
        execution_ids['construction'] = construction_id
        
        # Phase 2: Embedding Computation
        print("Phase 2: Embedding Computation")
        embed_id = tracker.track_embedding_computation(
            graph=workflow_graph,
            algorithm='node2vec',
            embeddings=workflow_embeddings,
            parameters={'dim': 4, 'walk_length': 10},
            source=master_workflow_id
        )
        execution_ids['embedding'] = embed_id
        
        # Phase 3: Similarity Analysis
        print("Phase 3: Similarity Analysis")
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
        print("Phase 4: Link Prediction")
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
        print("Phase 5: Centrality Analysis")
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
        print("Phase 6: Community Detection")
        communities = community_detector.detect_communities(graph_dict, method='label_propagation')
        comm_id = tracker.track_community_detection(
            graph=workflow_graph,
            communities=communities['communities'],
            method='label_propagation',
            parameters={},
            source=master_workflow_id
        )
        execution_ids['community_detection'] = comm_id
        
        # Phase 7: Workflow Summary
        print("Phase 7: Workflow Summary")
        summary_id = tracker.track_workflow_summary(
            master_workflow_id=master_workflow_id,
            execution_phases=list(execution_ids.keys()),
            execution_ids=execution_ids,
            total_time=time.time(),
            source='comprehensive_test'
        )
        
        # Verify all execution IDs were stored with the expected payload
        assert len(execution_ids) == 6
        expected_types = {
            'construction': ('graph_construction_', 'graph_construction'),
            'embedding': ('embedding_', 'embedding_computation'),
            'similarity': ('similarity_', 'similarity_calculation'),
            'link_prediction': ('link_prediction_', 'link_prediction'),
            'centrality': ('centrality_', 'centrality_calculation'),
            'community_detection': ('community_', 'community_detection'),
        }
        for phase, exec_id in execution_ids.items():
            prefix, entity_type = expected_types[phase]
            assert exec_id.startswith(prefix)
            _assert_tracked(
                tracker,
                exec_id,
                source=master_workflow_id,
                entity_type=entity_type,
            )

        summary_record = _assert_tracked(
            tracker,
            summary_id,
            source='comprehensive_test',
            entity_type='workflow_summary',
        )
        assert summary_id.startswith('workflow_summary_')
        assert summary_record['metadata']['master_workflow_id'] == master_workflow_id

        all_ids = list(execution_ids.values()) + [summary_id]
        assert len(set(all_ids)) == len(all_ids)
    
    def test_provenance_data_integrity(self, workflow_graph, workflow_embeddings):
        """Test provenance data integrity and consistency."""
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
            'embedding': ('embedding_', 'embedding_computation', embed_id),
            'similarity': ('similarity_', 'similarity_calculation', sim_id),
            'link_prediction': ('link_prediction_', 'link_prediction', link_id),
        }
        for op_type, op_id in operations:
            prefix, entity_type, expected_id = expected[op_type]
            assert op_id == expected_id
            assert op_id.startswith(prefix)
            _assert_tracked(
                tracker,
                op_id,
                source=workflow_id,
                entity_type=entity_type,
            )

        workflow_ids = [op_id for _, op_id in operations]
        assert len(set(workflow_ids)) == len(workflow_ids)
    
    def test_provenance_error_recovery(self):
        """Test provenance system error recovery."""
        # Test graceful degradation
        tracker_no_prov = AlgorithmTrackerWithProvenance(provenance=False)
        
        result = tracker_no_prov.track_embedding_computation(
            graph={'nodes': [], 'edges': []},
            algorithm='test',
            embeddings={},
            parameters={}
        )
        
        assert result is None  # Should return None when provenance is disabled
        assert tracker_no_prov._prov_manager is None
        
        # Tracking still records an execution when the graph is None — that is
        # current production behavior, so assert the write rather than
        # "either returns or raises".
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
