"""
Shared Agno availability probe.

Every integration module needs to know whether the real ``agno`` package
(version 2.x) is installed.  Probing once here (instead of once per module)
guarantees the exported ``AGNO_AVAILABLE`` flag means the *whole* integration
is ready — a caller gating on it will never see a store using the v2 ``BaseDb``
API while a toolkit silently degrades (or vice versa).

Only ``agno >= 2.9`` is supported.  When agno v1 is installed the v2 import
paths below fail and the integration degrades gracefully (importable, but not
attachable to Agno ``Agent`` / ``Team`` constructors).
"""

from typing import Optional

AGNO_AVAILABLE = False
AGNO_IMPORT_ERROR: Optional[str] = None

try:
    from agno.db.base import BaseDb  # noqa: F401
    from agno.db.schemas.memory import UserMemory  # noqa: F401
    from agno.knowledge.document.base import Document  # noqa: F401
    from agno.knowledge.knowledge import Knowledge  # noqa: F401
    from agno.tools.toolkit import Toolkit  # noqa: F401

    AGNO_AVAILABLE = True
except ImportError as exc:
    AGNO_IMPORT_ERROR = str(exc)
