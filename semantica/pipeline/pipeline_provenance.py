"""
Provenance-enabled wrapper for pipeline execution.

This module provides provenance tracking for end-to-end pipeline workflows,
capturing all steps, inputs, outputs, and transformations.

Usage:
    from semantica.pipeline.pipeline_provenance import PipelineWithProvenance
    from semantica.pipeline import PipelineBuilder

    builder = PipelineBuilder()
    builder.add_step("ingest", "file_ingest")
    pipeline = builder.build("my_pipeline")

    runner = PipelineWithProvenance(pipeline, provenance=True)
    result = runner.run(data)
    # Tracks all pipeline steps with complete lineage

Author: Semantica Contributors
License: MIT
"""

from typing import Optional, Any, Dict, List
from datetime import datetime, timezone
import uuid
import time

from .pipeline_builder import Pipeline
from .execution_engine import ExecutionEngine


class PipelineWithProvenance:
    """Pipeline executor with complete provenance tracking."""

    def __init__(
        self,
        pipeline: Pipeline,
        provenance: bool = False,
        agent_id: Optional[str] = None,
        is_automated: bool = True,
        **engine_config,
    ):
        """Initialize provenance-tracked pipeline runner.

        Args:
            pipeline: A built Pipeline instance (from PipelineBuilder.build()).
            provenance: Whether to record provenance metadata.
            agent_id: Identifier for the agent running the pipeline.
            is_automated: Whether the execution is automated (vs. human-triggered).
            **engine_config: Extra keyword arguments forwarded to ExecutionEngine.
        """
        self._pipeline = pipeline
        self._engine = ExecutionEngine(**engine_config)
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

    def run(self, data: Any = None, source: Optional[str] = None, **kwargs):
        """Run pipeline with provenance tracking.

        Args:
            data: Input data to feed into the pipeline.
            source: Provenance source label (defaults to "pipeline_execution").
            **kwargs: Extra options forwarded to ExecutionEngine.execute_pipeline().

        Returns:
            ExecutionResult from the engine.
        """
        pipeline_id = f"pipeline_{uuid.uuid4().hex[:8]}"
        start_time = time.time()
        activity_started_at_time = datetime.now(timezone.utc).isoformat()

        result = self._engine.execute_pipeline(self._pipeline, data=data, **kwargs)
        elapsed = time.time() - start_time
        activity_ended_at_time = datetime.now(timezone.utc).isoformat()

        if self.provenance and self._prov_manager:
            self._prov_manager.track_entity(
                entity_id=pipeline_id,
                source=source or "pipeline_execution",
                entity_type="pipeline_run",
                agent_id=self._agent_id,
                agent_type="software_agent",
                is_automated=self._is_automated,
                activity_id=pipeline_id,
                activity_started_at_time=activity_started_at_time,
                activity_ended_at_time=activity_ended_at_time,
                metadata={
                    "steps": len(self._pipeline.steps),
                    "duration_seconds": elapsed,
                    "status": "completed" if result.success else "failed",
                }
            )

        return result

    def __getattr__(self, name):
        return getattr(self._pipeline, name)


__all__ = ['PipelineWithProvenance']
