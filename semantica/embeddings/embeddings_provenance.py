"""
Provenance-enabled wrappers for embedding generation.

Tracks: model, dimensions, input texts, embedding vectors

Usage:
    from semantica.embeddings.embeddings_provenance import EmbeddingGeneratorWithProvenance
    
    embedder = EmbeddingGeneratorWithProvenance(provenance=True)
    embeddings = embedder.embed(["text1", "text2"])

Author: Semantica Contributors
License: MIT
"""

from typing import List, Optional
from datetime import datetime
import uuid


class EmbeddingGeneratorWithProvenance:
    """Embedding generator with provenance tracking."""

    def __init__(
        self,
        provenance: bool = False,
        agent_id: Optional[str] = None,
        is_automated: bool = True,
        **config,
    ):
        from .embedding_generator import EmbeddingGenerator

        self.provenance = provenance
        self._generator = EmbeddingGenerator(**config)
        self._prov_manager = None
        self._agent_id = agent_id or self.__class__.__name__
        self._is_automated = is_automated

        if provenance:
            try:
                from semantica.provenance import ProvenanceManager
                self._prov_manager = ProvenanceManager()
            except ImportError:
                self.provenance = False

    def embed(self, texts: List[str], source: str = None, **kwargs):
        """Generate embeddings with provenance tracking."""
        activity_started_at_time = datetime.utcnow().isoformat()
        embeddings = self._generator.embed(texts, **kwargs)
        activity_ended_at_time = datetime.utcnow().isoformat()

        if self.provenance and self._prov_manager:
            self._prov_manager.track_entity(
                entity_id=f"embed_{uuid.uuid4().hex[:8]}",
                source=source or "embedding_generation",
                entity_type="embeddings",
                agent_id=self._agent_id,
                agent_type="software_agent",
                is_automated=self._is_automated,
                activity_started_at_time=activity_started_at_time,
                activity_ended_at_time=activity_ended_at_time,
                metadata={
                    "model": getattr(self._generator, 'model', 'unknown'),
                    "dimensions": len(embeddings[0]) if embeddings else 0,
                    "count": len(embeddings)
                }
            )
        
        return embeddings
    
    def __getattr__(self, name):
        # __getattr__ only runs when normal lookup fails. Accessing
        # self._generator by attribute syntax HERE would re-enter
        # __getattr__ for ever when _generator itself is missing — the shape
        # pickle/copy protocol probes hit when __init__ never completed
        # (#994's RecursionError family). Fail fast on private probes.
        if name.startswith("_"):
            raise AttributeError(
                f"{type(self).__name__!r} object has no attribute {name!r}"
            )
        return getattr(self._generator, name)


__all__ = ['EmbeddingGeneratorWithProvenance']
