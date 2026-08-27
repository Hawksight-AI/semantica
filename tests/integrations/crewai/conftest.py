"""
Shared pytest configuration for CrewAI integration tests.

Installs comprehensive crewai stubs into sys.modules before any test in this
directory runs, so every test file can import the integration modules with
``CREWAI_AVAILABLE == True`` and exercise the real subclassing code paths
without a real crewai installation.

The stubs mirror the current CrewAI contracts:
- ``crewai.tools.BaseTool``  — Pydantic ``BaseModel`` (arbitrary types allowed)
- ``crewai.knowledge.source.base_knowledge_source.BaseKnowledgeSource`` —
  Pydantic model with ``validate_content``/``add``/``aadd`` abstract methods
  and ``_chunk_text``/``_save_documents`` helpers.

The graceful-degradation path (crewai genuinely absent) is covered separately
in ``test_degradation.py`` via a subprocess, so this stub never has to be torn
down mid-session.
"""

from __future__ import annotations

import sys
import types
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator


def _install_crewai_stubs() -> None:
    """Install a full set of crewai stubs into sys.modules."""

    # -----------------------------------------------------------------------
    # crewai.tools  — BaseTool
    # -----------------------------------------------------------------------
    class BaseTool(BaseModel):  # noqa: D101
        """Stub mirroring crewai.tools.base_tool.BaseTool."""

        model_config = ConfigDict(arbitrary_types_allowed=True)

        name: str = "base_tool"
        description: str = ""
        args_schema: Any = None
        result_as_answer: bool = False

        @field_serializer("args_schema", when_used="json")
        def _ser_args_schema(self, schema):  # noqa: D102
            if schema is None:
                return None
            return {"__schema__": f"{schema.__module__}.{schema.__qualname__}"}

        @field_validator("args_schema", mode="before")
        @classmethod
        def _restore_args_schema(cls, v):  # noqa: D102
            if isinstance(v, dict) and "__schema__" in v:
                import importlib

                mod_name, cls_name = v["__schema__"].rsplit(".", 1)
                return getattr(importlib.import_module(mod_name), cls_name)
            return v

        def run(self, *args: Any, **kwargs: Any) -> str:  # noqa: D102
            return self._run(*args, **kwargs)

        async def arun(self, *args: Any, **kwargs: Any) -> str:  # noqa: D102
            return await self._arun(*args, **kwargs)

        def _run(self, *args: Any, **kwargs: Any) -> str:  # noqa: D102
            raise NotImplementedError

        async def _arun(self, *args: Any, **kwargs: Any) -> str:  # noqa: D102
            raise NotImplementedError

    tools_mod = types.ModuleType("crewai.tools")
    tools_mod.BaseTool = BaseTool  # type: ignore[attr-defined]

    tools_base_mod = types.ModuleType("crewai.tools.base_tool")
    tools_base_mod.BaseTool = BaseTool  # type: ignore[attr-defined]

    # -----------------------------------------------------------------------
    # crewai.knowledge.source.base_knowledge_source — BaseKnowledgeSource
    # -----------------------------------------------------------------------
    class BaseKnowledgeSource(BaseModel):  # noqa: D101
        """Stub mirroring crewai.knowledge.source.base_knowledge_source."""

        model_config = ConfigDict(arbitrary_types_allowed=True)

        chunk_size: int = 4000
        chunk_overlap: int = 200
        chunks: list = Field(default_factory=list)
        chunk_embeddings: list = Field(default_factory=list, exclude=True)
        storage: Any = None
        metadata: dict = Field(default_factory=dict)
        collection_name: Optional[str] = None

        def _chunk_text(self, text: str) -> list:  # noqa: D102
            return [
                text[i : i + self.chunk_size]
                for i in range(0, len(text), self.chunk_size - self.chunk_overlap)
            ]

        def _save_documents(self) -> None:  # noqa: D102
            if self.storage is not None:
                self.storage.save(self.chunks)
            else:
                raise ValueError("No storage found to save documents.")

        async def _asave_documents(self) -> None:  # noqa: D102
            if self.storage is not None:
                await self.storage.asave(self.chunks)
            else:
                raise ValueError("No storage found to save documents.")

        def validate_content(self) -> Any:  # noqa: D102
            raise NotImplementedError

        def add(self) -> None:  # noqa: D102
            raise NotImplementedError

        async def aadd(self) -> None:  # noqa: D102
            raise NotImplementedError

    knowledge_pkg = types.ModuleType("crewai.knowledge")
    source_pkg = types.ModuleType("crewai.knowledge.source")
    source_base_mod = types.ModuleType("crewai.knowledge.source.base_knowledge_source")
    source_base_mod.BaseKnowledgeSource = (  # type: ignore[attr-defined]
        BaseKnowledgeSource
    )
    source_pkg.BaseKnowledgeSource = BaseKnowledgeSource  # type: ignore[attr-defined]
    knowledge_pkg.source = source_pkg

    # -----------------------------------------------------------------------
    # Register everything
    # -----------------------------------------------------------------------
    crewai = types.ModuleType("crewai")
    crewai.tools = tools_mod  # type: ignore[attr-defined]
    crewai.knowledge = knowledge_pkg  # type: ignore[attr-defined]

    _mods = {
        "crewai": crewai,
        "crewai.tools": tools_mod,
        "crewai.tools.base_tool": tools_base_mod,
        "crewai.knowledge": knowledge_pkg,
        "crewai.knowledge.source": source_pkg,
        "crewai.knowledge.source.base_knowledge_source": source_base_mod,
    }
    for name, mod in _mods.items():
        sys.modules[name] = mod


# Install once at import time (conftest is imported before any test file)
_install_crewai_stubs()
