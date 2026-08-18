"""
Shared pytest configuration for Agno integration tests.

When the real ``agno`` package (v2) is importable, tests run against it
directly — no stubs are installed.  Otherwise a comprehensive agno v2 stub is
installed into sys.modules before any test in this directory runs, so that
every test file can import the integration modules without a real agno
installation.
"""
from __future__ import annotations

import sys
import types


def _real_agno_available() -> bool:
    try:
        import agno  # noqa: F401
        from agno.db.base import BaseDb  # noqa: F401
        from agno.knowledge.knowledge import Knowledge  # noqa: F401
        from agno.tools.toolkit import Toolkit  # noqa: F401

        return True
    except ImportError:
        return False


def _install_agno_stubs() -> None:
    """Install a full set of agno v2 stubs into sys.modules."""

    agno = types.ModuleType("agno")

    # -----------------------------------------------------------------------
    # agno.db.base  — BaseDb
    # -----------------------------------------------------------------------
    db_pkg = types.ModuleType("agno.db")
    db_base = types.ModuleType("agno.db.base")

    class BaseDb:  # noqa: D101
        def __init__(self, *a, **kw): ...  # noqa: E704

    db_base.BaseDb = BaseDb  # type: ignore
    db_pkg.base = db_base

    # -----------------------------------------------------------------------
    # agno.db.schemas.memory  — UserMemory
    # -----------------------------------------------------------------------
    db_schemas = types.ModuleType("agno.db.schemas")
    db_schemas_memory = types.ModuleType("agno.db.schemas.memory")

    class UserMemory:  # noqa: D101
        def __init__(
            self,
            memory,
            memory_id=None,
            topics=None,
            user_id=None,
            input=None,
            created_at=None,
            updated_at=None,
            feedback=None,
            agent_id=None,
            team_id=None,
        ):
            self.memory = memory
            self.memory_id = memory_id
            self.topics = topics
            self.user_id = user_id
            self.input = input
            self.created_at = created_at
            self.updated_at = updated_at
            self.feedback = feedback
            self.agent_id = agent_id
            self.team_id = team_id

        def to_dict(self):
            return {
                k: v
                for k, v in {
                    "memory": self.memory,
                    "memory_id": self.memory_id,
                    "topics": self.topics,
                    "user_id": self.user_id,
                    "input": self.input,
                    "created_at": self.created_at,
                    "updated_at": self.updated_at,
                    "feedback": self.feedback,
                    "agent_id": self.agent_id,
                    "team_id": self.team_id,
                }.items()
                if v is not None
            }

        @classmethod
        def from_dict(cls, data):
            return cls(**data)

    db_schemas_memory.UserMemory = UserMemory  # type: ignore
    db_schemas.memory = db_schemas_memory
    db_pkg.schemas = db_schemas
    agno.db = db_pkg  # type: ignore

    # -----------------------------------------------------------------------
    # agno.tools.toolkit  — Toolkit
    # -----------------------------------------------------------------------
    tools_pkg = types.ModuleType("agno.tools")
    tools_toolkit_mod = types.ModuleType("agno.tools.toolkit")

    class Toolkit:  # noqa: D101
        def __init__(self, name: str = "toolkit", **kw):
            self.name = name
            self.functions: dict = {}

        def register(self, fn, name=None):  # noqa: D102
            self.functions[name or fn.__name__] = fn

    tools_toolkit_mod.Toolkit = Toolkit  # type: ignore
    tools_pkg.toolkit = tools_toolkit_mod
    agno.tools = tools_pkg  # type: ignore

    # -----------------------------------------------------------------------
    # agno.knowledge.knowledge  — Knowledge
    # -----------------------------------------------------------------------
    knowledge_pkg = types.ModuleType("agno.knowledge")
    knowledge_mod = types.ModuleType("agno.knowledge.knowledge")

    class Knowledge:  # noqa: D101
        def __init__(self, name=None, max_results=10, **kw):
            self.name = name
            self.max_results = max_results

        def search(self, query, max_results=None, filters=None, search_type=None):  # noqa: D102
            return []

    knowledge_mod.Knowledge = Knowledge  # type: ignore
    knowledge_pkg.knowledge = knowledge_mod

    # -----------------------------------------------------------------------
    # agno.knowledge.document.base  — Document
    # -----------------------------------------------------------------------
    document_pkg = types.ModuleType("agno.knowledge.document")
    document_base_mod = types.ModuleType("agno.knowledge.document.base")

    class Document:  # noqa: D101
        def __init__(self, content="", id=None, name=None, meta_data=None):
            self.content = content
            self.id = id
            self.name = name
            self.meta_data = meta_data or {}

    document_base_mod.Document = Document  # type: ignore
    document_pkg.base = document_base_mod
    knowledge_pkg.document = document_pkg
    agno.knowledge = knowledge_pkg  # type: ignore

    # -----------------------------------------------------------------------
    # Register everything
    # -----------------------------------------------------------------------
    _mods = {
        "agno": agno,
        "agno.db": db_pkg,
        "agno.db.base": db_base,
        "agno.db.schemas": db_schemas,
        "agno.db.schemas.memory": db_schemas_memory,
        "agno.tools": tools_pkg,
        "agno.tools.toolkit": tools_toolkit_mod,
        "agno.knowledge": knowledge_pkg,
        "agno.knowledge.knowledge": knowledge_mod,
        "agno.knowledge.document": document_pkg,
        "agno.knowledge.document.base": document_base_mod,
    }
    for name, mod in _mods.items():
        sys.modules[name] = mod


# Install stubs only when the real agno v2 package is not importable.
if not _real_agno_available():
    _install_agno_stubs()
