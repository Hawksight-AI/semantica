"""
Context Retriever for Agents

This module provides comprehensive context retrieval capabilities for agents,
retrieving relevant context from memory, knowledge graphs, and vector stores
to inform decision-making. It supports hybrid retrieval combining multiple
sources for optimal context relevance with high accuracy for GraphRAG use cases.

Algorithms Used:

Vector Retrieval:
    - Vector Similarity Search: Cosine similarity search in vector space
    - Query Embedding: Embedding generation for search queries using semantic models
    - Top-K Retrieval: Top-K result selection based on similarity scores
    - Semantic Re-ranking: Query-content semantic similarity for final ranking

Graph Retrieval:
    - Semantic Entity Matching: Cosine similarity between query and entity embeddings
    - Semantic Relationship Matching: Similarity matching for relationship types and entities
    - Graph Traversal: Multi-hop graph expansion for related entities (BFS-based)
    - Query Intent Extraction: Domain-agnostic extraction of relationship verbs and question types
    - Intent-Guided Boosting: Score boosting for entities/relationships matching query intent
    - Relationship-Aware Matching: Finding entities through semantically relevant relationships
    - Adaptive Thresholding: Dynamic similarity thresholds (default 0.3) for filtering

Memory Retrieval:
    - Memory Search: Vector and keyword search in memory store
    - Conversation History: Temporal-based memory retrieval

Result Processing:
    - Score Normalization: Per-source score normalization (0-1 range) for fair comparison
    - Hybrid Weighting: Configurable hybrid_alpha (0=vector only, 1=graph only, 0.5=balanced)
    - Context Boosting: Up to 20% boost for graph results with more related entities/relationships
    - Multi-Source Boost: 20% boost for results found in both vector and graph sources
    - Semantic Re-ranking: Final ranking using 70% original score + 30% query-content similarity
    - Entity-Based Deduplication: Graph results deduplicated by entity ID with relationship merging
    - Content-Based Deduplication: Non-graph results deduplicated by content hash
    - Metadata Merging: Dictionary-based metadata merging for duplicate results
    - Entity Merging: Set-based entity deduplication with relationship preservation

Content Generation:
    - Comprehensive Entity Descriptions: Entity name, type, and metadata properties
    - Relationship Context: Direction-aware relationship formatting with target entity types
    - Multi-Relationship Formatting: Up to 5 relationships per entity with grouping by type
    - Related Entity Context: Additional context from related entities when content is sparse

Key Features:
    - Domain-Agnostic: Works across any domain (biomedical, finance, tech, legal, etc.)
    - Semantic Matching: Uses embeddings for semantic similarity instead of keyword matching
    - Hybrid Retrieval: Combines vector + graph + memory with configurable weighting
    - Query Understanding: Extracts query intent (relationship types, question types)
    - High Accuracy: Optimized for GraphRAG with multi-factor scoring and semantic re-ranking
    - Context Richness: Generates comprehensive content from graph structures
    - Graph Expansion: Multi-hop traversal following semantically relevant paths
    - Result Deduplication: Smart merging of results from multiple sources
    - Configurable Strategies: Adjustable hybrid_alpha, max_hops, similarity thresholds

Main Classes:
    - RetrievedContext: Retrieved context item data structure with content, score,
      source, metadata, related_entities, related_relationships
    - ContextRetriever: Context retriever for hybrid retrieval with GraphRAG optimization

Example Usage:
    >>> from semantica.context import ContextRetriever
    >>> retriever = ContextRetriever(
    ...     memory_store=mem, knowledge_graph=kg, vector_store=vs,
    ...     hybrid_alpha=0.6  # 60% weight on graph, 40% on vector
    ... )
    >>> results = retriever.retrieve("What drugs target COX enzymes?", max_results=5)
    >>> for result in results:
    ...     print(f"{result.content}: {result.score:.2f}")
    ...     print(f"Related entities: {len(result.related_entities)}")
    ...     print(f"Related relationships: {len(result.related_relationships)}")

Author: Semantica Contributors
License: MIT
"""

from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union

from ..utils.logging import get_logger
from ..utils.progress_tracker import get_progress_tracker
from ..vector_store.hybrid_similarity import HybridSimilarityCalculator
from ..vector_store.decision_embedding_pipeline import DecisionEmbeddingPipeline
from ..kg.path_finder import PathFinder
from ..kg.centrality_calculator import CentralityCalculator
from ..kg.community_detector import CommunityDetector
from ..kg.similarity_calculator import SimilarityCalculator
try:
    from ..kg.temporal_query import TemporalGraphQuery as _TemporalGraphQuery
    from ..kg.temporal_model import parse_temporal_value as _parse_temporal_value
    _TEMPORAL_AVAILABLE = True
except Exception:  # pragma: no cover
    _TemporalGraphQuery = None  # type: ignore[assignment,misc]
    _parse_temporal_value = None  # type: ignore[assignment]
    _TEMPORAL_AVAILABLE = False


@dataclass
class RetrievedContext:
    """Retrieved context item."""

    content: str
    score: float
    source: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    related_entities: List[Dict[str, Any]] = field(default_factory=list)
    related_relationships: List[Dict[str, Any]] = field(default_factory=list)


class ContextRetriever:
    """
    Context retriever for hybrid retrieval.

    • Retrieve context from multiple sources
    • Hybrid retrieval (vector + graph)
    • Context relevance ranking
    • Context aggregation and synthesis
    • Ontology-aware context retrieval
    • Real-time context updates
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None, **kwargs):
        """
        Initialize context retriever.

        Args:
            config: Configuration dictionary
            **kwargs: Additional configuration options:
                - memory_store: Memory store instance
                - knowledge_graph: Knowledge graph instance
                - vector_store: Vector store instance
                - use_graph_expansion: Use graph expansion (default: True)
                - max_expansion_hops: Maximum graph expansion hops (default: 2)
                - hybrid_alpha: Weight for hybrid retrieval (0=vector only, 1=graph
                  only, default: 0.5)
        """
        self.logger = get_logger("context_retriever")
        self.config = config or {}
        self.config.update(kwargs)

        self.memory_store = self.config.get("memory_store")
        self.knowledge_graph = self.config.get("knowledge_graph")
        self.vector_store = self.config.get("vector_store")

        self.use_graph_expansion = self.config.get("use_graph_expansion", True)
        self.max_expansion_hops = self.config.get("max_expansion_hops", 2)
        self.hybrid_alpha = self.config.get("hybrid_alpha", 0.5)

        # Initialize progress tracker
        self.progress_tracker = get_progress_tracker()
        # Ensure progress tracker is enabled
        if not self.progress_tracker.enabled:
            self.progress_tracker.enabled = True

        # Initialize decision-specific components
        self.hybrid_calculator = HybridSimilarityCalculator()
        self.decision_pipeline: Optional[DecisionEmbeddingPipeline] = None
        
        # Initialize KG algorithms if knowledge graph available
        if self.knowledge_graph:
            self.path_finder = PathFinder()
            self.centrality_calculator = CentralityCalculator()
            self.community_detector = CommunityDetector()
            self.similarity_calculator = SimilarityCalculator()
        else:
            self.path_finder = None
            self.centrality_calculator = None
            self.community_detector = None
            self.similarity_calculator = None
        
        # Initialize decision pipeline if vector store available
        if self.vector_store:
            self.decision_pipeline = DecisionEmbeddingPipeline(
                vector_store=self.vector_store,
                graph_store=self.knowledge_graph,
                use_graph_features=True
            )

    def retrieve(
        self,
        query: str,
        max_results: int = 5,
        use_graph_expansion: Optional[bool] = None,
        min_relevance_score: float = 0.0,
        **options,
    ) -> List[RetrievedContext]:
        """
        Retrieve relevant context for query.

        Args:
            query: Search query
            max_results: Maximum number of results
            use_graph_expansion: Use graph expansion (overrides config)
            min_relevance_score: Minimum relevance score
            **options: Additional options:
                - entity_ids: Filter by entity IDs
                - node_types: Filter by node types
                - max_hops: Maximum expansion hops

        Returns:
            List of retrieved context items
        """
        # Track context retrieval
        tracking_id = self.progress_tracker.start_tracking(
            file=None,
            module="context",
            submodule="ContextRetriever",
            message=f"Retrieving context for: {query[:50]}...",
        )

        try:
            use_expansion = (
                use_graph_expansion
                if use_graph_expansion is not None
                else self.use_graph_expansion
            )

            all_results = []

            # Vector-based retrieval
            self.progress_tracker.update_tracking(
                tracking_id, message="Retrieving from vector store..."
            )
            vector_results = self._retrieve_from_vector(query, max_results * 2)
            all_results.extend(vector_results)

            # Graph-based retrieval
            if self.knowledge_graph and use_expansion:
                self.progress_tracker.update_tracking(
                    tracking_id, message="Retrieving from knowledge graph..."
                )
                # Extract query intent for better graph traversal
                query_intent = self._extract_query_intent(query)
                graph_results = self._retrieve_from_graph(
                    query,
                    max_results * 2,
                    max_hops=options.get("max_hops", self.max_expansion_hops),
                    query_intent=query_intent,
                )
                all_results.extend(graph_results)

            # Memory-based retrieval
            if self.memory_store:
                self.progress_tracker.update_tracking(
                    tracking_id, message="Retrieving from memory..."
                )
                memory_results = self._retrieve_from_memory(query, max_results * 2)
                all_results.extend(memory_results)

            # Combine and rank results
            self.progress_tracker.update_tracking(
                tracking_id, message="Ranking and merging results..."
            )
            ranked_results = self._rank_and_merge(all_results, query)

            # Filter by minimum score
            filtered_results = [
                r for r in ranked_results if r.score >= min_relevance_score
            ]

            self.progress_tracker.stop_tracking(
                tracking_id,
                status="completed",
                message=f"Retrieved {len(filtered_results[:max_results])} results",
            )
            # Return top results
            return filtered_results[:max_results]

        except Exception as e:
            self.progress_tracker.stop_tracking(
                tracking_id, status="failed", message=str(e)
            )
            raise

    def _retrieve_from_vector(
        self, query: str, max_results: int
    ) -> List[RetrievedContext]:
        """Retrieve from vector store."""
        if not self.vector_store:
            return []

        try:
            # Simulate vector search (actual implementation would use vector_store)
            results = []

            # If vector_store has a search method
            if hasattr(self.vector_store, "search"):
                search_results = self.vector_store.search(
                    query=query, limit=max_results
                )

                for result in search_results:
                    # Handle VectorSearchResult object or dict
                    if hasattr(result, "content"):
                        content = result.content
                        score = result.score
                        source = f"vector:{result.id}" if hasattr(result, 'id') else "vector:unknown"
                        metadata = result.metadata or {}
                    else:
                        metadata = result.get("metadata", {})
                        content = result.get("content") or metadata.get("content", "")
                        score = result.get("score", 0.0)
                        source = result.get("source") or f"vector:{result.get('id', 'unknown')}"

                    results.append(
                        RetrievedContext(
                            content=content,
                            score=score,
                            source=source,
                            metadata=metadata,
                        )
                    )

            return results

        except Exception as e:
            self.logger.warning(f"Vector retrieval failed: {e}")
            return []

    def _retrieve_from_graph(
        self, query: str, max_results: int, max_hops: int = 2, query_intent: Optional[Dict[str, Any]] = None
    ) -> List[RetrievedContext]:
        """Retrieve from knowledge graph."""
        if not self.knowledge_graph:
            return []

        results = []

        try:
            # Check if knowledge_graph implements GraphStore protocol (has query method)
            if hasattr(self.knowledge_graph, "query"):
                graph_results = self.knowledge_graph.query(query)

                for res in graph_results:
                    # Handle both interface dicts and raw dicts
                    node = res.get("node")
                    if hasattr(node, "id"):  # GraphNodeInterface
                        node_id = node.id
                        node_type = node.type
                        content = node.properties.get("content", "")
                        metadata = node.properties
                    else:  # Raw dict
                        node_id = res.get("id") or res.get("node", {}).get("id")
                        node_type = res.get("type") or res.get("node", {}).get("type")
                        content = res.get("content") or res.get("node", {}).get(
                            "content"
                        )
                        metadata = res.get("metadata") or res.get("node", {}).get(
                            "metadata"
                        )

                    score = res.get("score", 0.0)

                    # Get related entities
                    related_entities = self._get_related_entities(
                        node_id, max_hops=max_hops
                    )

                    results.append(
                        RetrievedContext(
                            content=content,
                            score=score,
                            source=f"graph:{node_id}",
                            metadata={
                                "node_type": node_type,
                                "node_id": node_id,
                                **(metadata or {}),
                            },
                            related_entities=related_entities,
                        )
                    )

                # Sort by score
                results.sort(key=lambda x: x.score, reverse=True)
                return results[:max_results]

            # Fallback to dictionary-based graph retrieval
            # Handle GraphBuilder format (entities and relationships)
            # Get entities and relationships from graph
            entities = self.knowledge_graph.get("entities", [])
            relationships = self.knowledge_graph.get("relationships", [])

            # Use semantic similarity if vector_store is available
            if self.vector_store and hasattr(self.vector_store, 'embed'):
                try:
                    import numpy as np
                    # Generate query embedding
                    query_embedding = self.vector_store.embed(query)
                    if query_embedding is not None:
                        query_embedding = np.array(query_embedding)
                        # Handle batch embeddings (take first if 2D)
                        if len(query_embedding.shape) == 2:
                            query_embedding = query_embedding[0]
                        query_norm = np.linalg.norm(query_embedding)
                        
                        if query_norm > 0:
                            # Calculate semantic similarity for each entity
                            entity_scores = []
                            for entity in entities:
                                entity_name = str(entity.get("name", entity.get("id", "")))
                                entity_type = str(entity.get("type", ""))
                                
                                # Create entity text for embedding (include type for better matching)
                                entity_text = f"{entity_name} {entity_type}".strip()
                                entity_embedding = self.vector_store.embed(entity_text)
                                
                                if entity_embedding is not None:
                                    entity_embedding = np.array(entity_embedding)
                                    # Handle batch embeddings
                                    if len(entity_embedding.shape) == 2:
                                        entity_embedding = entity_embedding[0]
                                    entity_norm = np.linalg.norm(entity_embedding)
                                    
                                    # Cosine similarity
                                    if entity_norm > 0:
                                        similarity = np.dot(query_embedding, entity_embedding) / (query_norm * entity_norm)
                                        
                                        # Boost if entity type is mentioned in query (domain-agnostic)
                                        if query_intent and query_intent.get("entity_types"):
                                            # Check if entity type semantically matches query keywords
                                            entity_type_lower = entity_type.lower()
                                            query_keywords = query_intent.get("keywords", set())
                                            if any(kw in entity_type_lower or entity_type_lower in kw for kw in query_keywords if len(kw) > 2):
                                                similarity *= 1.15  # 15% boost for type-keyword match
                                        
                                        entity_scores.append((entity, float(similarity)))
                            
                            # Also match relationships semantically
                            relationship_scores = []
                            for rel in relationships:
                                rel_type = str(rel.get("type", ""))
                                source_id = rel.get("source") or rel.get("source_id", "")
                                target_id = rel.get("target") or rel.get("target_id", "")
                                
                                # Find entity names for better matching
                                source_name = source_id
                                target_name = target_id
                                for e in entities:
                                    e_id = e.get("id") or e.get("name")
                                    if e_id == source_id:
                                        source_name = e.get("name", source_id)
                                    if e_id == target_id:
                                        target_name = e.get("name", target_id)
                                
                                # Create relationship text for embedding
                                rel_text = f"{rel_type} {source_name} {target_name}".strip()
                                rel_embedding = self.vector_store.embed(rel_text)
                                
                                if rel_embedding is not None:
                                    rel_embedding = np.array(rel_embedding)
                                    if len(rel_embedding.shape) == 2:
                                        rel_embedding = rel_embedding[0]
                                    rel_norm = np.linalg.norm(rel_embedding)
                                    
                                    if rel_norm > 0:
                                        similarity = np.dot(query_embedding, rel_embedding) / (query_norm * rel_norm)
                                        
                                        # Boost if relationship type semantically matches query (domain-agnostic)
                                        if query_intent and query_intent.get("relationship_types"):
                                            rel_type_lower = rel_type.lower()
                                            # Check if relationship type or its synonyms appear in query
                                            for rt in query_intent["relationship_types"]:
                                                if rt.lower() in rel_type_lower or rel_type_lower in rt.lower():
                                                    similarity *= 1.25  # 25% boost for matching relationship
                                                    break
                                        
                                        relationship_scores.append((rel, similarity, source_id, target_id))
                            
                            # Sort by similarity
                            entity_scores.sort(key=lambda x: x[1], reverse=True)
                            relationship_scores.sort(key=lambda x: x[1], reverse=True)
                            
                            # Combine entity and relationship matches
                            # Include entities from high-scoring relationships
                            matched_entity_ids = set()
                            matched_entities = []
                            
                            # Add top entity matches
                            for entity, score in entity_scores[:max_results * 2]:
                                if score > 0.3:  # Similarity threshold
                                    entity_id = entity.get("id") or entity.get("name")
                                    matched_entity_ids.add(entity_id)
                                    matched_entities.append((entity, score))
                            
                            # Add entities from high-scoring relationships
                            for rel, score, source_id, target_id in relationship_scores[:max_results]:
                                if score > 0.3:
                                    # Add source entity if not already matched
                                    if source_id not in matched_entity_ids:
                                        for e in entities:
                                            e_id = e.get("id") or e.get("name")
                                            if e_id == source_id:
                                                matched_entity_ids.add(source_id)
                                                # Boost score for relationship match
                                                matched_entities.append((e, score * 0.9))
                                                break
                                    # Add target entity if not already matched
                                    if target_id not in matched_entity_ids:
                                        for e in entities:
                                            e_id = e.get("id") or e.get("name")
                                            if e_id == target_id:
                                                matched_entity_ids.add(target_id)
                                                matched_entities.append((e, score * 0.9))
                                                break
                            
                            # Sort all matches by score
                            matched_entities.sort(key=lambda x: x[1], reverse=True)
                            matched_entities = matched_entities[:max_results * 2]
                        else:
                            matched_entities = self._keyword_match_entities(entities, query, max_results * 2)
                    else:
                        # Fallback to keyword matching if embedding fails
                        matched_entities = self._keyword_match_entities(entities, query, max_results * 2)
                except Exception as e:
                    self.logger.warning(f"Semantic matching failed: {e}, falling back to keyword matching")
                    matched_entities = self._keyword_match_entities(entities, query, max_results * 2)
            else:
                # Use keyword matching as fallback
                matched_entities = self._keyword_match_entities(entities, query, max_results * 2)
            
            # Process matched entities
            for entity, score in matched_entities:
                    # Find related relationships
                    entity_id = entity.get("id") or entity.get("name")
                    entity_type = str(entity.get("type", ""))
                    related_entities = []
                    related_relationships = []
                    
                    # Find relationships involving this entity
                    for rel in relationships:
                        if (rel.get("source") == entity_id or 
                            rel.get("target") == entity_id or
                            rel.get("source_id") == entity_id or
                            rel.get("target_id") == entity_id):
                            related_relationships.append(rel)
                            
                            # Get the other entity in the relationship
                            other_id = rel.get("target") or rel.get("target_id")
                            if other_id == entity_id:
                                other_id = rel.get("source") or rel.get("source_id")
                            
                            # Find the other entity
                            for e in entities:
                                e_id = e.get("id") or e.get("name")
                                if e_id == other_id:
                                    related_entities.append(e)
                                    break
                    
                    # Generate comprehensive content from entity and relationships
                    entity_display = entity.get('name', entity_id)
                    
                    # Start with entity description
                    entity_desc = f"{entity_display}"
                    if entity_type:
                        entity_desc += f" is a {entity_type}"
                    
                    # Add entity properties/metadata if available
                    entity_props = entity.get("metadata", {})
                    if entity_props:
                        # Include relevant properties
                        prop_keys = ["description", "summary", "details", "info"]
                        for key in prop_keys:
                            if key in entity_props and entity_props[key]:
                                entity_desc += f". {entity_props[key]}"
                                break
                    
                    content_parts = [entity_desc]
                    
                    if related_relationships:
                        # Group relationships by type for better content
                        rels_by_type = {}
                        for rel in related_relationships:
                            rel_type = rel.get("type", "related_to")
                            source_id = rel.get("source") or rel.get("source_id")
                            target_id = rel.get("target") or rel.get("target_id")
                            
                            # Determine direction
                            if source_id == entity_id:
                                # Entity is source
                                target_name = target_id
                                for e in entities:
                                    e_id = e.get("id") or e.get("name")
                                    if e_id == target_id:
                                        target_name = e.get("name", target_id)
                                        target_type = e.get("type", "")
                                        break
                                else:
                                    target_type = ""
                                
                                if rel_type not in rels_by_type:
                                    rels_by_type[rel_type] = []
                                rels_by_type[rel_type].append((target_name, target_type))
                            else:
                                # Entity is target
                                source_name = source_id
                                for e in entities:
                                    e_id = e.get("id") or e.get("name")
                                    if e_id == source_id:
                                        source_name = e.get("name", source_id)
                                        source_type = e.get("type", "")
                                        break
                                else:
                                    source_type = ""
                                
                                # Reverse relationship for readability
                                reverse_type = f"is {rel_type}ed by" if rel_type else "related to"
                                if reverse_type not in rels_by_type:
                                    rels_by_type[reverse_type] = []
                                rels_by_type[reverse_type].append((source_name, source_type))
                        
                        # Format relationships with more context
                        for rel_type, targets in list(rels_by_type.items())[:5]:  # Show more relationships
                            if len(targets) == 1:
                                target_name, target_type = targets[0]
                                if target_type:
                                    content_parts.append(f"{rel_type} {target_name} ({target_type})")
                                else:
                                    content_parts.append(f"{rel_type} {target_name}")
                            elif len(targets) <= 3:
                                target_list = []
                                for target_name, target_type in targets:
                                    if target_type:
                                        target_list.append(f"{target_name} ({target_type})")
                                    else:
                                        target_list.append(target_name)
                                content_parts.append(f"{rel_type} {', '.join(target_list)}")
                            else:
                                target_list = []
                                for target_name, target_type in targets[:3]:
                                    if target_type:
                                        target_list.append(f"{target_name} ({target_type})")
                                    else:
                                        target_list.append(target_name)
                                content_parts.append(f"{rel_type} {', '.join(target_list)} and {len(targets) - 3} more")
                    
                    # Add related entity context if available
                    if related_entities and len(content_parts) < 3:
                        entity_names = []
                        for e in related_entities[:3]:
                            e_name = e.get("name", e.get("id", ""))
                            e_type = e.get("type", "")
                            if e_type:
                                entity_names.append(f"{e_name} ({e_type})")
                            else:
                                entity_names.append(e_name)
                        if entity_names:
                            content_parts.append(f"Related to: {', '.join(entity_names)}")
                    
                    content = ". ".join(content_parts) + "."

                    results.append(
                        RetrievedContext(
                            content=content,
                            score=score,
                            source=f"graph:{entity_id}",
                            metadata={
                                "node_type": entity_type,
                                "node_id": entity_id,
                                **entity.get("metadata", {}),
                            },
                            related_entities=related_entities[:10],  # Limit entities
                            related_relationships=related_relationships[:10],  # Limit relationships
                        )
                    )

            # Sort by score
            results.sort(key=lambda x: x.score, reverse=True)

            return results[:max_results]

        except Exception as e:
            self.logger.warning(f"Graph retrieval failed: {e}")
            return []
    
    def _keyword_match_entities(self, entities, query, max_results):
        """Fallback keyword matching for entities."""
        query_lower = query.lower()
        query_words = set(query_lower.split())
        entity_scores = []
        
        for entity in entities:
            entity_name = str(entity.get("name", entity.get("id", "")))
            entity_name_lower = entity_name.lower()
            entity_type = str(entity.get("type", "")).lower()
            
            # Word overlap score
            entity_words = set(entity_name_lower.split())
            match_score = len(query_words.intersection(entity_words))
            
            # Substring match boost
            if any(word in entity_name_lower for word in query_words):
                match_score += 1
            
            if match_score > 0:
                score = match_score / max(len(query_words), 1)
                entity_scores.append((entity, score))
        
        entity_scores.sort(key=lambda x: x[1], reverse=True)
        return entity_scores[:max_results]

    def _retrieve_from_memory(
        self, query: str, max_results: int
    ) -> List[RetrievedContext]:
        """Retrieve from memory store."""
        if not self.memory_store:
            return []

        try:
            # If memory_store has a retrieve method
            if hasattr(self.memory_store, "retrieve"):
                memory_results = self.memory_store.retrieve(
                    query=query, max_results=max_results
                )

                results = []
                for result in memory_results:
                    results.append(
                        RetrievedContext(
                            content=result.get("content", ""),
                            score=result.get("score", 0.0),
                            source=result.get("source") or f"memory:{result.get('id', 'unknown')}",
                            metadata=result.get("metadata", {}),
                        )
                    )

                return results

            return []

        except Exception as e:
            self.logger.warning(f"Memory retrieval failed: {e}")
            return []

    def _rank_and_merge(
        self, results: List[RetrievedContext], query: str
    ) -> List[RetrievedContext]:
        """Rank and merge results from multiple sources with GraphRAG optimization."""
        # Separate results by source (handle None source gracefully)
        vector_results = [r for r in results if r.source and r.source.startswith("vector:")]
        graph_results = [r for r in results if r.source and r.source.startswith("graph:")]
        memory_results = [r for r in results if r.source and r.source.startswith("memory:")]
        
        # Normalize scores within each source (0-1 range)
        def normalize_scores(source_results):
            if not source_results:
                return source_results
            scores = [r.score for r in source_results]
            if not scores:
                return source_results
            min_score, max_score = min(scores), max(scores)
            if max_score > min_score:
                for r in source_results:
                    r.score = (r.score - min_score) / (max_score - min_score)
            return source_results
        
        vector_results = normalize_scores(vector_results)
        graph_results = normalize_scores(graph_results)
        memory_results = normalize_scores(memory_results)
        
        # Apply hybrid_alpha weighting: 0=vector only, 1=graph only, 0.5=balanced
        alpha = self.hybrid_alpha
        for r in vector_results:
            r.score = r.score * (1 - alpha)  # Weight vector results
        for r in graph_results:
            r.score = r.score * alpha  # Weight graph results
            # Boost graph results with more context (more related entities/relationships)
            context_boost = min(
                0.2,  # Max 20% boost
                (len(r.related_entities) + len(r.related_relationships or [])) * 0.01
            )
            r.score += context_boost
        for r in memory_results:
            r.score = r.score * 0.3  # Lower weight for memory
        
        # Deduplicate by entity ID (for graph) or content (for others)
        seen_entities = {}  # entity_id -> result
        seen_content = {}   # content_hash -> result
        
        all_results = vector_results + graph_results + memory_results
        
        for result in all_results:
            # For graph results, deduplicate by entity ID
            if result.source and result.source.startswith("graph:"):
                entity_id = result.metadata.get("node_id")
                if entity_id:
                    if entity_id not in seen_entities:
                        seen_entities[entity_id] = result
                    else:
                        # Merge: boost score if found in multiple sources
                        existing = seen_entities[entity_id]
                        existing.score = max(existing.score, result.score) * 1.2  # 20% boost for multi-source
                        existing.metadata.update(result.metadata)
                        # Merge related entities
                        existing_ids = {e.get("id") or e.get("name") for e in existing.related_entities}
                        for entity in result.related_entities:
                            e_id = entity.get("id") or entity.get("name")
                            if e_id not in existing_ids:
                                existing.related_entities.append(entity)
                                existing_ids.add(e_id)
                        # Merge relationships
                        if result.related_relationships:
                            if not existing.related_relationships:
                                existing.related_relationships = []
                            existing_rel_ids = {
                                (r.get("source"), r.get("target"), r.get("type"))
                                for r in existing.related_relationships
                            }
                            for rel in result.related_relationships:
                                rel_key = (
                                    rel.get("source") or rel.get("source_id"),
                                    rel.get("target") or rel.get("target_id"),
                                    rel.get("type")
                                )
                                if rel_key not in existing_rel_ids:
                                    existing.related_relationships.append(rel)
                                    existing_rel_ids.add(rel_key)
                        continue
            
            # For non-graph results, deduplicate by content
            content_key = result.content[:100] if result.content else ""
            if content_key not in seen_content:
                seen_content[content_key] = result
            else:
                existing = seen_content[content_key]
                existing.score = max(existing.score, result.score)
                existing.metadata.update(result.metadata)
        
        # Combine deduplicated results
        merged_results = list(seen_entities.values()) + [
            r for r in seen_content.values() 
            if not (r.source and r.source.startswith("graph:")) or r.metadata.get("node_id") not in seen_entities
        ]
        
        # Re-rank with query relevance boost
        if self.vector_store and hasattr(self.vector_store, 'embed'):
            try:
                import numpy as np
                query_embedding = self.vector_store.embed(query)
                if query_embedding is not None:
                    query_embedding = np.array(query_embedding)
                    if len(query_embedding.shape) == 2:
                        query_embedding = query_embedding[0]
                    query_norm = np.linalg.norm(query_embedding)
                    
                    if query_norm > 0:
                        for result in merged_results:
                            # Re-score based on semantic similarity to query
                            content_embedding = self.vector_store.embed(result.content[:500])
                            if content_embedding is not None:
                                content_embedding = np.array(content_embedding)
                                if len(content_embedding.shape) == 2:
                                    content_embedding = content_embedding[0]
                                content_norm = np.linalg.norm(content_embedding)
                                if content_norm > 0:
                                    semantic_sim = np.dot(query_embedding, content_embedding) / (query_norm * content_norm)
                                    # Blend original score with semantic similarity
                                    result.score = result.score * 0.7 + float(semantic_sim) * 0.3
            except Exception as e:
                self.logger.debug(f"Query relevance boost failed: {e}")
        
        # Final sort by score
        ranked = sorted(merged_results, key=lambda x: x.score, reverse=True)
        
        return ranked

    def _extract_query_intent(self, query: str) -> Dict[str, Any]:
        """Extract query intent to guide graph retrieval (domain-agnostic)."""
        query_lower = query.lower()
        intent = {
            "entity_types": [],
            "relationship_types": [],
            "question_type": "general",
            "keywords": set(query_lower.split())
        }
        
        # Generic question type detection (domain-agnostic)
        question_words = {
            "what": ["what", "which"],
            "who": ["who"],
            "how": ["how"],
            "when": ["when"],
            "where": ["where"],
            "why": ["why"]
        }
        
        for q_type, words in question_words.items():
            if any(query_lower.startswith(w) for w in words):
                intent["question_type"] = q_type
                break
        
        # Extract relationship verbs/patterns from query (domain-agnostic)
        # Use regex to find common relationship verbs that work across domains
        import re
        relationship_verbs = re.findall(
            r'\b(targets?|inhibits?|treats?|causes?|relates?|connects?|links?|interacts?|'
            r'influences?|affects?|depends?|requires?|contains?|includes?|belongs?|'
            r'opposes?|supports?|enables?|prevents?|blocks?|activates?|deactivates?|'
            r'regulates?|controls?|manages?|owns?|operates?|uses?|produces?|creates?|'
            r'develops?|builds?|designs?|implements?|maintains?|supports?|works with)\b',
            query_lower
        )
        for verb in relationship_verbs:
            if verb not in intent["relationship_types"]:
                intent["relationship_types"].append(verb)
        
        # Note: Entity types are not hardcoded - they will be matched semantically
        # based on the actual entities in the knowledge graph, making it domain-agnostic
        
        return intent

    def _calculate_graph_relevance(self, node: Dict[str, Any], query: str) -> float:
        """Calculate relevance score for graph node."""
        content = node.get("content", "").lower()
        query_lower = query.lower()

        # Simple word overlap
        query_words = set(query_lower.split())
        content_words = set(content.split())

        if not query_words:
            return 0.0

        overlap = len(query_words & content_words)
        return overlap / len(query_words)

    def _get_related_entities(
        self, node_id: str, max_hops: int = 2
    ) -> List[Dict[str, Any]]:
        """Get related entities from graph."""
        if not self.knowledge_graph:
            return []

        # Check if knowledge_graph implements GraphStore protocol
        if hasattr(self.knowledge_graph, "get_neighbors"):
            return self.knowledge_graph.get_neighbors(node_id, hops=max_hops)

        related = []
        visited = set()
        current_level = {node_id}

        for hop in range(max_hops):
            next_level = set()

            for current_id in current_level:
                if current_id in visited:
                    continue
                visited.add(current_id)

                # Find edges
                edges = self.knowledge_graph.get("edges", [])
                for edge in edges:
                    if edge.get("source") == current_id:
                        target_id = edge.get("target")
                        if target_id not in visited:
                            next_level.add(target_id)

                            # Get node info
                            nodes = self.knowledge_graph.get("nodes", [])
                            for node in nodes:
                                if node.get("id") == target_id:
                                    related.append(
                                        {
                                            "id": target_id,
                                            "type": node.get("type"),
                                            "content": node.get("content"),
                                            "relationship": edge.get("type"),
                                            "hop": hop + 1,
                                        }
                                    )

                    elif edge.get("target") == current_id:
                        source_id = edge.get("source")
                        if source_id not in visited:
                            next_level.add(source_id)

                            nodes = self.knowledge_graph.get("nodes", [])
                            for node in nodes:
                                if node.get("id") == source_id:
                                    related.append(
                                        {
                                            "id": source_id,
                                            "type": node.get("type"),
                                            "content": node.get("content"),
                                            "relationship": edge.get("type"),
                                            "hop": hop + 1,
                                        }
                                    )

            current_level = next_level

        return related

    # Search Methods
    def search(self, query: str, **options) -> List[RetrievedContext]:
        """
        Simple search (alias for retrieve).

        Args:
            query: Search query
            **options: Additional options

        Returns:
            List of RetrievedContext objects

        Example:
            >>> results = retriever.search("Python", max_results=10)
        """
        return self.retrieve(query, **options)

    def vector_search(self, query: str, **options) -> List[RetrievedContext]:
        """
        Vector-only search.

        Args:
            query: Search query
            **options: Additional options

        Returns:
            List of RetrievedContext objects from vector store

        Example:
            >>> results = retriever.vector_search("Python")
        """
        # Temporarily disable graph and memory
        original_graph = self.knowledge_graph
        original_memory = self.memory_store

        self.knowledge_graph = None
        self.memory_store = None

        try:
            results = self.retrieve(query, use_graph_expansion=False, **options)
        finally:
            self.knowledge_graph = original_graph
            self.memory_store = original_memory

        return results

    def graph_search(self, query: str, **options) -> List[RetrievedContext]:
        """
        Graph-only search.

        Args:
            query: Search query
            **options: Additional options

        Returns:
            List of RetrievedContext objects from graph

        Example:
            >>> results = retriever.graph_search("Python")
        """
        if not self.knowledge_graph:
            return []

        # Temporarily disable vector and memory
        original_vector = self.vector_store
        original_memory = self.memory_store

        self.vector_store = None
        self.memory_store = None

        try:
            results = self.retrieve(query, use_graph_expansion=True, **options)
        finally:
            self.vector_store = original_vector
            self.memory_store = original_memory

        return results

    def memory_search(self, query: str, **options) -> List[RetrievedContext]:
        """
        Memory-only search.

        Args:
            query: Search query
            **options: Additional options

        Returns:
            List of RetrievedContext objects from memory

        Example:
            >>> results = retriever.memory_search("Python")
        """
        if not self.memory_store:
            return []

        # Use memory store's retrieve method
        memory_results = self.memory_store.retrieve(query, **options)

        # Convert to RetrievedContext
        results = []
        for mem in memory_results:
            results.append(
                RetrievedContext(
                    content=mem.get("content", ""),
                    score=mem.get("score", 0.0),
                    source="memory",
                    metadata=mem.get("metadata", {}),
                )
            )

        return results

    def hybrid_search(self, query: str, **options) -> List[RetrievedContext]:
        """
        Hybrid search (all sources).

        Args:
            query: Search query
            **options: Additional options

        Returns:
            List of RetrievedContext objects from all sources

        Example:
            >>> results = retriever.hybrid_search("Python")
        """
        return self.retrieve(query, **options)

    # Advanced Retrieval
    def find_similar(
        self, content: str, limit: int = 5, **options
    ) -> List[RetrievedContext]:
        """
        Find similar content.

        Args:
            content: Content to find similar items for
            limit: Maximum results (default: 5)
            **options: Additional options

        Returns:
            List of similar RetrievedContext objects

        Example:
            >>> similar = retriever.find_similar("Python programming", limit=5)
        """
        return self.retrieve(content, max_results=limit, **options)

    def get_context(
        self, query: str, max_results: int = 5, **options
    ) -> List[RetrievedContext]:
        """
        Get context for query.

        Args:
            query: Query string
            max_results: Maximum results (default: 5)
            **options: Additional options

        Returns:
            List of RetrievedContext objects

        Example:
            >>> context_data = retriever.get_context("Python", max_results=10)
        """
        return self.retrieve(query, max_results=max_results, **options)

    def expand_query(
        self, query: str, max_hops: int = 2, **options
    ) -> List[RetrievedContext]:
        """
        Expand query with graph.

        Args:
            query: Query string
            max_hops: Maximum expansion hops (default: 2)
            **options: Additional options

        Returns:
            List of expanded RetrievedContext objects

        Example:
            >>> expanded = retriever.expand_query("Python", max_hops=3)
        """
        return self.retrieve(
            query,
            use_graph_expansion=True,
            max_hops=max_hops,
            **options,
        )

    def get_related(self, entity_id: str, max_hops: int = 2) -> List[Dict[str, Any]]:
        """
        Get related entities.

        Args:
            entity_id: Entity ID
            max_hops: Maximum hops (default: 2)

        Returns:
            List of related entity dicts

        Example:
            >>> related = retriever.get_related("entity_123", max_hops=2)
        """
        if not self.knowledge_graph:
            return []

        return self._get_related_entities(entity_id, max_hops=max_hops)

    def get_path(
        self, source_id: str, target_id: str, max_hops: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Get path between entities.

        Args:
            source_id: Source entity ID
            target_id: Target entity ID
            max_hops: Maximum hops (default: 5)

        Returns:
            List of path nodes/edges

        Example:
            >>> path = retriever.get_path("entity_1", "entity_2", max_hops=5)
        """
        if not self.knowledge_graph:
            return []

        # Simple BFS path finding
        from collections import deque

        queue = deque([(source_id, [source_id])])
        visited = {source_id}

        while queue:
            current_id, path = queue.popleft()

            if len(path) > max_hops:
                continue

            if current_id == target_id:
                # Return path with node info
                nodes = self.knowledge_graph.get("nodes", [])
                path_info = []
                for node_id in path:
                    for node in nodes:
                        if node.get("id") == node_id:
                            path_info.append(
                                {
                                    "id": node_id,
                                    "content": node.get("content", ""),
                                    "type": node.get("type", ""),
                                }
                            )
                            break
                return path_info

            # Get neighbors
            edges = self.knowledge_graph.get("edges", [])
            for edge in edges:
                neighbor_id = None
                if edge.get("source") == current_id:
                    neighbor_id = edge.get("target")
                elif edge.get("target") == current_id:
                    neighbor_id = edge.get("source")

                if neighbor_id and neighbor_id not in visited:
                    visited.add(neighbor_id)
                    queue.append((neighbor_id, path + [neighbor_id]))

        return []

    # Reasoning Methods
    def _build_reasoning_path(
        self,
        query_entities: List[Dict[str, Any]],
        max_hops: int = 2
    ) -> List[Dict[str, Any]]:
        """
        Build multi-hop reasoning path through knowledge graph.

        Args:
            query_entities: List of entities extracted from query
            max_hops: Maximum number of hops to traverse (default: 2)

        Returns:
            List of reasoning path segments with entity relationships
        """
        if not self.knowledge_graph:
            return []

        reasoning_paths = []
        visited_entities = set()

        # Get entities and relationships from knowledge graph
        # Handle both dict and GraphStore objects
        if isinstance(self.knowledge_graph, dict):
            entities = self.knowledge_graph.get("entities", [])
            relationships = self.knowledge_graph.get("relationships", [])
        elif hasattr(self.knowledge_graph, "get_entities") and hasattr(self.knowledge_graph, "get_relationships"):
            # GraphStore-like object
            entities = self.knowledge_graph.get_entities() or []
            relationships = self.knowledge_graph.get_relationships() or []
        else:
            # Try to access as dict anyway
            entities = getattr(self.knowledge_graph, "entities", [])
            relationships = getattr(self.knowledge_graph, "relationships", [])

        # Create entity lookup
        entity_map = {}
        for entity in entities:
            entity_id = entity.get("id") or entity.get("text") or entity.get("name")
            if entity_id:
                entity_map[entity_id] = entity

        # Create relationship lookup
        rel_map = {}
        for rel in relationships:
            source = rel.get("source") or rel.get("source_id")
            target = rel.get("target") or rel.get("target_id")
            rel_type = rel.get("type") or rel.get("predicate")
            if source and target:
                if source not in rel_map:
                    rel_map[source] = []
                rel_map[source].append({"target": target, "type": rel_type, "rel": rel})

        # Start BFS from query entities
        from collections import deque
        queue = deque()

        for query_entity in query_entities:
            entity_id = query_entity.get("id") or query_entity.get("text") or query_entity.get("name")
            if entity_id and entity_id in entity_map:
                queue.append((entity_id, 0, [entity_id]))

        while queue:
            current_id, hop, path = queue.popleft()

            if hop >= max_hops:
                continue

            if current_id in visited_entities:
                continue
            visited_entities.add(current_id)

            # Get relationships from current entity
            if current_id in rel_map:
                for rel_info in rel_map[current_id]:
                    target_id = rel_info["target"]
                    rel_type = rel_info["type"]
                    rel = rel_info["rel"]

                    if target_id not in path:  # Avoid cycles
                        new_path = path + [target_id]

                        # Build relationships list for this path
                        path_relationships = []
                        for i in range(len(new_path) - 1):
                            source_id = new_path[i]
                            target_id_rel = new_path[i + 1]
                            # Find the relationship type between these two entities
                            rel_type_found = None
                            if source_id in rel_map:
                                for r_info in rel_map[source_id]:
                                    if r_info["target"] == target_id_rel:
                                        rel_type_found = r_info["type"]
                                        break
                            path_relationships.append({
                                "source": source_id,
                                "target": target_id_rel,
                                "type": rel_type_found or "related_to"
                            })

                        # Add to reasoning paths
                        reasoning_paths.append({
                            "path": new_path,
                            "hops": hop + 1,
                            "relationships": path_relationships,
                            "entities": [
                                entity_map.get(eid, {}) for eid in new_path
                            ]
                        })

                        # Continue traversal
                        if target_id in entity_map and hop + 1 < max_hops:
                            queue.append((target_id, hop + 1, new_path))

        return reasoning_paths

    def _generate_reasoned_response(
        self,
        query: str,
        retrieved_context: List[RetrievedContext],
        reasoning_paths: List[Dict[str, Any]],
        llm_provider: Any,
        at_time: Optional[Any] = None,
        header_template: str = "[Graph context valid as of: {at_time} UTC | Source: {source}]",
    ) -> str:
        """
        Generate natural language response using LLM with retrieved context and reasoning paths.

        Args:
            query: User query
            retrieved_context: Retrieved context items
            reasoning_paths: Multi-hop reasoning paths
            llm_provider: LLM provider instance (from semantica.llms)
            at_time: Optional point-in-time for the graph snapshot. When set, a
                structured temporal header is prepended to the context block so
                the LLM knows the validity window of the facts it is reasoning over.
            header_template: Format string for the temporal header. Placeholders:
                ``{at_time}`` (ISO timestamp) and ``{source}`` (snapshot label).

        Returns:
            Generated natural language response
        """
        # Build temporal header when at_time is explicitly provided
        temporal_header = ""
        if at_time is not None:
            if isinstance(at_time, datetime):
                # Normalise to UTC so the header always says "UTC" truthfully
                if at_time.tzinfo is None:
                    at_time = at_time.replace(tzinfo=timezone.utc)
                else:
                    at_time = at_time.astimezone(timezone.utc)
                at_time_str = at_time.isoformat()
            else:
                at_time_str = str(at_time)
            # Use plain str.replace instead of .format() so that unexpected
            # braces in header_template or in at_time_str cannot be
            # interpreted as additional format placeholders (injection guard).
            temporal_header = (
                header_template
                .replace("{at_time}", at_time_str)
                .replace("{source}", "KnowledgeGraph snapshot")
            ) + "\n\n"

        # Format retrieved context
        context_text = "\n\n".join([
            f"Context {i+1} (Score: {ctx.score:.2f}):\n{ctx.content}"
            for i, ctx in enumerate(retrieved_context[:5])
        ])

        # Format reasoning paths
        reasoning_text = ""
        if reasoning_paths:
            reasoning_text = "\n\nReasoning Paths (Multi-hop connections):\n"
            for i, path_info in enumerate(reasoning_paths[:3], 1):
                entities = path_info.get("entities", [])
                relationships = path_info.get("relationships", [])
                
                if entities:
                    path_parts = []
                    for j, entity in enumerate(entities):
                        entity_name = entity.get('text') or entity.get('name') or 'Unknown'
                        path_parts.append(entity_name)
                        # Add relationship after entity (except for last entity)
                        if j < len(relationships) and relationships[j].get('type'):
                            rel_type = relationships[j]['type']
                            path_parts.append(f"--[{rel_type}]-->")
                    path_str = " ".join(path_parts)
                    reasoning_text += f"Path {i}: {path_str}\n"

        # Construct prompt
        prompt = f"""You are a knowledge graph reasoning assistant. Answer the user's question based on the retrieved context and reasoning paths from the knowledge graph.

User Question: {query}

{temporal_header}Retrieved Context:
{context_text}

{reasoning_text}

Instructions:
1. Answer the question using the retrieved context and reasoning paths
2. Cite specific entities and relationships from the reasoning paths
3. Explain the multi-hop connections when relevant
4. Be concise but comprehensive
5. If information is not available in the context, say so

Answer:"""

        try:
            response = llm_provider.generate(prompt)
            return response
        except Exception as e:
            self.logger.warning(f"LLM generation failed: {e}")
            # Fallback: return summary of context
            return f"Based on the retrieved context, here are the relevant findings:\n\n{context_text[:500]}..."

    def query_with_reasoning(
        self,
        query: str,
        llm_provider: Any,
        max_results: int = 10,
        max_hops: int = 2,
        at_time: Optional[Any] = None,
        header_template: str = "[Graph context valid as of: {at_time} UTC | Source: {source}]",
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Query with multi-hop reasoning and LLM-based response generation.

        Retrieves context, builds reasoning paths through the graph, and generates
        a natural language response grounded in the knowledge graph.

        Args:
            query: User query
            llm_provider: LLM provider instance (from semantica.llms)
            max_results: Maximum context results to retrieve (default: 10)
            max_hops: Maximum graph traversal hops (default: 2)
            at_time: Optional point-in-time for the graph snapshot.  Accepts a
                :class:`~datetime.datetime` (naive datetimes are assumed UTC)
                or an ISO 8601 string.  When set, a structured temporal header
                is prepended to the LLM context block so the model knows the
                validity window of the facts it reasons over.
            header_template: Template string for the temporal header.  Only
                ``{at_time}`` and ``{source}`` placeholders are substituted;
                any other braces are left as-is.  Defaults to
                ``"[Graph context valid as of: {at_time} UTC | Source: {source}]"``.
            **kwargs: Additional retrieval options passed to ``retrieve()``

        Returns:
            Dictionary with:
                - response: Generated natural language answer
                - reasoning_path: Multi-hop reasoning trace
                - sources: Retrieved context items
                - confidence: Overall confidence score

        Example:
            >>> from semantica.llms import Groq
            >>> llm = Groq(model="llama-3.1-8b-instant")
            >>> result = retriever.query_with_reasoning(
            ...     "What IPs are associated with security alerts?",
            ...     llm_provider=llm,
            ...     max_hops=2
            ... )
            >>> print(result['response'])
        """
        tracking_id = self.progress_tracker.start_tracking(
            file=None,
            module="context",
            submodule="ContextRetriever",
            message=f"Querying with reasoning: {query[:50]}...",
        )

        try:
            # Step 1: Retrieve initial context
            self.progress_tracker.update_tracking(
                tracking_id, message="Retrieving context..."
            )
            retrieved_context = self.retrieve(
                query,
                max_results=max_results,
                use_graph_expansion=True,
                **kwargs
            )

            # Step 2: Extract entities from query and retrieved context
            self.progress_tracker.update_tracking(
                tracking_id, message="Extracting entities..."
            )
            query_entities = []
            
            # Extract entities from retrieved context
            for ctx in retrieved_context:
                query_entities.extend(ctx.related_entities)

            # Deduplicate entities
            seen_ids = set()
            unique_entities = []
            for entity in query_entities:
                entity_id = entity.get("id") or entity.get("text") or entity.get("name")
                if entity_id and entity_id not in seen_ids:
                    seen_ids.add(entity_id)
                    unique_entities.append(entity)

            # Step 3: Build reasoning paths
            self.progress_tracker.update_tracking(
                tracking_id, message="Building reasoning paths..."
            )
            reasoning_paths = self._build_reasoning_path(
                unique_entities,
                max_hops=max_hops
            )

            # Step 4: Generate response using LLM
            self.progress_tracker.update_tracking(
                tracking_id, message="Generating response..."
            )
            response = self._generate_reasoned_response(
                query,
                retrieved_context,
                reasoning_paths,
                llm_provider,
                at_time=at_time,
                header_template=header_template,
            )

            # Step 5: Format reasoning path as string
            reasoning_path_str = ""
            if reasoning_paths:
                for path_info in reasoning_paths[:1]:  # Show first path
                    entities = path_info.get("entities", [])
                    relationships = path_info.get("relationships", [])
                    if entities:
                        path_parts = []
                        for i, entity in enumerate(entities):
                            entity_name = entity.get("text") or entity.get("name") or "Unknown"
                            path_parts.append(entity_name)
                            if i < len(relationships) and relationships[i].get("type"):
                                path_parts.append(f"--[{relationships[i]['type']}]-->")
                        reasoning_path_str = " ".join(path_parts)

            # Calculate overall confidence
            confidence = 0.0
            if retrieved_context:
                avg_score = sum(ctx.score for ctx in retrieved_context) / len(retrieved_context)
                confidence = min(1.0, avg_score * 0.8 + (0.2 if reasoning_paths else 0.0))

            self.progress_tracker.stop_tracking(
                tracking_id, status="completed", message="Query with reasoning completed"
            )

            return {
                "response": response,
                "reasoning_path": reasoning_path_str,
                "sources": [
                    {
                        "content": ctx.content[:200],
                        "score": ctx.score,
                        "source": ctx.source
                    }
                    for ctx in retrieved_context[:5]
                ],
                "confidence": confidence,
                "num_sources": len(retrieved_context),
                "num_reasoning_paths": len(reasoning_paths)
            }

        except Exception as e:
            self.progress_tracker.stop_tracking(
                tracking_id, status="failed", message=str(e)
            )
            self.logger.error(f"Query with reasoning failed: {e}")
            # Fallback: return retrieved context without LLM generation
            return {
                "response": f"Retrieved {len(retrieved_context)} relevant items. LLM generation unavailable.",
                "reasoning_path": "",
                "sources": [
                    {
                        "content": ctx.content[:200],
                        "score": ctx.score,
                        "source": ctx.source
                    }
                    for ctx in retrieved_context[:5]
                ],
                "confidence": 0.5,
                "num_sources": len(retrieved_context),
                "num_reasoning_paths": 0
            }

    # Filter Methods
    def filter_by_entity(
        self, entity_id: str, query: str, **options
    ) -> List[RetrievedContext]:
        """
        Filter by entity.

        Args:
            entity_id: Entity ID to filter by
            query: Search query
            **options: Additional options

        Returns:
            Filtered RetrievedContext objects

        Example:
            >>> results = retriever.filter_by_entity("entity_123", "Python")
        """
        results = self.retrieve(query, **options)
        filtered = []
        for result in results:
            # Check if entity is in related entities
            for entity in result.related_entities:
                if entity.get("id") == entity_id:
                    filtered.append(result)
                    break
        return filtered

    def filter_by_type(
        self, type: str, query: str, **options
    ) -> List[RetrievedContext]:
        """
        Filter by type.

        Args:
            type: Node/entity type to filter by
            query: Search query
            **options: Additional options

        Returns:
            Filtered RetrievedContext objects

        Example:
            >>> results = retriever.filter_by_type("PROGRAMMING_LANGUAGE", "Python")
        """
        results = self.retrieve(query, **options)
        filtered = []
        for result in results:
            if result.metadata.get("node_type") == type:
                filtered.append(result)
        return filtered

    def filter_by_date(
        self,
        start_date: Union[str, datetime],
        end_date: Union[str, datetime],
        query: str,
        **options
    ) -> List[RetrievedContext]:
        """
        Filter by date.

        Args:
            start_date: Start date
            end_date: End date
            query: Search query
            **options: Additional options

        Returns:
            Filtered RetrievedContext objects

        Example:
            >>> results = retriever.filter_by_date("2024-01-01", "2024-12-31", "Python")
        """
        if isinstance(start_date, str):
            from dateutil.parser import parse
            start_date = parse(start_date)
        if isinstance(end_date, str):
            from dateutil.parser import parse
            end_date = parse(end_date)

        results = self.retrieve(query, **options)
        filtered = []
        for result in results:
            result_date = result.metadata.get("timestamp")
            if result_date:
                if isinstance(result_date, str):
                    from dateutil.parser import parse
                    result_date = parse(result_date)
                if start_date <= result_date <= end_date:
                    filtered.append(result)
        return filtered

    def filter_by_score(
        self,
        min_score: float,
        query: str,
        **options
    ) -> List[RetrievedContext]:
        """
        Filter by score.

        Args:
            min_score: Minimum score threshold
            query: Search query
            **options: Additional options

        Returns:
            Filtered RetrievedContext objects

        Example:
            >>> results = retriever.filter_by_score(0.7, "Python")
        """
        results = self.retrieve(query, min_relevance_score=min_score, **options)
        return [r for r in results if r.score >= min_score]

    # Batch Operations
    def batch_search(
        self, queries: List[str], **options
    ) -> Dict[str, List[RetrievedContext]]:
        """
        Search multiple queries.

        Args:
            queries: List of queries
            **options: Additional options

        Returns:
            Dict mapping query to results

        Example:
            >>> results = retriever.batch_search(["Python", "Java", "C++"])
        """
        results = {}
        for query in queries:
            results[query] = self.retrieve(query, **options)
        return results

    def batch_get_context(
        self,
        queries: List[str],
        max_results: int = 5,
        **options
    ) -> Dict[str, List[RetrievedContext]]:
        """
        Get context for multiple queries.

        Args:
            queries: List of queries
            max_results: Maximum results per query (default: 5)
            **options: Additional options

        Returns:
            Dict mapping query to context results

        Example:
            >>> contexts = retriever.batch_get_context(
            ...     ["Python", "Java"], max_results=5
            ... )
        """
        results = {}
        for query in queries:
            results[query] = self.get_context(query, max_results=max_results, **options)
        return results

    # Decision Context Methods
    def retrieve_decision_precedents(
        self,
        query: str,
        limit: int = 10,
        use_hybrid_search: bool = True,
        semantic_weight: float = 0.7,
        structural_weight: float = 0.3,
        max_hops: int = 3,
        include_context: bool = True,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[RetrievedContext]:
        """
        Retrieve decision precedents using hybrid search.
        
        Args:
            query: Decision scenario query
            limit: Number of precedents to return
            use_hybrid_search: Whether to use hybrid similarity
            semantic_weight: Weight for semantic similarity
            structural_weight: Weight for structural similarity
            max_hops: Maximum hops for context expansion
            include_context: Whether to include contextual information
            filters: Optional metadata filters
            
        Returns:
            List of RetrievedContext objects with decision precedents
        """
        if not self.vector_store:
            self.logger.warning("No vector store available for precedent search")
            return []
        
        # Search for similar decisions
        try:
            similar_decisions = self.vector_store.search_decisions(
                query=query,
                semantic_weight=semantic_weight,
                structural_weight=structural_weight,
                filters=filters,
                limit=limit,
                use_hybrid_search=use_hybrid_search
            )
        except (AttributeError, NotImplementedError):
            # Fallback to regular vector search
            vector_results = self.vector_store.search(query, limit=limit)
            similar_decisions = []
            for result in vector_results:
                similar_decisions.append({
                    "similarity": result.get("score", 0.0),
                    "metadata": result.get("metadata", {}),
                    "id": result.get("id")
                })
        
        # Convert to RetrievedContext objects
        precedents = []
        for decision in similar_decisions:
            metadata = decision.get("metadata", {})
            scenario = metadata.get("scenario", "")
            reasoning = metadata.get("reasoning", "")
            outcome = metadata.get("outcome", "")
            
            # Build content
            content_parts = [f"Scenario: {scenario}"]
            if reasoning:
                content_parts.append(f"Reasoning: {reasoning}")
            if outcome:
                content_parts.append(f"Outcome: {outcome}")
            
            content = "\n".join(content_parts)
            
            # Create RetrievedContext
            precedent = RetrievedContext(
                content=content,
                score=decision.get("similarity", 0.0),
                source="decision_precedent",
                metadata=metadata
            )
            
            # Add context if requested (only when hybrid search is enabled)
            if include_context and self.knowledge_graph and use_hybrid_search:
                context_entities = self._extract_entities_from_decision(metadata)
                if context_entities:
                    precedent.related_entities = context_entities

                    # Expand context with graph traversal
                    if max_hops > 0:
                        expanded_entities = self._expand_decision_context(
                            context_entities, max_hops
                        )
                        precedent.related_entities.extend(expanded_entities)
            
            precedents.append(precedent)
        
        return precedents

    def query_decisions(
        self,
        query: str,
        max_hops: int = 3,
        include_context: bool = True,
        use_hybrid_search: bool = False,
        limit: int = 10,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[RetrievedContext]:
        """
        Query decisions with multi-hop reasoning capabilities.
        
        Args:
            query: Natural language query
            max_hops: Maximum hops for context expansion
            include_context: Whether to include contextual information
            use_hybrid_search: Whether to use hybrid search
            limit: Number of results
            filters: Optional metadata filters
            
        Returns:
            List of RetrievedContext objects
        """
        return self.retrieve_decision_precedents(
            query=query,
            limit=limit,
            use_hybrid_search=use_hybrid_search,
            max_hops=max_hops,
            include_context=include_context,
            filters=filters
        )

    def get_decision_context(
        self,
        decision_id: str,
        depth: int = 2,
        include_entities: bool = True,
        include_policies: bool = True,
        max_hops: int = 3
    ) -> RetrievedContext:
        """
        Get comprehensive context for a specific decision.
        
        Args:
            decision_id: Decision vector ID
            depth: Context depth
            include_entities: Whether to include entities
            include_policies: Whether to include policies
            max_hops: Maximum hops for context expansion
            
        Returns:
            RetrievedContext with comprehensive decision context
        """
        if not self.vector_store:
            raise ValueError("Vector store required for decision context")
        
        # Get decision metadata
        decision_metadata = self.vector_store.get_metadata(decision_id)
        if not decision_metadata:
            raise ValueError(f"Decision {decision_id} not found")
        
        # Build content
        scenario = decision_metadata.get("scenario", "")
        reasoning = decision_metadata.get("reasoning", "")
        outcome = decision_metadata.get("outcome", "")
        
        content_parts = [f"Decision ID: {decision_id}"]
        content_parts.append(f"Scenario: {scenario}")
        if reasoning:
            content_parts.append(f"Reasoning: {reasoning}")
        if outcome:
            content_parts.append(f"Outcome: {outcome}")
        
        content = "\n".join(content_parts)
        
        # Create RetrievedContext
        context = RetrievedContext(
            content=content,
            score=1.0,  # Perfect match for exact decision
            source="decision_context",
            metadata=decision_metadata
        )
        
        # Add entities
        if include_entities:
            entities = self._extract_entities_from_decision(decision_metadata)
            context.related_entities = entities
            
            # Expand with graph traversal
            if self.knowledge_graph and max_hops > 0:
                expanded_entities = self._expand_decision_context(entities, max_hops)
                context.related_entities.extend(expanded_entities)
        
        # Add policies if requested
        if include_policies and self.knowledge_graph:
            policies = self._find_relevant_policies(decision_metadata)
            context.related_relationships = policies
        
        return context

    def _extract_entities_from_decision(self, metadata: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract entities from decision metadata."""
        entities = []
        
        # Get entities from metadata
        decision_entities = metadata.get("entities", [])
        for entity in decision_entities:
            entities.append({
                "name": entity,
                "type": "entity",
                "source": "decision"
            })
        
        # Add category as entity
        category = metadata.get("category")
        if category:
            entities.append({
                "name": category,
                "type": "category",
                "source": "decision"
            })
        
        return entities

    def _expand_decision_context(
        self,
        entities: List[Dict[str, Any]],
        max_hops: int
    ) -> List[Dict[str, Any]]:
        """Expand decision context using graph traversal and KG algorithms."""
        if not self.knowledge_graph:
            return []
        
        expanded_entities = []
        
        for entity in entities:
            entity_name = entity.get("name")
            if not entity_name:
                continue
            
            # Find related entities using multiple KG algorithms
            try:
                # Basic neighbor expansion — prefer get_neighbors > get_neighbor_ids > neighbors
                # Supports multi-hop BFS when max_hops > 1
                try:
                    def _get_neighbors(node: str) -> List[Any]:
                        if hasattr(self.knowledge_graph, 'get_neighbors'):
                            try:
                                raw = self.knowledge_graph.get_neighbors(node)
                            except TypeError:
                                raw = self.knowledge_graph.get_neighbors(node, hops=1)
                            if isinstance(raw, list):
                                return [n.get("id") if isinstance(n, dict) else n for n in raw if n]
                        elif hasattr(self.knowledge_graph, "get_neighbor_ids"):
                            return list(self.knowledge_graph.get_neighbor_ids(node))
                        elif hasattr(self.knowledge_graph, "neighbors"):
                            return [
                                n.get("id") if isinstance(n, dict) else n
                                for n in self.knowledge_graph.neighbors(node)
                                if n
                            ]
                        return []

                    visited: set = {entity_name}
                    frontier = _get_neighbors(entity_name)
                    for hop in range(1, max_hops + 1):
                        next_frontier: List[Any] = []
                        for neighbor in frontier[:5]:  # Limit per level
                            if neighbor and neighbor not in visited:
                                visited.add(neighbor)
                                expanded_entities.append({
                                    "name": neighbor,
                                    "type": "related_entity",
                                    "source": "graph_expansion",
                                    "parent_entity": entity_name,
                                    "relationship_type": "neighbor",
                                    "hop_distance": hop,
                                })
                                next_hop = _get_neighbors(neighbor)
                                next_frontier.extend(next_hop)
                        frontier = next_frontier
                        if not frontier:
                            break
                except Exception:
                    pass  # Neighbor expansion is best-effort
                
                # Use path finder for multi-hop relationships
                if self.path_finder and max_hops > 1:
                    # Find entities within specified hop distance
                    for other_entity in entities:
                        other_name = other_entity.get("name")
                        if other_name and other_name != entity_name:
                            try:
                                path = self.path_finder.find_shortest_path(
                                    self.knowledge_graph, entity_name, other_name
                                )
                                if path and 1 < len(path) <= max_hops + 1:
                                    # Add intermediate entities from path
                                    for intermediate in path[1:-1]:
                                        expanded_entities.append({
                                            "name": intermediate,
                                            "type": "path_intermediate",
                                            "source": "path_finder",
                                            "parent_entity": entity_name,
                                            "path_length": len(path),
                                            "target_entity": other_name
                                        })
                            except Exception:
                                continue
                
                # Use community detection for contextually related entities
                if self.community_detector:
                    try:
                        communities = self.community_detector.detect_communities(self.knowledge_graph)
                        
                        # Find community of current entity
                        entity_community = None
                        for comm_id, comm_nodes in communities.items():
                            if entity_name in comm_nodes:
                                entity_community = comm_id
                                break
                        
                        # Add other entities from same community
                        if entity_community is not None:
                            same_community_entities = communities[entity_community]
                            for comm_entity in same_community_entities:
                                if comm_entity != entity_name and comm_entity not in [e["name"] for e in expanded_entities]:
                                    expanded_entities.append({
                                        "name": comm_entity,
                                        "type": "community_related",
                                        "source": "community_detector",
                                        "parent_entity": entity_name,
                                        "community_id": entity_community
                                    })
                    except Exception:
                        continue
                
                # Use centrality to rank and prioritize important entities
                if self.centrality_calculator and expanded_entities:
                    try:
                        # Calculate centrality for expanded entities
                        centrality_scores = {}
                        for expanded_entity in expanded_entities:
                            entity_name = expanded_entity["name"]
                            if hasattr(self.centrality_calculator, 'calculate_degree_centrality'):
                                # Simplified centrality calculation
                                if hasattr(self.knowledge_graph, 'get_neighbors'):
                                    if hasattr(self.knowledge_graph, "neighbors"):
                                        neighbor_ids = [
                                            n.get("id") if isinstance(n, dict) else n
                                            for n in self.knowledge_graph.neighbors(entity_name)
                                            if n
                                        ]
                                    elif hasattr(self.knowledge_graph, "get_neighbor_ids"):
                                        neighbor_ids = self.knowledge_graph.get_neighbor_ids(entity_name)
                                    else:
                                        neighbor_details = self.knowledge_graph.get_neighbors(entity_name, hops=1)
                                        neighbor_ids = [
                                            n.get("id") for n in neighbor_details
                                            if isinstance(n, dict) and n.get("id")
                                        ]
                                    centrality_scores[entity_name] = len(neighbor_ids)
                                else:
                                    centrality_scores[entity_name] = 1
                        
                        # Sort by centrality and keep top entities
                        expanded_entities.sort(
                            key=lambda x: centrality_scores.get(x["name"], 0),
                            reverse=True
                        )
                        
                        # Keep only top entities based on centrality
                        expanded_entities = expanded_entities[:10]
                        
                        # Add centrality information
                        for entity in expanded_entities:
                            entity["centrality_score"] = centrality_scores.get(entity["name"], 0)
                            
                    except Exception:
                        continue
                        
            except Exception as e:
                # Sanitize entity name for logging (remove sensitive data)
                safe_entity_name = entity_name[:20] if entity_name else "unknown"
                self.logger.warning(f"Failed to expand context for {safe_entity_name}: {type(e).__name__}")
        
        return expanded_entities

    def _find_relevant_policies(self, metadata: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Find relevant policies for decision."""
        policies = []
        
        if not self.knowledge_graph:
            return policies
        
        # Extract category and look for related policies
        category = metadata.get("category")
        if category:
            try:
                # Look for policy nodes related to category
                if hasattr(self.knowledge_graph, 'get_nodes_by_label'):
                    policy_nodes = self.knowledge_graph.get_nodes_by_label("Policy")
                    for policy in policy_nodes[:5]:  # Limit results
                        policy_name = (
                            policy.get("content")
                            or policy.get("metadata", {}).get("name", "")
                            or policy.get("id", "")
                        ) if isinstance(policy, dict) else policy
                        policies.append({
                            "name": policy_name,
                            "type": "policy",
                            "source": "policy_search",
                            "related_category": category
                        })
            except Exception as e:
                # Sanitize category for logging (remove sensitive data)
                safe_category = category[:20] if category else "unknown"
                self.logger.warning(f"Failed to find policies for {safe_category}: {type(e).__name__}")
                return policies
        return policies

    # Decision Retrieval Methods
    def find_precedents_hybrid(
        self,
        scenario: str,
        category: Optional[str] = None,
        limit: int = 10,
        use_hybrid_search: bool = True,
        max_hops: int = 3
    ) -> List["Decision"]:
        """
        Hybrid precedent search with user controls.
        
        Args:
            scenario: Scenario to find precedents for
            category: Optional category filter
            limit: Maximum number of results
            use_hybrid_search: Use hybrid search (semantic + structural)
            max_hops: Maximum hops for multi-hop reasoning
            
        Returns:
            List of similar decisions
        """
        from .decision_models import Decision
        
        if not self.knowledge_graph:
            return []
        
        try:
            # Use DecisionQuery if available
            if hasattr(self.knowledge_graph, 'execute_query'):
                from .decision_query import DecisionQuery
                query_engine = DecisionQuery(self.knowledge_graph)
                return query_engine.find_precedents_hybrid(scenario, category, limit)
            elif hasattr(self.knowledge_graph, '_decisions'):
                # ContextGraph path — DecisionQuery._find_precedents_basic handles this backend
                from .decision_query import DecisionQuery
                query_engine = DecisionQuery(graph_store=self.knowledge_graph)
                return query_engine.find_precedents_hybrid(
                    scenario, category, limit, use_advanced_features=False
                )
            else:
                # Fallback to simple graph search
                return self._fallback_precedent_search(scenario, category, limit)

        except Exception as e:
            self.logger.error(f"Failed to find precedents: {e}")
            return []

    def retrieve_decisions(
        self,
        query: str,
        category: Optional[str] = None,
        limit: int = 10
    ) -> List["Decision"]:
        """
        Decision-specific retrieval.
        
        Args:
            query: Query string
            category: Optional category filter
            limit: Maximum number of results
            
        Returns:
            List of relevant decisions
        """
        return self.find_precedents_hybrid(query, category, limit)

    def multi_hop_context_assembly(
        self,
        start_node: str,
        query_context: str,
        max_hops: int = 3,
        include_context: bool = True
    ) -> Dict[str, Any]:
        """
        Dynamic context assembly with user controls.
        
        Args:
            start_node: Starting node ID
            query_context: Query context
            max_hops: Maximum hops to traverse
            include_context: Include full context
            
        Returns:
            Assembled context with decisions
        """
        if not self.knowledge_graph:
            return {"context": [], "decisions": [], "metadata": {}}
        
        try:
            # Get multi-hop context
            context = self.expand_context(start_node, max_hops=max_hops)
            
            # Find related decisions
            decisions = []
            query_engine = self._get_decision_query()
            if query_engine is not None:
                try:
                    decisions = query_engine.multi_hop_reasoning(start_node, query_context, max_hops)
                except Exception:
                    decisions = []
            
            return {
                "context": context,
                "decisions": decisions,
                "metadata": {
                    "start_node": start_node,
                    "query_context": query_context,
                    "max_hops": max_hops,
                    "context_count": len(context),
                    "decision_count": len(decisions)
                }
            }
            
        except Exception as e:
            self.logger.error(f"Failed multi-hop context assembly: {e}")
            return {"context": [], "decisions": [], "metadata": {}}

    def graph_augmented_generation(
        self,
        query: str,
        graph_context: Dict[str, Any]
    ) -> str:
        """
        GAG for reduced hallucinations.
        
        Args:
            query: Query string
            graph_context: Graph context from multi-hop assembly
            
        Returns:
            Augmented response with context
        """
        context_text = ""
        
        # Format decisions from context
        decisions = graph_context.get("decisions", [])
        if decisions:
            context_text += "Relevant Decisions:\n"
            for decision in decisions[:5]:  # Limit to top 5
                context_text += f"- {decision.scenario} (Category: {decision.category})\n"
                context_text += f"  Reasoning: {decision.reasoning[:200]}...\n"
                context_text += f"  Outcome: {decision.outcome}\n\n"
        
        # Format entities from context
        entities = graph_context.get("context", [])
        if entities:
            context_text += "Related Entities:\n"
            for entity in entities[:10]:  # Limit to top 10
                context_text += f"- {entity.get('name', 'Unknown')} ({entity.get('type', 'Unknown')})\n"
        
        # Generate augmented response
        if context_text:
            return f"Based on the following context:\n\n{context_text}\nQuery: {query}\n\nResponse would be generated by LLM with this context."
        else:
            return f"Query: {query}\n\nNo relevant context found."

    def explainable_retrieval(self, decision_id: str) -> Dict[str, Any]:
        """
        Trace relationship paths for explainability.
        
        Args:
            decision_id: Decision ID to trace
            
        Returns:
            Explainability information
        """
        if not self.knowledge_graph:
            return {"error": "Knowledge graph not available"}
        
        try:
            # Get decision details
            decision_context = self.expand_context(decision_id, max_hops=1)
            
            # Trace paths using graph traversal
            paths = []
            if hasattr(self.knowledge_graph, 'execute_query'):
                query = """
                MATCH path = (d:Decision {decision_id: $decision_id})-[*1..3]-(related)
                RETURN path, length(path) as path_length
                ORDER BY path_length
                LIMIT 10
                """
                results = self.knowledge_graph.execute_query(query, {"decision_id": decision_id})
                paths = [record.get("path") for record in results]
            
            return {
                "decision_id": decision_id,
                "context": decision_context,
                "relationship_paths": paths,
                "path_count": len(paths)
            }
            
        except Exception as e:
            self.logger.error(f"Failed explainable retrieval: {e}")
            return {"error": "An error occurred during explainable retrieval. Please check the logs for details."}

    def dynamic_context_traversal(
        self,
        query: str,
        entity_types: List[str],
        max_hops: int = 4
    ) -> Dict[str, Any]:
        """
        Dynamic context assembly with entity filtering.
        
        Args:
            query: Query string
            entity_types: List of entity types to filter
            max_hops: Maximum hops to traverse
            
        Returns:
            Filtered context results
        """
        if not self.knowledge_graph:
            return {"context": [], "metadata": {}}
        
        try:
            # Find relevant entities based on query
            relevant_entities = []
            
            # Use vector search to find initial entities
            vector_results = self.vector_search(query, limit=20)
            for result in vector_results:
                if result.get("type") in entity_types:
                    relevant_entities.append(result)
            
            # Expand context for all relevant entities via single traversal
            raw_context = self.expand_context(query, max_hops=max_hops)
            expanded_context = [
                item for item in raw_context
                if item.get("type") in entity_types
            ]
            
            return {
                "query": query,
                "entity_types": entity_types,
                "max_hops": max_hops,
                "context": expanded_context,
                "metadata": {
                    "initial_entities": len(relevant_entities),
                    "expanded_context": len(expanded_context)
                }
            }
            
        except Exception as e:
            self.logger.error(f"Failed dynamic context traversal: {e}")
            return {"context": [], "metadata": {}}

    def hybrid_retrieval(
        self,
        query: str,
        use_vector: bool = True,
        use_graph: bool = True
    ) -> Dict[str, Any]:
        """
        Combine vector search with graph traversal.
        
        Args:
            query: Query string
            use_vector: Use vector search
            use_graph: Use graph traversal
            
        Returns:
            Hybrid retrieval results
        """
        results = {"query": query, "vector_results": [], "graph_results": [], "hybrid_results": []}
        
        try:
            # Vector search
            if use_vector:
                results["vector_results"] = self.vector_search(query, limit=20)
            
            # Graph search
            if use_graph:
                graph_context = self.expand_context(query, max_hops=2)
                results["graph_results"] = graph_context
            
            # Combine results
            all_results = results["vector_results"] + results["graph_results"]
            
            # Deduplicate and rank
            seen = set()
            hybrid_results = []
            for result in all_results:
                result_id = result.get("name") or result.get("id") or str(hash(result.get("content", "")))
                if result_id not in seen:
                    seen.add(result_id)
                    hybrid_results.append(result)
            
            results["hybrid_results"] = hybrid_results[:20]  # Limit final results
            
        except Exception as e:
            self.logger.error(f"Failed hybrid retrieval: {e}")
        
        return results

    def _fallback_precedent_search(
        self,
        scenario: str,
        category: Optional[str],
        limit: int
    ) -> List["Decision"]:
        """Fallback precedent search when DecisionQuery is not available."""
        from .decision_models import Decision
        
        decisions = []
        
        try:
            # Simple graph search for decision nodes
            if hasattr(self.knowledge_graph, 'get_nodes_by_label'):
                decision_nodes = self.knowledge_graph.get_nodes_by_label("Decision")
                
                for node_data in decision_nodes[:limit]:
                    metadata = {}
                    if isinstance(node_data, dict):
                        metadata = node_data.get("metadata") or node_data.get("properties") or {}
                    # Convert to Decision object
                    decision = Decision(
                        decision_id=node_data.get("id", "") if isinstance(node_data, dict) else "",
                        category=metadata.get("category", ""),
                        scenario=node_data.get("content", "") if isinstance(node_data, dict) else "",
                        reasoning=metadata.get("reasoning", ""),
                        outcome=metadata.get("outcome", ""),
                        confidence=metadata.get("confidence", 0.0),
                        timestamp=datetime.now(),
                        decision_maker=metadata.get("decision_maker", ""),
                        metadata=metadata
                    )
                    
                    # Filter by category if specified
                    if category and decision.category != category:
                        continue
                    
                    decisions.append(decision)
        
        except Exception as e:
            self.logger.error(f"Fallback precedent search failed: {e}")
        
        return decisions

    def _extract_entities_from_query(self, query: str) -> List[str]:
        """Extract potential entity names from query."""
        # Simple entity extraction - could be enhanced with NER
        entities = []

        # Split query and look for capitalized terms (potential entities)
        words = query.split()
        for word in words:
            # Strip punctuation for length check but keep original
            stripped = word.strip(".,;:!?")
            if stripped and stripped[0].isupper() and len(stripped) > 2:
                entities.append(stripped)

        return entities[:10]  # Limit entities

    def expand_context(
        self,
        entity_id: str,
        max_hops: int = 2
    ) -> List[Dict[str, Any]]:
        """
        Expand context for an entity using graph traversal.

        Args:
            entity_id: Entity ID or query term to expand context for
            max_hops: Maximum hops to traverse

        Returns:
            List of related context items
        """
        if not self.knowledge_graph:
            return []

        try:
            results = []
            visited: set = {entity_id}
            current_level = [entity_id]

            for hop in range(max_hops):
                next_level = []
                for node in current_level:
                    try:
                        neighbors = self.knowledge_graph.get_neighbors(node)
                        for neighbor in (neighbors or []):
                            if neighbor not in visited:
                                visited.add(neighbor)
                                next_level.append(neighbor)
                                results.append({
                                    "id": neighbor,
                                    "type": "Unknown",
                                    "content": str(neighbor),
                                    "hop": hop + 1
                                })
                    except Exception:
                        pass
                current_level = next_level
                if not current_level:
                    break

            return results

        except Exception as e:
            self.logger.error(f"Context expansion failed: {e}")
            return []

    def _get_decision_query(self):
        """Get a DecisionQuery instance for the current knowledge graph."""
        if not self.knowledge_graph:
            return None
        try:
            from .decision_query import DecisionQuery
            return DecisionQuery(self.knowledge_graph)
        except Exception:
            return None


class TemporalGraphRetriever:
    """
    Drop-in temporal wrapper for any ContextRetriever.

    Calls ``base_retriever.retrieve(query)``, then filters ``related_entities``
    and ``related_relationships`` in each :class:`RetrievedContext` item to
    those active at *at_time* using
    :meth:`~semantica.kg.temporal_query.TemporalGraphQuery.reconstruct_at_time`.

    When no *at_time* is set (neither in the constructor nor at the call site)
    the base retriever result is returned unchanged — no copies, no filtering.

    Example::

        from semantica.context import ContextRetriever, TemporalGraphRetriever

        base = ContextRetriever(knowledge_graph=kg)
        retriever = TemporalGraphRetriever(base, at_time="2023-06-01")
        results = retriever.retrieve("which suppliers were certified?")
        # related_entities / related_relationships in each result are valid as
        # of 2023-06-01; dangling edges are removed automatically.
    """

    _DEFAULT_HEADER = "[Graph context valid as of: {at_time} UTC | Source: {source}]"

    def __init__(
        self,
        base_retriever: "ContextRetriever",
        at_time: Optional[Any] = None,
        header_template: str = _DEFAULT_HEADER,
    ):
        """
        Args:
            base_retriever: Any :class:`ContextRetriever` instance to wrap.
            at_time: Default point-in-time for temporal filtering. Accepts a
                :class:`~datetime.datetime` or any string parseable by
                :func:`~semantica.kg.temporal_model.parse_temporal_value`
                (e.g. ``"2023-06-01"``). ``None`` disables filtering.
            header_template: Format string used to build the temporal context
                header injected into LLM prompts by
                :meth:`ContextRetriever.query_with_reasoning`. Placeholders:
                ``{at_time}`` and ``{source}``.

        Example:
            >>> from semantica.context import ContextRetriever, TemporalGraphRetriever

            >>> # Passthrough — no temporal filtering applied
            >>> base = ContextRetriever(knowledge_graph=kg)
            >>> retriever = TemporalGraphRetriever(base)
            >>> results = retriever.retrieve("active suppliers")  # identical to base.retrieve()

            >>> # Point-in-time snapshot — ISO string shorthand
            >>> retriever = TemporalGraphRetriever(base, at_time="2023-06-01")
            >>> results = retriever.retrieve("certified suppliers")
            >>> # related_entities/related_relationships are valid as of 2023-06-01

            >>> # Custom prompt header for LLM context
            >>> retriever = TemporalGraphRetriever(
            ...     base,
            ...     at_time="2023-06-01",
            ...     header_template="[Snapshot: {at_time} | {source}]",
            ... )

            >>> # Combine with TemporalQueryRewriter for end-to-end temporal RAG
            >>> from semantica.kg import TemporalQueryRewriter
            >>> rw = TemporalQueryRewriter()
            >>> parsed = rw.rewrite("which suppliers were certified before 2022?")
            >>> retriever = TemporalGraphRetriever(base, at_time=parsed.at_time)
            >>> results = retriever.retrieve(parsed.rewritten_query)
        """
        if not _TEMPORAL_AVAILABLE:
            raise ImportError(
                "TemporalGraphRetriever requires the semantica.kg temporal modules "
                "(temporal_query, temporal_model). Ensure they are installed and "
                "importable without errors."
            )
        self.base_retriever = base_retriever
        self.at_time = at_time
        self.header_template = header_template
        self._tgq = _TemporalGraphQuery()

    def retrieve(
        self,
        query: str,
        at_time: Optional[Any] = None,
        **kwargs,
    ) -> List[RetrievedContext]:
        """
        Retrieve context and apply point-in-time temporal filtering.

        Args:
            query: Search query forwarded to the base retriever.
            at_time: Override the instance-level ``at_time`` for this call.
                ``None`` falls back to the constructor value; if both are
                ``None`` the base result is returned unchanged.
            **kwargs: Forwarded to ``base_retriever.retrieve()``.

        Returns:
            List of :class:`RetrievedContext` items whose
            ``related_entities`` and ``related_relationships`` are restricted
            to facts valid at *at_time*. Dangling relationships (whose
            source or target entity was filtered out) are removed.

        Example:
            >>> from datetime import datetime, timezone
            >>> from semantica.context import ContextRetriever, TemporalGraphRetriever

            >>> base = ContextRetriever(knowledge_graph=kg)
            >>> retriever = TemporalGraphRetriever(base, at_time="2023-06-01")

            >>> # Use constructor at_time
            >>> results = retriever.retrieve("drug interactions")
            >>> for r in results:
            ...     print(len(r.related_entities), "entities valid as of 2023-06-01")

            >>> # Override at_time per call (e.g. from TemporalQueryRewriter output)
            >>> results_q1 = retriever.retrieve(
            ...     "capital requirements",
            ...     at_time=datetime(2023, 3, 31, tzinfo=timezone.utc),
            ... )

            >>> # Passthrough: no at_time → base result unchanged
            >>> retriever_plain = TemporalGraphRetriever(base)
            >>> plain = retriever_plain.retrieve("suppliers")  # no temporal filtering
        """
        import dataclasses

        effective_at_time = at_time if at_time is not None else self.at_time
        results = self.base_retriever.retrieve(query, **kwargs)
        if effective_at_time is None:
            return results
        parsed = (
            effective_at_time
            if isinstance(effective_at_time, datetime)
            else _parse_temporal_value(effective_at_time)
        )
        filtered_results = []
        for ctx in results:
            subgraph = {
                "entities": ctx.related_entities,
                "relationships": ctx.related_relationships,
            }
            filtered = self._tgq.reconstruct_at_time(subgraph, parsed)
            # Return a new RetrievedContext rather than mutating the original
            # so callers that hold a reference to the base retriever's results
            # are not surprised by side-effects.
            filtered_results.append(dataclasses.replace(
                ctx,
                related_entities=filtered["entities"],
                related_relationships=filtered["relationships"],
            ))
        return filtered_results
