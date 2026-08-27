"""
Provenance-enabled wrappers for export operations.

Tracks: export format, destination, timestamp, data exported

Usage:
    from semantica.export.export_provenance import JSONExporterWithProvenance
    
    exporter = JSONExporterWithProvenance(provenance=True)
    exporter.export(data, "output.json")

Author: Semantica Contributors
License: MIT
"""

from typing import Any, Optional
import uuid

from ..utils.helpers import utc_now_iso


class ExporterWithProvenance:
    """Base exporter with provenance tracking."""

    def __init__(
        self,
        provenance: bool = False,
        agent_id: Optional[str] = None,
        is_automated: bool = True,
        **config,
    ):
        from .exporter import Exporter

        self.provenance = provenance
        self._exporter = Exporter(**config)
        self._prov_manager = None
        self._agent_id = agent_id or self.__class__.__name__
        self._is_automated = is_automated

        if provenance:
            try:
                from semantica.provenance import ProvenanceManager
                self._prov_manager = ProvenanceManager()
            except ImportError:
                self.provenance = False

    def export(self, data: Any, destination: str, **kwargs):
        """Export data with provenance tracking."""
        activity_started_at_time = utc_now_iso()
        result = self._exporter.export(data, destination, **kwargs)
        activity_ended_at_time = utc_now_iso()

        if self.provenance and self._prov_manager:
            self._prov_manager.track_entity(
                entity_id=f"export_{uuid.uuid4().hex[:8]}",
                source="export_operation",
                entity_type="export",
                agent_id=self._agent_id,
                agent_type="software_agent",
                is_automated=self._is_automated,
                activity_started_at_time=activity_started_at_time,
                activity_ended_at_time=activity_ended_at_time,
                metadata={
                    "destination": destination,
                    "format": kwargs.get('format', 'unknown')
                }
            )
        
        return result
    
    def __getattr__(self, name):
        return getattr(self._exporter, name)


__all__ = ['ExporterWithProvenance']
