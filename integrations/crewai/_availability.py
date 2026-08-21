"""
Shared CrewAI availability probe.

Every integration module needs to know whether the real ``crewai`` package is
installed.  Probing once here (instead of once per module) guarantees the
exported ``CREWAI_AVAILABLE`` flag means the *whole* integration is ready — a
caller gating on it will never see tools using CrewAI while a knowledge source
silently degrades (or vice versa).
"""

from typing import Optional

CREWAI_AVAILABLE = False
CREWAI_IMPORT_ERROR: Optional[str] = None

try:
    from crewai.knowledge.source.base_knowledge_source import (  # noqa: F401
        BaseKnowledgeSource,
    )
    from crewai.tools import BaseTool  # noqa: F401

    CREWAI_AVAILABLE = True
except ImportError as exc:
    CREWAI_IMPORT_ERROR = str(exc)
