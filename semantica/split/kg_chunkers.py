"""
KG/Ontology-Specific Chunkers Module

This module provides specialized chunkers for knowledge graph, ontology, and graph
analytics workflows, designed to preserve graph structure and semantic relationships.

Supported Chunkers:
    - EntityAwareChunker: Preserves entity boundaries
    - RelationAwareChunker: Preserves triplet integrity
    - GraphBasedChunker: Uses graph structure for chunking
    - OntologyAwareChunker: Uses ontology concepts for chunking
    - HierarchicalChunker: Multi-level hierarchical chunking

Algorithms Used:
    - Entity Boundary Detection: NER-based entity extraction and boundary preservation
    - Triplet Preservation: Graph-based triplet integrity checking
    - Graph Centrality Analysis: Degree, betweenness, closeness, eigenvector centrality
    - Community Detection: Louvain algorithm, Leiden algorithm, modularity optimization
    - Graph Connectivity: Connected components, shortest paths, bridge detection
    - Ontology Hierarchy Traversal: Taxonomic structure traversal and concept grouping

Key Features:
    - Entity boundary preservation for GraphRAG
    - Triplet integrity preservation for KG workflows
    - Graph structure-aware chunking
    - Ontology concept-aware chunking
    - Hierarchical multi-level chunking
    - Integration with semantic extraction module

Main Classes:
    - EntityAwareChunker: Entity boundary-preserving chunker
    - RelationAwareChunker: Triplet-preserving chunker
    - GraphBasedChunker: Graph structure-based chunker
    - OntologyAwareChunker: Ontology concept-based chunker
    - HierarchicalChunker: Multi-level hierarchical chunker

Example Usage:
    >>> from semantica.split.kg_chunkers import EntityAwareChunker
    >>> chunker = EntityAwareChunker(chunk_size=1000, ner_method="llm")
    >>> chunks = chunker.chunk(text)

Author: Semantica Contributors
License: MIT
"""

from typing import Any, Dict, List, Optional, Union

from ..utils.logging import get_logger
from ..utils.progress_tracker import get_progress_tracker
from .methods import (
    split_entity_aware,
    split_graph_based,
    split_hierarchical,
    split_ontology_aware,
    split_relation_aware,
)
from .semantic_chunker import Chunk

logger = get_logger("kg_chunkers")


class EntityAwareChunker:
    """
    Entity boundary-preserving chunker for GraphRAG workflows.

    Ensures that entities and their associated information are kept together,
    preserving the semantic integrity necessary for accurate graph-based retrieval.
    """

    def __init__(
        self,
        chunk_size: int = 1000,
        chunk_overlap: int = 200,
        ner_method: str = "ml",
        preserve_entities: bool = True,
        **kwargs,
    ):
        """
        Initialize entity-aware chunker.

        Args:
            chunk_size: Target chunk size
            chunk_overlap: Overlap between chunks
            ner_method: NER method to use ("pattern", "regex", "ml", "huggingface", "llm")
            preserve_entities: Whether to preserve entity boundaries
            **kwargs: Additional options for NER extractor
        """
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.ner_method = ner_method
        self.preserve_entities = preserve_entities
        self.options = kwargs
        self.logger = get_logger("entity_aware_chunker")
        self.progress_tracker = get_progress_tracker()
        # Ensure progress tracker is enabled
        if not self.progress_tracker.enabled:
            self.progress_tracker.enabled = True

    def chunk(self, text: str, **options) -> List[Chunk]:
        """
        Chunk text preserving entity boundaries.

        Args:
            text: Input text
            **options: Additional options

        Returns:
            List of chunks
        """
        tracking_id = self.progress_tracker.start_tracking(
            module="split",
            submodule="EntityAwareChunker",
            message="Chunking text with entity awareness",
        )

        try:
            merged_options = {**self.options, **options}
            chunks = split_entity_aware(
                text,
                chunk_size=self.chunk_size,
                ner_method=self.ner_method,
                preserve_entities=self.preserve_entities,
                **merged_options,
            )

            self.progress_tracker.stop_tracking(
                tracking_id,
                status="completed",
                message=f"Created {len(chunks)} entity-aware chunks",
            )
            return chunks

        except Exception as e:
            self.progress_tracker.stop_tracking(
                tracking_id, status="failed", message=str(e)
            )
            raise


class RelationAwareChunker:
    """
    Triplet-preserving chunker for KG workflows.

    Ensures that relation triplets (subject-predicate-object) are preserved within
    the same chunk, preventing the loss of relational context.
    """

    def __init__(
        self,
        chunk_size: int = 1000,
        chunk_overlap: int = 200,
        relation_method: str = "ml",
        preserve_triplets: bool = True,
        **kwargs,
    ):
        """
        Initialize relation-aware chunker.

        Args:
            chunk_size: Target chunk size
            chunk_overlap: Overlap between chunks
            relation_method: Relation extraction method
            preserve_triplets: Whether to preserve triplet integrity
            **kwargs: Additional options for relation extractor
        """
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.relation_method = relation_method
        self.preserve_triplets = preserve_triplets
        self.options = kwargs
        self.logger = get_logger("relation_aware_chunker")
        self.progress_tracker = get_progress_tracker()
        # Ensure progress tracker is enabled
        if not self.progress_tracker.enabled:
            self.progress_tracker.enabled = True

    def chunk(self, text: str, **options) -> List[Chunk]:
        """
        Chunk text preserving triplet integrity.

        Args:
            text: Input text
            **options: Additional options

        Returns:
            List of chunks
        """
        tracking_id = self.progress_tracker.start_tracking(
            module="split",
            submodule="RelationAwareChunker",
            message="Chunking text with relation awareness",
        )

        try:
            merged_options = {**self.options, **options}
            chunks = split_relation_aware(
                text,
                chunk_size=self.chunk_size,
                relation_method=self.relation_method,
                preserve_triplets=self.preserve_triplets,
                **merged_options,
            )

            self.progress_tracker.stop_tracking(
                tracking_id,
                status="completed",
                message=f"Created {len(chunks)} relation-aware chunks",
            )
            return chunks

        except Exception as e:
            self.progress_tracker.stop_tracking(
                tracking_id, status="failed", message=str(e)
            )
            raise


class GraphBasedChunker:
    """
    Graph structure-based chunker using centrality or communities.

    Uses graph analysis (centrality measures, community detection) to determine
    optimal chunk boundaries based on the underlying knowledge graph structure.
    """

    def __init__(
        self,
        chunk_size: int = 1000,
        strategy: str = "community",
        algorithm: str = "louvain",
        **kwargs,
    ):
        """
        Initialize graph-based chunker.

        Args:
            chunk_size: Target chunk size
            strategy: Strategy ("community", "centrality")
            algorithm: Algorithm name ("louvain", "leiden", "betweenness", etc.)
            **kwargs: Additional options
        """
        self.chunk_size = chunk_size
        self.strategy = strategy
        self.algorithm = algorithm
        self.options = kwargs
        self.logger = get_logger("graph_based_chunker")
        self.progress_tracker = get_progress_tracker()
        # Ensure progress tracker is enabled
        if not self.progress_tracker.enabled:
            self.progress_tracker.enabled = True

    def chunk(self, text: str, **options) -> List[Chunk]:
        """
        Chunk text using graph structure.

        Args:
            text: Input text
            **options: Additional options

        Returns:
            List of chunks
        """
        tracking_id = self.progress_tracker.start_tracking(
            module="split",
            submodule="GraphBasedChunker",
            message="Chunking text using graph structure",
        )

        try:
            merged_options = {**self.options, **options}
            chunks = split_graph_based(
                text,
                chunk_size=self.chunk_size,
                strategy=self.strategy,
                algorithm=self.algorithm,
                **merged_options,
            )

            self.progress_tracker.stop_tracking(
                tracking_id,
                status="completed",
                message=f"Created {len(chunks)} graph-based chunks",
            )
            return chunks

        except Exception as e:
            self.progress_tracker.stop_tracking(
                tracking_id, status="failed", message=str(e)
            )
            raise


class OntologyAwareChunker:
    """
    Ontology concept and hierarchy-based chunker.

    Chunks text based on ontology concepts, hierarchies, and taxonomic structures,
    ensuring alignment with domain-specific concepts and terminologies.
    """

    def __init__(
        self,
        chunk_size: int = 1000,
        ontology_uri: Optional[str] = None,
        preserve_concepts: bool = True,
        **kwargs,
    ):
        """
        Initialize ontology-aware chunker.

        Args:
            chunk_size: Target chunk size
            ontology_uri: Ontology URI (optional)
            preserve_concepts: Whether to preserve concept boundaries
            **kwargs: Additional options
        """
        self.chunk_size = chunk_size
        self.ontology_uri = ontology_uri
        self.preserve_concepts = preserve_concepts
        self.options = kwargs
        self.logger = get_logger("ontology_aware_chunker")
        self.progress_tracker = get_progress_tracker()
        # Ensure progress tracker is enabled
        if not self.progress_tracker.enabled:
            self.progress_tracker.enabled = True

    def chunk(self, text: str, **options) -> List[Chunk]:
        """
        Chunk text using ontology concepts.

        Args:
            text: Input text
            **options: Additional options

        Returns:
            List of chunks
        """
        tracking_id = self.progress_tracker.start_tracking(
            module="split",
            submodule="OntologyAwareChunker",
            message="Chunking text using ontology concepts",
        )

        try:
            merged_options = {**self.options, **options}
            chunks = split_ontology_aware(
                text,
                chunk_size=self.chunk_size,
                ontology_uri=self.ontology_uri,
                preserve_concepts=self.preserve_concepts,
                **merged_options,
            )

            self.progress_tracker.stop_tracking(
                tracking_id,
                status="completed",
                message=f"Created {len(chunks)} ontology-aware chunks",
            )
            return chunks

        except Exception as e:
            self.progress_tracker.stop_tracking(
                tracking_id, status="failed", message=str(e)
            )
            raise


class HierarchicalChunker:
    """
    Multi-level hierarchical chunker.

    Creates multiple layers of chunks, from fine-grained (sentences) to coarse-grained
    (sections), allowing for retrieval at various levels of granularity.
    """

    def __init__(
        self,
        levels: Optional[List[str]] = None,
        chunk_sizes: Optional[List[int]] = None,
        **kwargs,
    ):
        if levels is None:
            levels = ["section", "paragraph", "sentence"]
        """
        Initialize hierarchical chunker.

        Args:
            levels: Hierarchy levels (e.g., ["section", "paragraph", "sentence"])
            chunk_sizes: Chunk sizes for each level
            **kwargs: Additional options
        """
        self.levels = levels
        self.chunk_sizes = chunk_sizes or [2000, 1000, 500]
        self.options = kwargs
        self.logger = get_logger("hierarchical_chunker")
        self.progress_tracker = get_progress_tracker()
        # Ensure progress tracker is enabled
        if not self.progress_tracker.enabled:
            self.progress_tracker.enabled = True

    def chunk(self, text: str, **options) -> List[Chunk]:
        """
        Chunk text hierarchically.

        Args:
            text: Input text
            **options: Additional options

        Returns:
            List of chunks with hierarchical metadata
        """
        tracking_id = self.progress_tracker.start_tracking(
            module="split",
            submodule="HierarchicalChunker",
            message="Chunking text hierarchically",
        )

        try:
            merged_options = {**self.options, **options}
            chunks = split_hierarchical(
                text, levels=self.levels, chunk_sizes=self.chunk_sizes, **merged_options
            )

            # Add hierarchical metadata
            for chunk in chunks:
                chunk.metadata["hierarchical"] = True
                chunk.metadata["levels"] = self.levels

            self.progress_tracker.stop_tracking(
                tracking_id,
                status="completed",
                message=f"Created {len(chunks)} hierarchical chunks",
            )
            return chunks

        except Exception as e:
            self.progress_tracker.stop_tracking(
                tracking_id, status="failed", message=str(e)
            )
            raise
