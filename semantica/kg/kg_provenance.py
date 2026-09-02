"""
Provenance-enabled wrappers for knowledge graph operations and algorithms.

Provides provenance tracking for KG operations including:
- Graph construction and entity/relationship management
- Node embeddings (node2vec, deepwalk, word2vec)
- Similarity calculations (cosine, euclidean, manhattan, correlation)
- Path finding (BFS, Dijkstra, A*, all shortest paths)
- Link prediction (preferential attachment, jaccard, adamic_adar)
- Centrality measures (degree, betweenness, closeness, eigenvector, PageRank)
- Community detection (label propagation, louvain)
- Connectivity analysis and graph properties

Tracks: graph operations, algorithm executions, parameters, timestamps, and metadata.

Usage:
    from semantica.kg.kg_provenance import GraphBuilderWithProvenance, AlgorithmTrackerWithProvenance
    
    # Graph building with provenance
    graph_builder = GraphBuilderWithProvenance(provenance=True)
    result = graph_builder.build_single_source(graph_data)
    
    # Algorithm tracking with provenance
    tracker = AlgorithmTrackerWithProvenance(provenance=True)
    
    # Track embedding computation
    embed_id = tracker.track_embedding_computation(
        graph=networkx_graph,
        algorithm='node2vec',
        embeddings=computed_embeddings,
        parameters={'embedding_dimension': 128, 'walk_length': 80}
    )
    
    # Track similarity analysis
    sim_id = tracker.track_similarity_calculation(
        embeddings=node_embeddings,
        query_embedding=query_vector,
        similarities=similarity_scores,
        method='cosine'
    )

Supported Algorithms:
- Node Embeddings: node2vec, deepwalk, word2vec, line
- Similarity Metrics: cosine, euclidean, manhattan, correlation, jaccard
- Path Finding: BFS, Dijkstra, A*, all shortest paths, k-shortest paths
- Link Prediction: preferential attachment, jaccard, adamic_adar, resource allocation
- Centrality Measures: degree, betweenness, closeness, eigenvector, PageRank
- Community Detection: label propagation, louvain, leiden, infomap
- Graph Analysis: connected components, graph density, clustering coefficient

Author: Semantica Contributors
License: MIT
Version: 1.0.0
"""

from typing import Any, Dict, List, Optional
import uuid
import time

from ..utils.helpers import utc_now_iso


class GraphBuilderWithProvenance:
    """
    Graph builder with provenance tracking.
    
    Tracks graph construction operations including entity/relationship creation,
    source data lineage, construction parameters, and execution metadata.
    
    Methods:
        build_single_source: Build graph from single data source with provenance
        build: Build graph from multiple sources with provenance
        __getattr__: Delegate other methods to underlying GraphBuilder
    
    Example:
        builder = GraphBuilderWithProvenance(provenance=True)
        result = builder.build_single_source({
            'entities': [{'id': 'person1', 'type': 'Person'}],
            'relationships': [{'source': 'person1', 'target': 'person2', 'type': 'KNOWS'}]
        })
    """
    
    def __init__(
        self,
        provenance: bool = False,
        agent_id: Optional[str] = None,
        is_automated: bool = True,
        **config,
    ):
        from .graph_builder import GraphBuilder

        self.provenance = provenance
        self._builder = GraphBuilder(**config)
        self._prov_manager = None
        self._agent_id = agent_id or self.__class__.__name__
        self._is_automated = is_automated

        if provenance:
            try:
                from semantica.provenance import ProvenanceManager
                self._prov_manager = ProvenanceManager()
            except ImportError:
                self.provenance = False
    
    def build(self, sources, **kwargs):
        """Build graph with provenance tracking."""
        activity_started_at_time = utc_now_iso()
        # Track the build operation (recorded before the build runs, so it
        # has no end time yet — this is the "in progress" marker).
        if self.provenance and self._prov_manager:
            build_id = f"graph_build_{uuid.uuid4().hex[:8]}"
            self._prov_manager.track_entity(
                entity_id=build_id,
                source="graph_construction",
                agent_id=self._agent_id,
                agent_type="software_agent",
                is_automated=self._is_automated,
                activity_started_at_time=activity_started_at_time,
                metadata={
                    "entity_type": "graph_build_operation",
                    "operation": "build_graph",
                    "sources_count": len(sources) if isinstance(sources, list) else 1,
                    "timestamp": time.time()
                }
            )

        result = self._builder.build(sources, **kwargs)
        activity_ended_at_time = utc_now_iso()

        # Track individual entities and relationships if available
        if self.provenance and self._prov_manager and hasattr(result, 'get'):
            try:
                # Try to extract entities and relationships for tracking
                entities = result.get('entities', [])
                relationships = result.get('relationships', [])

                for entity in entities:
                    entity_id = entity.get('id') or str(entity.get('name', ''))
                    if entity_id:
                        self._prov_manager.track_entity(
                            entity_id=entity_id,
                            source="graph_construction",
                            entity_type="graph_entity",
                            agent_id=self._agent_id,
                            agent_type="software_agent",
                            is_automated=self._is_automated,
                            activity_started_at_time=activity_started_at_time,
                            activity_ended_at_time=activity_ended_at_time,
                            metadata={
                                "operation": "build_entity",
                                "entity_type": entity.get('type'),
                                "build_id": build_id,
                                "timestamp": time.time()
                            }
                        )

                for relationship in relationships:
                    rel_id = relationship.get('id') or f"{relationship.get('source', '')}-{relationship.get('target', '')}"
                    if rel_id:
                        self._prov_manager.track_entity(
                            entity_id=rel_id,
                            source="graph_construction",
                            entity_type="graph_relationship",
                            agent_id=self._agent_id,
                            agent_type="software_agent",
                            is_automated=self._is_automated,
                            activity_started_at_time=activity_started_at_time,
                            activity_ended_at_time=activity_ended_at_time,
                            metadata={
                                "operation": "build_relationship",
                                "relationship_type": relationship.get('type'),
                                "build_id": build_id,
                                "timestamp": time.time()
                            }
                        )
            except Exception as e:
                # Don't fail the build if provenance tracking fails
                pass

        return result

    def build_single_source(self, kg_data, **kwargs):
        """Build graph from single source with provenance tracking."""
        activity_started_at_time = utc_now_iso()
        # Track the build operation (recorded before the build runs, so it
        # has no end time yet — this is the "in progress" marker).
        if self.provenance and self._prov_manager:
            build_id = f"graph_build_single_{uuid.uuid4().hex[:8]}"
            self._prov_manager.track_entity(
                entity_id=build_id,
                source="graph_construction",
                agent_id=self._agent_id,
                agent_type="software_agent",
                is_automated=self._is_automated,
                activity_started_at_time=activity_started_at_time,
                metadata={
                    "entity_type": "graph_build_operation",
                    "operation": "build_single_source",
                    "timestamp": time.time()
                }
            )

        result = self._builder.build_single_source(kg_data, **kwargs)
        activity_ended_at_time = utc_now_iso()

        # Track entities and relationships if available
        if self.provenance and self._prov_manager and isinstance(result, dict):
            try:
                entities = result.get('entities', [])
                relationships = result.get('relationships', [])

                for entity in entities:
                    entity_id = entity.get('id') or str(entity.get('name', ''))
                    if entity_id:
                        self._prov_manager.track_entity(
                            entity_id=entity_id,
                            source="graph_construction",
                            entity_type="graph_entity",
                            agent_id=self._agent_id,
                            agent_type="software_agent",
                            is_automated=self._is_automated,
                            activity_started_at_time=activity_started_at_time,
                            activity_ended_at_time=activity_ended_at_time,
                            metadata={
                                "operation": "build_entity",
                                "entity_type": entity.get('type'),
                                "build_id": build_id,
                                "timestamp": time.time()
                            }
                        )
                
                for relationship in relationships:
                    rel_id = relationship.get('id') or f"{relationship.get('source', '')}-{relationship.get('target', '')}"
                    if rel_id:
                        self._prov_manager.track_entity(
                            entity_id=rel_id,
                            source="graph_construction",
                            entity_type="graph_relationship",
                            agent_id=self._agent_id,
                            agent_type="software_agent",
                            is_automated=self._is_automated,
                            activity_started_at_time=activity_started_at_time,
                            activity_ended_at_time=activity_ended_at_time,
                            metadata={
                                "operation": "build_relationship",
                                "relationship_type": relationship.get('type'),
                                "build_id": build_id,
                                "timestamp": time.time()
                            }
                        )
            except Exception as e:
                # Don't fail the build if provenance tracking fails
                pass
        
        return result
    
    def __getattr__(self, name):
        """Delegate other methods to the underlying builder."""
        return getattr(self._builder, name)


class AlgorithmTrackerWithProvenance:
    """
    Algorithm execution tracker with provenance tracking.
    
    Tracks KG algorithm executions including embeddings, similarity, paths, links,
    centrality, communities, and graph analysis operations.
    
    Methods:
        track_embedding_computation: Track node embedding algorithm executions
        track_similarity_calculation: Track similarity analysis operations
        track_link_prediction: Track link prediction algorithm executions
        track_centrality_calculation: Track centrality measure calculations
        track_community_detection: Track community detection executions
    
    Example:
        tracker = AlgorithmTrackerWithProvenance(provenance=True)
        
        embed_id = tracker.track_embedding_computation(
            graph=networkx_graph,
            algorithm='node2vec',
            embeddings=computed_embeddings,
            parameters={'embedding_dimension': 128, 'walk_length': 80}
        )
        
        sim_id = tracker.track_similarity_calculation(
            embeddings=node_embeddings,
            query_embedding=query_vector,
            similarities=similarity_scores,
            method='cosine'
        )
    """
    
    def __init__(
        self,
        provenance: bool = False,
        agent_id: Optional[str] = None,
        is_automated: bool = True,
        **config,
    ):
        self.provenance = provenance
        self._prov_manager = None
        self._agent_id = agent_id or self.__class__.__name__
        self._is_automated = is_automated

        if provenance:
            try:
                from semantica.provenance import ProvenanceManager
                self._prov_manager = ProvenanceManager()
            except ImportError:
                self.provenance = False

    def track_embedding_computation(
        self,
        graph: Any,
        algorithm: str,
        embeddings: Dict[str, List[float]],
        parameters: Dict[str, Any],
        source: str = None,
        **kwargs
    ):
        """
        Track node embedding algorithm computation with provenance.
        
        Args:
            graph: Input graph (NetworkX or similar format)
            algorithm: Embedding algorithm name (e.g., 'node2vec', 'deepwalk')
            embeddings: Computed node embeddings {node_id: embedding_vector}
            parameters: Algorithm parameters (embedding_dimension, walk_length, etc.)
            source: Source identifier for provenance tracking
        
        Returns:
            str: Execution ID for tracking and reproducibility
        """
        if self.provenance and self._prov_manager:
            execution_id = f"embedding_{uuid.uuid4().hex[:8]}"
            
            # Track the execution
            self._prov_manager.track_entity(
                entity_id=execution_id,
                source=source or "algorithm_execution",
                agent_id=self._agent_id,
                agent_type="software_agent",
                is_automated=self._is_automated,
                activity_started_at_time=kwargs.get("activity_started_at_time"),
                activity_ended_at_time=kwargs.get("activity_ended_at_time"),
                metadata={
                    "entity_type": "embedding_computation",
                    "algorithm": algorithm,
                    "parameters": parameters,
                    "input_data_type": type(graph).__name__,
                    "output_data_type": "embeddings",
                    "node_count": len(embeddings),
                    "embedding_dimension": (len(next(iter(embeddings.values()))) if embeddings and hasattr(next(iter(embeddings.values())), '__len__') else 0),
                    "timestamp": time.time()
                }
            )
            
            # Track each embedding as separate entity
            for node_id, embedding_vector in embeddings.items():
                self._prov_manager.track_entity(
                    entity_id=f"embedding_{node_id}",
                    source=source or "algorithm_execution",
                    agent_id=self._agent_id,
                    agent_type="software_agent",
                    is_automated=self._is_automated,
                    activity_started_at_time=kwargs.get("activity_started_at_time"),
                    activity_ended_at_time=kwargs.get("activity_ended_at_time"),
                    metadata={
                        "entity_type": "node_embedding",
                        "algorithm": algorithm,
                        "node_id": node_id,
                        "embedding_dimension": len(embedding_vector) if hasattr(embedding_vector, '__len__') else 0,
                        "execution_id": execution_id,
                        "timestamp": time.time()
                    }
                )
            
            return execution_id
        return None
    
    def track_similarity_calculation(
        self,
        embeddings: Dict[str, List[float]],
        query_embedding: List[float],
        similarities: Dict[str, float],
        method: str,
        source: str = None,
        **kwargs
    ):
        """
        Track similarity calculation analysis with provenance.
        
        Args:
            embeddings: Node embeddings {node_id: embedding_vector}
            query_embedding: Query embedding vector for similarity comparison
            similarities: Computed similarity scores {node_id: similarity_score}
            method: Similarity method ('cosine', 'euclidean', 'manhattan', 'correlation')
            source: Source identifier for provenance tracking
        
        Returns:
            str: Execution ID for tracking and reproducibility
        """
        if self.provenance and self._prov_manager:
            execution_id = f"similarity_{uuid.uuid4().hex[:8]}"
            
            # Track the execution
            self._prov_manager.track_entity(
                entity_id=execution_id,
                source=source or "algorithm_execution",
                agent_id=self._agent_id,
                agent_type="software_agent",
                is_automated=self._is_automated,
                activity_started_at_time=kwargs.get("activity_started_at_time"),
                activity_ended_at_time=kwargs.get("activity_ended_at_time"),
                metadata={
                    "entity_type": "similarity_calculation",
                    "algorithm": f"similarity_{method}",
                    "method": method,
                    "input_data_type": "embeddings",
                    "output_data_type": "similarities",
                    "embeddings_count": len(embeddings),
                    "similarities_count": len(similarities),
                    "query_dimension": len(query_embedding),
                    "timestamp": time.time()
                }
            )
            
            # Track similarity results
            for node_id, similarity_score in similarities.items():
                self._prov_manager.track_entity(
                    entity_id=f"similarity_{node_id}_{execution_id}",
                    source=source or "algorithm_execution",
                    agent_id=self._agent_id,
                    agent_type="software_agent",
                    is_automated=self._is_automated,
                    activity_started_at_time=kwargs.get("activity_started_at_time"),
                    activity_ended_at_time=kwargs.get("activity_ended_at_time"),
                    metadata={
                        "entity_type": "similarity_result",
                        "method": method,
                        "node_id": node_id,
                        "similarity_score": similarity_score,
                        "execution_id": execution_id,
                        "timestamp": time.time()
                    }
                )
            
            return execution_id
        return None
    
    def track_link_prediction(
        self,
        graph: Any,
        predictions: List[tuple],
        method: str,
        parameters: Dict[str, Any],
        source: str = None,
        **kwargs
    ):
        """Track link prediction with provenance."""
        if self.provenance and self._prov_manager:
            execution_id = f"link_prediction_{uuid.uuid4().hex[:8]}"
            
            # Track the execution
            self._prov_manager.track_entity(
                entity_id=execution_id,
                source=source or "algorithm_execution",
                agent_id=self._agent_id,
                agent_type="software_agent",
                is_automated=self._is_automated,
                activity_started_at_time=kwargs.get("activity_started_at_time"),
                activity_ended_at_time=kwargs.get("activity_ended_at_time"),
                metadata={
                    "entity_type": "link_prediction",
                    "algorithm": f"link_prediction_{method}",
                    "method": method,
                    "input_data_type": type(graph).__name__,
                    "output_data_type": "predictions",
                    "predictions_count": len(predictions),
                    "parameters": parameters,
                    "timestamp": time.time()
                }
            )
            
            # Track each prediction
            for i, (node1, node2, score) in enumerate(predictions):
                self._prov_manager.track_entity(
                    entity_id=f"prediction_{execution_id}_{i}",
                    source=source or "algorithm_execution",
                    agent_id=self._agent_id,
                    agent_type="software_agent",
                    is_automated=self._is_automated,
                    activity_started_at_time=kwargs.get("activity_started_at_time"),
                    activity_ended_at_time=kwargs.get("activity_ended_at_time"),
                    metadata={
                        "entity_type": "link_prediction_result",
                        "method": method,
                        "node1": node1,
                        "node2": node2,
                        "score": score,
                        "execution_id": execution_id,
                        "timestamp": time.time()
                    }
                )
            
            return execution_id
        return None
    
    def track_centrality_calculation(
        self,
        graph: Any,
        centrality_scores: Dict[str, float],
        method: str,
        parameters: Dict[str, Any] = None,
        source: str = None,
        **kwargs
    ):
        """
        Track centrality measure calculation with provenance.
        
        Args:
            graph: Input graph (NetworkX or similar format)
            centrality_scores: Computed centrality scores {node_id: centrality_value}
            method: Centrality method ('degree', 'betweenness', 'closeness', 'eigenvector', 'pagerank')
            parameters: Algorithm parameters (normalized, max_iter, alpha, tolerance)
            source: Source identifier for provenance tracking
        
        Returns:
            str: Execution ID for tracking and reproducibility
        """
        if self.provenance and self._prov_manager:
            execution_id = f"centrality_{uuid.uuid4().hex[:8]}"
            
            # Track the execution
            self._prov_manager.track_entity(
                entity_id=execution_id,
                source=source or "algorithm_execution",
                agent_id=self._agent_id,
                agent_type="software_agent",
                is_automated=self._is_automated,
                activity_started_at_time=kwargs.get("activity_started_at_time"),
                activity_ended_at_time=kwargs.get("activity_ended_at_time"),
                metadata={
                    "entity_type": "centrality_calculation",
                    "algorithm": f"centrality_{method}",
                    "method": method,
                    "input_data_type": type(graph).__name__,
                    "output_data_type": "centrality_scores",
                    "scores_count": len(centrality_scores),
                    "parameters": parameters,
                    "timestamp": time.time()
                }
            )
            
            # Track centrality scores
            for node_id, score in centrality_scores.items():
                self._prov_manager.track_entity(
                    entity_id=f"centrality_{node_id}_{execution_id}",
                    source=source or "algorithm_execution",
                    agent_id=self._agent_id,
                    agent_type="software_agent",
                    is_automated=self._is_automated,
                    activity_started_at_time=kwargs.get("activity_started_at_time"),
                    activity_ended_at_time=kwargs.get("activity_ended_at_time"),
                    metadata={
                        "entity_type": "centrality_score",
                        "method": method,
                        "node_id": node_id,
                        "centrality_score": score,
                        "execution_id": execution_id,
                        "timestamp": time.time()
                    }
                )
            
            return execution_id
        return None
    
    def track_community_detection(
        self,
        graph: Any,
        communities: List[List[str]],
        method: str,
        parameters: Dict[str, Any] = None,
        source: str = None,
        **kwargs
    ):
        """Track community detection with provenance."""
        if self.provenance and self._prov_manager:
            execution_id = f"community_{uuid.uuid4().hex[:8]}"
            
            # Track the execution
            self._prov_manager.track_entity(
                entity_id=execution_id,
                source=source or "algorithm_execution",
                agent_id=self._agent_id,
                agent_type="software_agent",
                is_automated=self._is_automated,
                activity_started_at_time=kwargs.get("activity_started_at_time"),
                activity_ended_at_time=kwargs.get("activity_ended_at_time"),
                metadata={
                    "entity_type": "community_detection",
                    "algorithm": f"community_detection_{method}",
                    "method": method,
                    "input_data_type": type(graph).__name__,
                    "output_data_type": "communities",
                    "communities_count": len(communities),
                    "parameters": parameters,
                    "timestamp": time.time()
                }
            )
            
            # Track communities
            for i, community in enumerate(communities):
                self._prov_manager.track_entity(
                    entity_id=f"community_{execution_id}_{i}",
                    source=source or "algorithm_execution",
                    agent_id=self._agent_id,
                    agent_type="software_agent",
                    is_automated=self._is_automated,
                    activity_started_at_time=kwargs.get("activity_started_at_time"),
                    activity_ended_at_time=kwargs.get("activity_ended_at_time"),
                    metadata={
                        "entity_type": "community",
                        "method": method,
                        "community_id": i,
                        "nodes": community,
                        "community_size": len(community),
                        "execution_id": execution_id,
                        "timestamp": time.time()
                    }
                )
            
            return execution_id
        return None

    def track_graph_construction(
        self,
        input_data: Dict[str, Any],
        output_graph: Dict[str, Any],
        entities_count: int,
        relationships_count: int,
        construction_time: float = None,
        source: str = None,
        **kwargs
    ):
        """Track graph construction with provenance."""
        if self.provenance and self._prov_manager:
            execution_id = f"graph_construction_{uuid.uuid4().hex[:8]}"
            self._prov_manager.track_entity(
                entity_id=execution_id,
                source=source or "graph_construction",
                agent_id=self._agent_id,
                agent_type="software_agent",
                is_automated=self._is_automated,
                activity_started_at_time=kwargs.get("activity_started_at_time"),
                activity_ended_at_time=kwargs.get("activity_ended_at_time"),
                metadata={
                    "entity_type": "graph_construction",
                    "entities_count": entities_count,
                    "relationships_count": relationships_count,
                    "construction_time": construction_time,
                    "timestamp": time.time()
                }
            )
            return execution_id
        return None

    def track_similarity_result(
        self,
        node_id: str,
        similarity_score: float,
        method: str,
        execution_id: str,
        source: str = None,
        **kwargs
    ):
        """Track individual similarity result with provenance."""
        if self.provenance and self._prov_manager:
            result_id = f"similarity_result_{uuid.uuid4().hex[:8]}"
            self._prov_manager.track_entity(
                entity_id=result_id,
                source=source or "similarity_result",
                agent_id=self._agent_id,
                agent_type="software_agent",
                is_automated=self._is_automated,
                activity_started_at_time=kwargs.get("activity_started_at_time"),
                activity_ended_at_time=kwargs.get("activity_ended_at_time"),
                metadata={
                    "entity_type": "similarity_result",
                    "node_id": node_id,
                    "similarity_score": similarity_score,
                    "method": method,
                    "execution_id": execution_id,
                    "timestamp": time.time()
                }
            )
            return result_id
        return None

    def track_similarity_threshold_analysis(
        self,
        execution_id: str,
        threshold: float,
        high_similarity_nodes: Dict[str, float],
        source: str = None,
        **kwargs
    ):
        """Track similarity threshold analysis with provenance."""
        if self.provenance and self._prov_manager:
            result_id = f"similarity_threshold_{uuid.uuid4().hex[:8]}"
            self._prov_manager.track_entity(
                entity_id=result_id,
                source=source or "similarity_threshold",
                agent_id=self._agent_id,
                agent_type="software_agent",
                is_automated=self._is_automated,
                activity_started_at_time=kwargs.get("activity_started_at_time"),
                activity_ended_at_time=kwargs.get("activity_ended_at_time"),
                metadata={
                    "entity_type": "similarity_threshold_analysis",
                    "execution_id": execution_id,
                    "threshold": threshold,
                    "high_similarity_count": len(high_similarity_nodes),
                    "timestamp": time.time()
                }
            )
            return result_id
        return None

    def track_entity_processing(
        self,
        entity_id: str,
        entity_type: str,
        entity_data: Dict[str, Any],
        source: str = None,
        **kwargs
    ):
        """Track entity processing with provenance."""
        if self.provenance and self._prov_manager:
            result_id = f"entity_processing_{uuid.uuid4().hex[:8]}"
            self._prov_manager.track_entity(
                entity_id=result_id,
                source=source or "entity_processing",
                agent_id=self._agent_id,
                agent_type="software_agent",
                is_automated=self._is_automated,
                activity_started_at_time=kwargs.get("activity_started_at_time"),
                activity_ended_at_time=kwargs.get("activity_ended_at_time"),
                metadata={
                    "entity_type": "entity_processing",
                    "processed_entity_id": entity_id,
                    "processed_entity_type": entity_type,
                    "timestamp": time.time()
                }
            )
            return result_id
        return None

    def track_relationship_processing(
        self,
        relationship_id: str,
        relationship_type: str,
        relationship_data: Dict[str, Any],
        source: str = None,
        **kwargs
    ):
        """Track relationship processing with provenance."""
        if self.provenance and self._prov_manager:
            result_id = f"relationship_processing_{uuid.uuid4().hex[:8]}"
            self._prov_manager.track_entity(
                entity_id=result_id,
                source=source or "relationship_processing",
                agent_id=self._agent_id,
                agent_type="software_agent",
                is_automated=self._is_automated,
                activity_started_at_time=kwargs.get("activity_started_at_time"),
                activity_ended_at_time=kwargs.get("activity_ended_at_time"),
                metadata={
                    "entity_type": "relationship_processing",
                    "processed_relationship_id": relationship_id,
                    "processed_relationship_type": relationship_type,
                    "timestamp": time.time()
                }
            )
            return result_id
        return None

    def track_path_analysis(
        self,
        graph: Any,
        paths: Dict[str, Any] = None,
        method: str = None,
        source: str = None,
        **kwargs
    ):
        """Track path analysis with provenance."""
        if self.provenance and self._prov_manager:
            result_id = f"path_analysis_{uuid.uuid4().hex[:8]}"
            self._prov_manager.track_entity(
                entity_id=result_id,
                source=source or "path_analysis",
                agent_id=self._agent_id,
                agent_type="software_agent",
                is_automated=self._is_automated,
                activity_started_at_time=kwargs.get("activity_started_at_time"),
                activity_ended_at_time=kwargs.get("activity_ended_at_time"),
                metadata={
                    "entity_type": "path_analysis",
                    "paths_count": len(paths) if paths else 0,
                    "method": method,
                    "timestamp": time.time()
                }
            )
            return result_id
        return None

    def track_path_finding(
        self,
        graph: Any,
        source_node: str = None,
        target_node: str = None,
        paths: Any = None,
        path: Any = None,
        method: str = None,
        parameters: Dict[str, Any] = None,
        source: str = None,
        **kwargs
    ):
        """Track path finding with provenance."""
        if self.provenance and self._prov_manager:
            result_id = f"path_finding_{uuid.uuid4().hex[:8]}"
            self._prov_manager.track_entity(
                entity_id=result_id,
                source=source or "path_finding",
                agent_id=self._agent_id,
                agent_type="software_agent",
                is_automated=self._is_automated,
                activity_started_at_time=kwargs.get("activity_started_at_time"),
                activity_ended_at_time=kwargs.get("activity_ended_at_time"),
                metadata={
                    "entity_type": "path_finding",
                    "source_node": source_node,
                    "target_node": target_node,
                    "method": method,
                    "timestamp": time.time()
                }
            )
            return result_id
        return None

    def track_embedding_analysis(
        self,
        embeddings: Dict[str, Any],
        analysis_results: Dict[str, Any] = None,
        source: str = None,
        **kwargs
    ):
        """Track embedding analysis with provenance."""
        if self.provenance and self._prov_manager:
            result_id = f"embedding_analysis_{uuid.uuid4().hex[:8]}"
            self._prov_manager.track_entity(
                entity_id=result_id,
                source=source or "embedding_analysis",
                agent_id=self._agent_id,
                agent_type="software_agent",
                is_automated=self._is_automated,
                activity_started_at_time=kwargs.get("activity_started_at_time"),
                activity_ended_at_time=kwargs.get("activity_ended_at_time"),
                metadata={
                    "entity_type": "embedding_analysis",
                    "embeddings_count": len(embeddings),
                    "timestamp": time.time()
                }
            )
            return result_id
        return None

    def track_connectivity_analysis(
        self,
        graph: Any,
        components: List[List[str]],
        source: str = None,
        **kwargs
    ):
        """Track connectivity analysis with provenance."""
        if self.provenance and self._prov_manager:
            result_id = f"connectivity_{uuid.uuid4().hex[:8]}"
            self._prov_manager.track_entity(
                entity_id=result_id,
                source=source or "connectivity_analysis",
                agent_id=self._agent_id,
                agent_type="software_agent",
                is_automated=self._is_automated,
                activity_started_at_time=kwargs.get("activity_started_at_time"),
                activity_ended_at_time=kwargs.get("activity_ended_at_time"),
                metadata={
                    "entity_type": "connectivity_analysis",
                    "components_count": len(components),
                    "timestamp": time.time()
                }
            )
            return result_id
        return None

    def track_cross_layer_analysis(
        self,
        graph_data: Any = None,
        cross_layer_results: Dict[str, Any] = None,
        source: str = None,
        **kwargs
    ):
        """Track cross-layer analysis with provenance."""
        if self.provenance and self._prov_manager:
            result_id = f"cross_layer_{uuid.uuid4().hex[:8]}"
            self._prov_manager.track_entity(
                entity_id=result_id,
                source=source or "cross_layer_analysis",
                agent_id=self._agent_id,
                agent_type="software_agent",
                is_automated=self._is_automated,
                activity_started_at_time=kwargs.get("activity_started_at_time"),
                activity_ended_at_time=kwargs.get("activity_ended_at_time"),
                metadata={
                    "entity_type": "cross_layer_analysis",
                    "layers_count": len(cross_layer_results) if cross_layer_results else 0,
                    "timestamp": time.time()
                }
            )
            return result_id
        return None

    def track_pipeline_summary(
        self,
        pipeline_id: str,
        execution_phases: List[str],
        execution_ids: Dict[str, str],
        total_time: float = None,
        input_data_size: int = None,
        source: str = None,
        **kwargs
    ):
        """Track pipeline summary with provenance."""
        if self.provenance and self._prov_manager:
            result_id = f"pipeline_summary_{uuid.uuid4().hex[:8]}"
            self._prov_manager.track_entity(
                entity_id=result_id,
                source=source or "pipeline_summary",
                agent_id=self._agent_id,
                agent_type="software_agent",
                is_automated=self._is_automated,
                activity_started_at_time=kwargs.get("activity_started_at_time"),
                activity_ended_at_time=kwargs.get("activity_ended_at_time"),
                metadata={
                    "entity_type": "pipeline_summary",
                    "pipeline_id": pipeline_id,
                    "phases_count": len(execution_phases),
                    "total_time": total_time,
                    "input_data_size": input_data_size,
                    "timestamp": time.time()
                }
            )
            return result_id
        return None

    def track_workflow_summary(
        self,
        master_workflow_id: str,
        execution_phases: List[str],
        execution_ids: Dict[str, str],
        total_time: float = None,
        source: str = None,
        **kwargs
    ):
        """Track workflow summary with provenance."""
        if self.provenance and self._prov_manager:
            summary_id = f"workflow_summary_{uuid.uuid4().hex[:8]}"
            self._prov_manager.track_entity(
                entity_id=summary_id,
                source=source or "workflow_summary",
                agent_id=self._agent_id,
                agent_type="software_agent",
                is_automated=self._is_automated,
                activity_started_at_time=kwargs.get("activity_started_at_time"),
                activity_ended_at_time=kwargs.get("activity_ended_at_time"),
                metadata={
                    "entity_type": "workflow_summary",
                    "master_workflow_id": master_workflow_id,
                    "execution_phases": execution_phases,
                    "phases_count": len(execution_phases),
                    "total_time": total_time,
                    "timestamp": time.time()
                }
            )
            return summary_id
        return None

    def track_link_prediction_result(
        self,
        source_node: str,
        target_node: str,
        prediction_score: float,
        method: str,
        execution_id: str,
        source: str = None,
        **kwargs
    ):
        """Track individual link prediction result with provenance."""
        if self.provenance and self._prov_manager:
            result_id = f"link_prediction_result_{uuid.uuid4().hex[:8]}"
            self._prov_manager.track_entity(
                entity_id=result_id,
                source=source or "link_prediction_result",
                agent_id=self._agent_id,
                agent_type="software_agent",
                is_automated=self._is_automated,
                activity_started_at_time=kwargs.get("activity_started_at_time"),
                activity_ended_at_time=kwargs.get("activity_ended_at_time"),
                metadata={
                    "entity_type": "link_prediction_result",
                    "source_node": source_node,
                    "target_node": target_node,
                    "prediction_score": prediction_score,
                    "method": method,
                    "execution_id": execution_id,
                    "timestamp": time.time()
                }
            )
            return result_id
        return None


    def _track_generic(self, analysis_type: str, source: str = None, **kwargs):
        """Generic tracking method for domain-specific analyses."""
        if self.provenance and self._prov_manager:
            result_id = f"{analysis_type}_{uuid.uuid4().hex[:8]}"
            self._prov_manager.track_entity(
                entity_id=result_id,
                source=source or analysis_type,
                agent_id=self._agent_id,
                agent_type="software_agent",
                is_automated=self._is_automated,
                activity_started_at_time=kwargs.get("activity_started_at_time"),
                activity_ended_at_time=kwargs.get("activity_ended_at_time"),
                metadata={"entity_type": analysis_type, "timestamp": time.time(), **{k: str(v)[:100] for k, v in kwargs.items() if not callable(v)}},
            )
            return result_id
        return None

    def track_influence_analysis(self, graph=None, source=None, **kwargs):
        return self._track_generic("influence_analysis", source=source, **kwargs)

    def track_verification_analysis(self, graph=None, source=None, **kwargs):
        return self._track_generic("verification_analysis", source=source, **kwargs)

    def track_supply_chain_paths(self, graph=None, source=None, **kwargs):
        return self._track_generic("supply_chain_paths", source=source, **kwargs)

    def track_bottleneck_analysis(self, graph=None, source=None, **kwargs):
        return self._track_generic("bottleneck_analysis", source=source, **kwargs)

    def track_quality_analysis(self, graph=None, source=None, **kwargs):
        return self._track_generic("quality_analysis", source=source, **kwargs)

    def track_lead_time_analysis(self, graph=None, source=None, **kwargs):
        return self._track_generic("lead_time_analysis", source=source, **kwargs)

    def track_cross_domain_analysis(self, graph=None, source=None, **kwargs):
        return self._track_generic("cross_domain_analysis", source=source, **kwargs)

    def track_cross_domain_similarity(self, graph=None, source=None, **kwargs):
        return self._track_generic("cross_domain_similarity", source=source, **kwargs)

    def track_collaboration_potential(self, graph=None, source=None, **kwargs):
        return self._track_generic("collaboration_potential", source=source, **kwargs)


# Convenience functions for easy access
def create_provenance_enabled_graph_builder(**config):
    """Create a provenance-enabled graph builder."""
    return GraphBuilderWithProvenance(provenance=True, **config)


def create_provenance_enabled_algorithm_tracker(**config):
    """Create a provenance-enabled algorithm tracker."""
    return AlgorithmTrackerWithProvenance(provenance=True, **config)
