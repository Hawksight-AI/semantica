"""
Provenance-enabled wrappers for reasoning operations.

Tracks: premises, conclusions, inference rules, confidence scores

Usage:
    from semantica.reasoning.reasoning_provenance import ReasoningEngineWithProvenance
    
    reasoner = ReasoningEngineWithProvenance(provenance=True)
    result = reasoner.infer(premises)

Author: Semantica Contributors
License: MIT
"""

from typing import Any, Optional
from datetime import datetime
import uuid


class ReasoningEngineWithProvenance:
    """Reasoning engine with provenance tracking."""

    def __init__(
        self,
        provenance: bool = False,
        agent_id: Optional[str] = None,
        is_automated: bool = True,
        **config,
    ):
        from .reasoner import Reasoner

        self.provenance = provenance
        self._engine = Reasoner(**config)
        self._prov_manager = None
        self._agent_id = agent_id or self.__class__.__name__
        self._is_automated = is_automated

        if provenance:
            try:
                from semantica.provenance import ProvenanceManager
                self._prov_manager = ProvenanceManager()
            except ImportError:
                self.provenance = False

    def infer(self, premises: Any, source: str = None, **kwargs):
        """Perform inference with provenance tracking."""
        activity_started_at_time = datetime.utcnow().isoformat()
        result = self._engine.infer_facts(premises, **kwargs)
        activity_ended_at_time = datetime.utcnow().isoformat()

        if self.provenance and self._prov_manager:
            self._prov_manager.track_entity(
                entity_id=f"inference_{uuid.uuid4().hex[:8]}",
                source=source or "reasoning_engine",
                entity_type="inference",
                agent_id=self._agent_id,
                agent_type="software_agent",
                is_automated=self._is_automated,
                activity_started_at_time=activity_started_at_time,
                activity_ended_at_time=activity_ended_at_time,
                metadata={
                    "premises_count": len(premises) if hasattr(premises, '__len__') else 1,
                    "confidence": getattr(result, 'confidence', None)
                }
            )
        
        return result
    
    def __getattr__(self, name):
        return getattr(self._engine, name)


__all__ = ['ReasoningEngineWithProvenance']
