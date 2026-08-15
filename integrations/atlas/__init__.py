"""Atlas → Semantica integration (atlas #618).

Indexes an Atlas workspace's artifact spine (specs · sections · ACs · issues · runs · PRs · tests ·
decisions, and — when present — assumptions · change-events) into a Semantica graph, per-workspace
(multi-tenant: one namespace / named graph per ``workspace_id``), and answers impact / coverage /
risk / assumption-provenance questions over it.
"""

from .atlas_adapter import AtlasSemanticaAdapter, WorkspaceGraph

__all__ = ["AtlasSemanticaAdapter", "WorkspaceGraph"]
