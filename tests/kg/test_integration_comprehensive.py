"""
Comprehensive integration tests for KG module.

Tests integration between all KG components and algorithms.
"""

import pytest
import networkx as nx
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Any, Tuple
import time
import json

from semantica.kg import (
    GraphBuilderWithProvenance,
    AlgorithmTrackerWithProvenance,
    SimilarityCalculator,
    PathFinder,
    LinkPredictor,
    CentralityCalculator,
    CommunityDetector,
    ConnectivityAnalyzer
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


class TestComprehensiveIntegration:
    """Comprehensive integration tests for KG module."""
    
    @pytest.fixture
    def complex_graph_data(self):
        """Create complex graph data for integration testing."""
        return {
            'entities': [
                {'id': 'user1', 'type': 'User', 'name': 'Alice', 'age': 30, 'department': 'Engineering'},
                {'id': 'user2', 'type': 'User', 'name': 'Bob', 'age': 25, 'department': 'Marketing'},
                {'id': 'user3', 'type': 'User', 'name': 'Charlie', 'age': 35, 'department': 'Engineering'},
                {'id': 'user4', 'type': 'User', 'name': 'Diana', 'age': 28, 'department': 'Marketing'},
                {'id': 'user5', 'type': 'User', 'name': 'Eve', 'age': 32, 'department': 'Sales'},
                {'id': 'project1', 'type': 'Project', 'name': 'AI Platform', 'budget': 100000},
                {'id': 'project2', 'type': 'Project', 'name': 'Data Pipeline', 'budget': 75000},
                {'id': 'project3', 'type': 'Project', 'name': 'Mobile App', 'budget': 50000},
                {'id': 'skill1', 'type': 'Skill', 'name': 'Python', 'category': 'Programming'},
                {'id': 'skill2', 'type': 'Skill', 'name': 'Machine Learning', 'category': 'AI'},
                {'id': 'skill3', 'type': 'Skill', 'name': 'Data Analysis', 'category': 'Analytics'},
                {'id': 'skill4', 'type': 'Skill', 'name': 'Web Development', 'category': 'Programming'},
                {'id': 'team1', 'type': 'Team', 'name': 'AI Research', 'size': 5},
                {'id': 'team2', 'type': 'Team', 'name': 'Data Science', 'size': 4},
                {'id': 'team3', 'type': 'Team', 'name': 'Frontend Dev', 'size': 3}
            ],
            'relationships': [
                {'source': 'user1', 'target': 'project1', 'type': 'WORKS_ON', 'role': 'Lead'},
                {'source': 'user2', 'target': 'project1', 'type': 'WORKS_ON', 'role': 'Developer'},
                {'source': 'user3', 'target': 'project2', 'type': 'WORKS_ON', 'role': 'Lead'},
                {'source': 'user4', 'target': 'project2', 'type': 'WORKS_ON', 'role': 'Developer'},
                {'source': 'user5', 'target': 'project3', 'type': 'WORKS_ON', 'role': 'Lead'},
                {'source': 'user1', 'target': 'skill1', 'type': 'HAS_SKILL', 'level': 'Expert'},
                {'source': 'user1', 'target': 'skill2', 'type': 'HAS_SKILL', 'level': 'Advanced'},
                {'source': 'user2', 'target': 'skill3', 'type': 'HAS_SKILL', 'level': 'Intermediate'},
                {'source': 'user3', 'target': 'skill2', 'type': 'HAS_SKILL', 'level': 'Expert'},
                {'source': 'user4', 'target': 'skill3', 'type': 'HAS_SKILL', 'level': 'Advanced'},
                {'source': 'user5', 'target': 'skill4', 'type': 'HAS_SKILL', 'level': 'Intermediate'},
                {'source': 'user1', 'target': 'team1', 'type': 'MEMBER_OF', 'role': 'Lead'},
                {'source': 'user3', 'target': 'team1', 'type': 'MEMBER_OF', 'role': 'Member'},
                {'source': 'user2', 'target': 'team2', 'type': 'MEMBER_OF', 'role': 'Lead'},
                {'source': 'user4', 'target': 'team2', 'type': 'MEMBER_OF', 'role': 'Member'},
                {'source': 'user5', 'target': 'team3', 'type': 'MEMBER_OF', 'role': 'Lead'},
                {'source': 'project1', 'target': 'project2', 'type': 'RELATED_TO', 'relationship': 'data_flow'},
                {'source': 'project2', 'target': 'project3', 'type': 'RELATED_TO', 'relationship': 'integration'},
                {'source': 'team1', 'target': 'team2', 'type': 'COLLABORATES_WITH', 'frequency': 'weekly'},
                {'source': 'user1', 'target': 'user2', 'type': 'COLLABORATES_WITH', 'frequency': 'daily'},
                {'source': 'user3', 'target': 'user4', 'type': 'COLLABORATES_WITH', 'frequency': 'weekly'},
                {'source': 'skill1', 'target': 'skill2', 'type': 'RELATED_TO', 'relationship': 'common_usage'},
                {'source': 'skill2', 'target': 'skill3', 'type': 'RELATED_TO', 'relationship': 'data_science'},
                {'source': 'skill3', 'target': 'skill4', 'type': 'RELATED_TO', 'relationship': 'frontend_integration'}
            ]
        }
    
    @pytest.fixture
    def multi_layer_network(self):
        """Create a multi-layer network for integration testing."""
        # Create multiple layers of the network
        layers = {}
        
        # Layer 1: User-Project relationships
        user_project_graph = nx.Graph()
        user_project_graph.add_edges_from([
            ('user1', 'project1'), ('user2', 'project1'), ('user3', 'project2'),
            ('user4', 'project2'), ('user5', 'project3'), ('user1', 'project2')
        ])
        layers['user_project'] = user_project_graph
        
        # Layer 2: Skill relationships
        skill_graph = nx.Graph()
        skill_graph.add_edges_from([
            ('skill1', 'skill2'), ('skill2', 'skill3'), ('skill3', 'skill4'),
            ('skill1', 'skill3'), ('skill2', 'skill4')
        ])
        layers['skill'] = skill_graph
        
        # Layer 3: Collaboration network
        collab_graph = nx.Graph()
        collab_graph.add_edges_from([
            ('user1', 'user2'), ('user1', 'user3'), ('user2', 'user4'),
            ('user3', 'user4'), ('user4', 'user5'), ('user5', 'user1')
        ])
        layers['collaboration'] = collab_graph
        
        # Layer 4: Project dependencies
        project_graph = nx.DiGraph()
        project_graph.add_edges_from([
            ('project1', 'project2'), ('project2', 'project3')
        ])
        layers['project'] = project_graph
        
        return layers
    
    @pytest.fixture
    def realistic_embeddings(self):
        """Generate realistic embeddings for testing."""
        np.random.seed(42)
        
        # Define embedding clusters for different entity types
        cluster_centers = {
            'users': np.array([0.8, 0.2, 0.1, 0.3]),
            'projects': np.array([0.2, 0.8, 0.3, 0.1]),
            'skills': np.array([0.1, 0.3, 0.8, 0.2]),
            'teams': np.array([0.3, 0.1, 0.2, 0.8])
        }
        
        embeddings = {}
        
        # Generate embeddings for each entity type
        for entity_type, center in cluster_centers.items():
            if entity_type == 'users':
                entities = ['user1', 'user2', 'user3', 'user4', 'user5']
            elif entity_type == 'projects':
                entities = ['project1', 'project2', 'project3']
            elif entity_type == 'skills':
                entities = ['skill1', 'skill2', 'skill3', 'skill4']
            elif entity_type == 'teams':
                entities = ['team1', 'team2', 'team3']
            else:
                continue
            
            for entity in entities:
                # Generate embedding around the cluster center
                noise = np.random.randn(4) * 0.2
                embedding = center + noise
                embedding = embedding / np.linalg.norm(embedding)
                embeddings[entity] = embedding.tolist()
        
        return embeddings
    
    def test_full_pipeline_integration(self, complex_graph_data, realistic_embeddings):
        """Test full pipeline integration with all components."""
        # Initialize all components
        builder = GraphBuilderWithProvenance(provenance=True)
        tracker = AlgorithmTrackerWithProvenance(provenance=True)
        sim_calc = SimilarityCalculator()
        path_finder = PathFinder()
        link_predictor = LinkPredictor()
        centrality_calc = CentralityCalculator()
        community_detector = CommunityDetector()
        conn_analyzer = ConnectivityAnalyzer()
        
        pipeline_id = f"full_pipeline_{int(time.time())}"
        execution_ids = {}
        
        # Phase 1: Graph Construction
        print("Phase 1: Graph Construction")
        start_time = time.time()
        graph_result = builder.build_single_source(complex_graph_data)
        construction_time = time.time() - start_time
        
        assert 'entities' in graph_result
        assert 'relationships' in graph_result
        assert len(graph_result['entities']) == 15
        assert len(graph_result['relationships']) == 24
        
        construction_id = tracker.track_graph_construction(
            input_data=complex_graph_data,
            output_graph=graph_result,
            entities_count=len(graph_result['entities']),
            relationships_count=len(graph_result['relationships']),
            construction_time=construction_time,
            source=pipeline_id
        )
        execution_ids['construction'] = construction_id
        
        # Phase 2: Network Analysis
        print("Phase 2: Network Analysis")
        
        # Create network graph from relationships
        network_graph = nx.Graph()
        for rel in graph_result['relationships']:
            network_graph.add_edge(rel['source'], rel['target'])
        
        # Centrality analysis
        graph_dict = {
            'nodes': list(network_graph.nodes()),
            'edges': list(network_graph.edges())
        }
        
        degree_cent = centrality_calc.calculate_degree_centrality(graph_dict)
        cent_id = tracker.track_centrality_calculation(
            graph=network_graph,
            centrality_scores=degree_cent['centrality'],
            method='degree',
            source=pipeline_id
        )
        execution_ids['centrality'] = cent_id
        
        # Connectivity analysis
        components = conn_analyzer.find_connected_components(graph_dict)['components']
        conn_id = tracker.track_connectivity_analysis(
            graph=network_graph,
            components=components,
            source=pipeline_id
        )
        execution_ids['connectivity'] = conn_id
        
        # Community detection
        communities = community_detector.detect_communities(graph_dict, method='label_propagation')
        comm_id = tracker.track_community_detection(
            graph=network_graph,
            communities=communities['communities'],
            method='label_propagation',
            source=pipeline_id
        )
        execution_ids['community'] = comm_id
        
        # Phase 3: Embedding Analysis
        print("Phase 3: Embedding Analysis")
        
        # Similarity analysis
        query_embedding = realistic_embeddings['user1']
        similarities = sim_calc.batch_similarity(
            embeddings=realistic_embeddings,
            query_embedding=query_embedding,
            method='cosine',
            top_k=5
        )
        
        sim_id = tracker.track_similarity_calculation(
            embeddings=realistic_embeddings,
            query_embedding=query_embedding,
            similarities=similarities,
            method='cosine',
            source=pipeline_id
        )
        execution_ids['similarity'] = sim_id
        
        # Phase 4: Link Prediction
        print("Phase 4: Link Prediction")
        
        predictions = link_predictor.predict_links(
            graph=network_graph,
            method='preferential_attachment',
            top_k=10
        )
        
        link_id = tracker.track_link_prediction(
            graph=network_graph,
            predictions=predictions,
            method='preferential_attachment',
            parameters={'top_k': 10},
            source=pipeline_id
        )
        execution_ids['link_prediction'] = link_id
        
        # Phase 5: Path Analysis
        print("Phase 5: Path Analysis")
        
        # Find shortest paths between key entities
        key_nodes = ['user1', 'project1', 'skill1']
        path_results = {}
        
        for source in key_nodes:
            for target in key_nodes:
                if source != target:
                    try:
                        path = path_finder.bfs_shortest_path(network_graph, source, target)
                        if path:
                            path_results[f"{source}->{target}"] = path
                    except:
                        continue
        
        # Track path analysis
        path_id = tracker.track_path_analysis(
            graph=network_graph,
            paths=path_results,
            method='bfs_shortest_path',
            source=pipeline_id
        )
        execution_ids['path_analysis'] = path_id
        
        # Phase 6: Cross-Layer Analysis
        print("Phase 6: Cross-Layer Analysis")
        
        # Analyze relationships between different entity types
        cross_layer_results = {}
        
        # User-Project-Skill relationships
        user_projects = {}
        user_skills = {}
        project_skills = {}
        
        for entity in graph_result['entities']:
            if entity['type'] == 'User':
                user_projects[entity['id']] = []
                user_skills[entity['id']] = []
            elif entity['type'] == 'Project':
                project_skills[entity['id']] = []
        
        for rel in graph_result['relationships']:
            if rel['type'] == 'WORKS_ON':
                if rel['source'] in user_projects:
                    user_projects[rel['source']].append(rel['target'])
            elif rel['type'] == 'HAS_SKILL':
                if rel['source'] in user_skills:
                    user_skills[rel['source']].append(rel['target'])
            elif rel['type'] == 'RELATED_TO':
                if rel['source'] in project_skills:
                    project_skills[rel['source']].append(rel['target'])
        
        cross_layer_results['user_projects'] = user_projects
        cross_layer_results['user_skills'] = user_skills
        cross_layer_results['project_skills'] = project_skills
        
        # Track cross-layer analysis
        cross_layer_id = tracker.track_cross_layer_analysis(
            graph_data=graph_result,
            cross_layer_results=cross_layer_results,
            source=pipeline_id
        )
        execution_ids['cross_layer'] = cross_layer_id
        
        # Phase 7: Pipeline Summary
        print("Phase 7: Pipeline Summary")
        
        summary_id = tracker.track_pipeline_summary(
            pipeline_id=pipeline_id,
            execution_phases=list(execution_ids.keys()),
            execution_ids=execution_ids,
            total_time=time.time() - start_time,
            input_data_size=len(complex_graph_data),
            output_data_size=len(graph_result),
            source='comprehensive_integration_test'
        )
        
        expected = {
            'construction': 'graph_construction',
            'centrality': 'centrality_calculation',
            'connectivity': 'connectivity_analysis',
            'community': 'community_detection',
            'similarity': 'similarity_calculation',
            'link_prediction': 'link_prediction',
            'path_analysis': 'path_analysis',
            'cross_layer': 'cross_layer_analysis',
        }
        assert len(execution_ids) == 8
        for phase, exec_id in execution_ids.items():
            _assert_tracked(
                tracker,
                exec_id,
                source=pipeline_id,
                entity_type=expected[phase],
            )
        summary_record = _assert_tracked(
            tracker,
            summary_id,
            source='comprehensive_integration_test',
            entity_type='pipeline_summary',
            pipeline_id=pipeline_id,
            phases_count=8,
        )
        assert summary_id.startswith('pipeline_summary_')
        assert summary_record['metadata']['input_data_size'] == len(complex_graph_data)
    
    def test_multi_layer_network_analysis(self, multi_layer_network, realistic_embeddings):
        """Test multi-layer network analysis."""
        tracker = AlgorithmTrackerWithProvenance(provenance=True)
        centrality_calc = CentralityCalculator()
        community_detector = CommunityDetector()
        sim_calc = SimilarityCalculator()
        
        multi_layer_id = f"multi_layer_{int(time.time())}"
        layer_results = {}
        
        # Analyze each layer
        for layer_name, graph in multi_layer_network.items():
            print(f"Analyzing layer: {layer_name}")
            
            # Convert to dict format
            graph_dict = {
                'nodes': list(graph.nodes()),
                'edges': list(graph.edges())
            }
            
            # Centrality analysis
            if graph.number_of_nodes() > 0:
                degree_cent = centrality_calc.calculate_degree_centrality(graph_dict)
                layer_results[f"{layer_name}_centrality"] = degree_cent
                cent_id = tracker.track_centrality_calculation(
                    graph=graph,
                    centrality_scores=degree_cent['centrality'],
                    method='degree',
                    source=multi_layer_id
                )
                _assert_tracked(
                    tracker,
                    cent_id,
                    source=multi_layer_id,
                    method='degree',
                    scores_count=len(degree_cent['centrality']),
                )
            
            # Community detection
            if graph.number_of_edges() > 0:
                communities = community_detector.detect_communities(graph_dict, method='label_propagation')
                layer_results[f"{layer_name}_communities"] = communities
                comm_id = tracker.track_community_detection(
                    graph=graph,
                    communities=communities['communities'],
                    method='label_propagation',
                    source=multi_layer_id
                )
                _assert_tracked(
                    tracker,
                    comm_id,
                    source=multi_layer_id,
                    method='label_propagation',
                    communities_count=len(communities['communities']),
                )
        
        # Cross-layer similarity analysis
        print("Cross-layer similarity analysis")
        
        # Find similar entities across layers
        layer_similarities = {}
        
        for layer1_name, graph1 in multi_layer_network.items():
            for layer2_name, graph2 in multi_layer_network.items():
                if layer1_name != layer2_name:
                    # Find common nodes
                    common_nodes = set(graph1.nodes()) & set(graph2.nodes())
                    
                    if common_nodes:
                        # Calculate similarity based on network position
                        similarity_score = len(common_nodes) / max(len(graph1.nodes()), len(graph2.nodes()))
                        layer_similarities[f"{layer1_name}_{layer2_name}"] = similarity_score
        
        cross_layer_id = tracker.track_cross_layer_analysis(
            graph_data=multi_layer_network,
            cross_layer_results=layer_similarities,
            source='multi_layer_test'
        )
        _assert_tracked(
            tracker,
            cross_layer_id,
            source='multi_layer_test',
            entity_type='cross_layer_analysis',
            layers_count=len(layer_similarities),
        )
        
        # Embedding-based entity similarity
        entity_similarities = sim_calc.pairwise_similarity(realistic_embeddings)
        
        embed_id = tracker.track_embedding_analysis(
            embeddings=realistic_embeddings,
            analysis_results=entity_similarities,
            source='multi_layer_test'
        )
        _assert_tracked(
            tracker,
            embed_id,
            source='multi_layer_test',
            entity_type='embedding_analysis',
            embeddings_count=len(realistic_embeddings),
        )
        
        assert len(layer_results) > 0
        assert len(layer_similarities) > 0
        assert len(entity_similarities) > 0
    
    def test_error_handling_and_recovery(self):
        """Test error handling and recovery mechanisms."""
        tracker = AlgorithmTrackerWithProvenance(provenance=True)
        centrality_calc = CentralityCalculator()
        
        # Test with invalid graph data
        invalid_graph = {
            'nodes': [],  # Empty graph
            'edges': []
        }
        
        result = centrality_calc.calculate_degree_centrality(invalid_graph)
        assert isinstance(result, dict)
        
        # Provenance tracking with a None graph still writes a record.
        result = tracker.track_embedding_computation(
            graph=None,
            algorithm='test',
            embeddings={},
            parameters={},
            source='integration_error_recovery'
        )
        _assert_tracked(
            tracker,
            result,
            source='integration_error_recovery',
            algorithm='test',
            input_data_type='NoneType',
        )
        
        # Test graceful degradation when provenance is disabled
        tracker_no_prov = AlgorithmTrackerWithProvenance(provenance=False)
        
        result = tracker_no_prov.track_embedding_computation(
            graph=invalid_graph,
            algorithm='test',
            embeddings={},
            parameters={}
        )
        
        # Should return None when provenance is disabled
        assert result is None
        assert tracker_no_prov._prov_manager is None
    
    def test_performance_benchmarks(self, realistic_embeddings):
        """Test performance benchmarks with realistic data."""
        import time
        
        # Create larger test data
        large_graph = nx.erdos_renyi_graph(100, 0.1, seed=42)
        
        # Benchmark centrality calculation
        centrality_calc = CentralityCalculator()
        graph_dict = {
            'nodes': list(large_graph.nodes()),
            'edges': list(large_graph.edges())
        }
        
        start_time = time.time()
        degree_cent = centrality_calc.calculate_degree_centrality(graph_dict)
        centrality_time = time.time() - start_time
        
        # Benchmark similarity calculation
        sim_calc = SimilarityCalculator()
        
        # Create larger embeddings
        large_embeddings = {}
        for i in range(100):
            embedding = np.random.randn(8)
            large_embeddings[f"node_{i}"] = (embedding / np.linalg.norm(embedding)).tolist()
        
        start_time = time.time()
        similarities = sim_calc.batch_similarity(
            embeddings=large_embeddings,
            query_embedding=[0.5] * 8,
            method='cosine',
            top_k=10
        )
        similarity_time = time.time() - start_time
        
        # Benchmark link prediction
        link_predictor = LinkPredictor()
        
        start_time = time.time()
        predictions = link_predictor.predict_links(
            graph=large_graph,
            method='preferential_attachment',
            top_k=20
        )
        prediction_time = time.time() - start_time
        
        # Performance assertions
        assert centrality_time < 2.0  # Should complete within 2 seconds
        assert similarity_time < 1.0  # Should complete within 1 second
        assert prediction_time < 1.0  # Should complete within 1 second
        
        print(f"Performance benchmarks:")
        print(f"  Centrality calculation (100 nodes): {centrality_time:.3f}s")
        print(f"  Similarity calculation (100 embeddings): {similarity_time:.3f}s")
        print(f"  Link prediction (100 nodes): {prediction_time:.3f}s")
        print(f"  Graph density: {nx.density(large_graph):.3f}")
        print(f"  Average degree: {sum(dict(large_graph.degree()).values()) / len(large_graph):.1f}")
    
    def test_data_consistency_validation(self, complex_graph_data, realistic_embeddings):
        """Test data consistency validation across components."""
        # Validate graph data consistency
        entity_ids = {entity['id'] for entity in complex_graph_data['entities']}
        relationship_sources = {rel['source'] for rel in complex_graph_data['relationships']}
        relationship_targets = {rel['target'] for rel in complex_graph_data['relationships']}
        
        # All relationship sources and targets should exist as entities
        assert relationship_sources.issubset(entity_ids), "Relationship sources not found in entities"
        assert relationship_targets.issubset(entity_ids), "Relationship targets not found in entities"
        
        # Validate embedding consistency
        embedding_ids = set(realistic_embeddings.keys())
        assert embedding_ids.issubset(entity_ids), "Embedding IDs not found in entities"
        
        # Validate embedding dimensions
        embedding_dims = {len(embedding) for embedding in realistic_embeddings.values()}
        assert len(set(embedding_dims)) == 1, "Embeddings have inconsistent dimensions"
        
        # Test consistency across algorithms
        tracker = AlgorithmTrackerWithProvenance(provenance=True)
        centrality_calc = CentralityCalculator()
        sim_calc = SimilarityCalculator()
        
        # Create consistent graph from relationships
        graph = nx.Graph()
        for rel in complex_graph_data['relationships']:
            graph.add_edge(rel['source'], rel['target'])
        
        graph_dict = {
            'nodes': list(graph.nodes()),
            'edges': list(graph.edges())
        }
        
        # Calculate centrality
        degree_cent = centrality_calc.calculate_degree_centrality(graph_dict)
        
        # Calculate similarities
        query_embedding = realistic_embeddings['user1']
        similarities = sim_calc.batch_similarity(
            embeddings=realistic_embeddings,
            query_embedding=query_embedding,
            method='cosine',
            top_k=5
        )
        
        # Validate consistency
        assert set(degree_cent['centrality'].keys()) == set(graph.nodes())
        assert set(similarities.keys()).issubset(set(realistic_embeddings.keys()))
        
        # Track with provenance
        cent_id = tracker.track_centrality_calculation(
            graph=graph,
            centrality_scores=degree_cent['centrality'],
            method='degree',
            source='consistency_validation'
        )
        
        sim_id = tracker.track_similarity_calculation(
            embeddings=realistic_embeddings,
            query_embedding=query_embedding,
            similarities=similarities,
            method='cosine',
            source='consistency_validation'
        )
        
        # Verify tracking IDs
        assert cent_id is not None
        assert sim_id is not None
        assert cent_id != sim_id
        
        print("Data consistency validation completed")
        print(f"Entities: {len(entity_ids)}")
        print(f"Relationships: {len(complex_graph_data['relationships'])}")
        print(f"Embeddings: {len(realistic_embeddings)}")
        print(f"Graph nodes: {len(graph.nodes())}")
        print(f"Graph edges: {len(graph.edges())}")
    
    def test_concurrent_operations(self, realistic_embeddings):
        """Test concurrent operations and thread safety."""
        import threading
        import time
        
        # Test concurrent similarity calculations
        sim_calc = SimilarityCalculator()
        results = {}
        errors = []
        
        def calculate_similarity(thread_id):
            try:
                query_embedding = realistic_embeddings['user1']
                similarities = sim_calc.batch_similarity(
                    embeddings=realistic_embeddings,
                    query_embedding=query_embedding,
                    method='cosine',
                    top_k=3
                )
                results[thread_id] = similarities
            except Exception as e:
                errors.append(f"Thread {thread_id}: {e}")
        
        # Create multiple threads
        threads = []
        for i in range(5):
            thread = threading.Thread(target=calculate_similarity, args=(i,))
            threads.append(thread)
        
        # Start all threads
        for thread in threads:
            thread.start()
        
        # Wait for completion
        for thread in threads:
            thread.join()
        
        # Verify results
        assert len(errors) == 0, f"Errors in concurrent operations: {errors}"
        assert len(results) == 5, "Not all threads completed successfully"
        
        # Verify consistency of results
        first_result = list(results.values())[0]
        for result in results.values():
            assert set(result.keys()) == set(first_result.keys()), "Inconsistent results across threads"
        
        print("Concurrent operations test completed")
        print(f"Threads completed: {len(results)}")
        print(f"Consistent results: {len(set(tuple(sorted(r.items())) for r in results.values())) == 1}")


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
