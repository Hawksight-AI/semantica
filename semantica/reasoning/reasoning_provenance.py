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

import uuid
from datetime import datetime
from typing import Any, Optional


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
        self._engine = Reasoner(provenance=provenance, **config)
        self._prov_manager = None
        self._agent_id = agent_id or self.__class__.__name__
        self._is_automated = is_automated

        if provenance:
            try:
                from semantica.provenance import ProvenanceManager
                self._prov_manager = ProvenanceManager()
            except ImportError:
                self.provenance = False

    def infer(self, premises: Any, source: str = None, rules: Any = None):
        """Perform inference with provenance tracking.

        Only the reasoner's real parameters (``premises`` and ``rules``) are
        forwarded to the underlying engine; arbitrary keyword arguments are no
        longer passed through (they previously reached
        ``Reasoner.infer_facts`` -- which accepts only ``facts``/``rules`` --
        and raised ``TypeError``).
        """
        activity_started_at_time = datetime.utcnow().isoformat()
        results = self._engine.infer_with_results(premises, rules)
        activity_ended_at_time = datetime.utcnow().isoformat()

        # Aggregate confidence across the derived results (min = weakest link);
        # None only when nothing was inferred.
        confidence = (
            min(r.confidence for r in results) if results else None
        )
        # Preserve the historical return shape: a list of conclusion strings.
        inferred = [r.conclusion for r in results]

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
                    "confidence": confidence,
                }
            )
        
        return inferred
    
    def __getattr__(self, name):
        return getattr(self._engine, name)


__all__ = ['ReasoningEngineWithProvenance']
