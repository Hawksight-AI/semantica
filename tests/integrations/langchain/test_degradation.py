"""
Graceful-degradation tests for the LangChain integration.

Runs the adapters in a fresh subprocess with langchain-core hidden, so the
object-base path is proven even when this env has langchain-core installed.
"""

from __future__ import annotations

import os
import subprocess
import sys
from types import SimpleNamespace

import pytest

from integrations.langchain import (
    LANGCHAIN_AVAILABLE,
    SemanticaDecisionTool,
    SemanticaKGTool,
)

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

_SCRIPT = r"""
import sys
from types import SimpleNamespace

class _BlockLangchain:
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "langchain_core" or fullname.startswith("langchain_core."):
            raise ImportError("langchain_core blocked for degradation test")
        return None

sys.meta_path.insert(0, _BlockLangchain())
for name in list(sys.modules):
    if name == "langchain_core" or name.startswith("langchain_core."):
        del sys.modules[name]

from integrations.langchain.retriever import LANGCHAIN_AVAILABLE as RET_AVAIL
from integrations.langchain.vectorstore import (
    LANGCHAIN_AVAILABLE as VS_AVAIL,
    SemanticaVectorStore,
)
from integrations.langchain.tools import (
    LANGCHAIN_AVAILABLE as TOOL_AVAIL,
    SemanticaKGTool,
    SemanticaDecisionTool,
)
from integrations.langchain.retriever import SemanticaRetriever, _get_document

assert RET_AVAIL is False and VS_AVAIL is False and TOOL_AVAIL is False

retriever = SemanticaRetriever(graph=SimpleNamespace(), hops=2)
assert retriever.hops == 2

store = SemanticaVectorStore(hybrid=SimpleNamespace(), tags=["x"])
assert store.hybrid is not None

graph = SimpleNamespace(query=lambda q, limit=10: [{"q": q, "limit": limit}])
assert SemanticaKGTool(graph).build() is None
assert SemanticaDecisionTool(graph).build() is None

try:
    _get_document(page_content="x")
    raise SystemExit("expected RuntimeError from _get_document")
except RuntimeError as exc:
    assert "langchain-core" in str(exc)

print("DEGRADATION_OK")
"""


def test_importable_and_functional_without_langchain():
    result = subprocess.run(
        [sys.executable, "-c", _SCRIPT],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, (
        f"subprocess failed:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    )
    assert "DEGRADATION_OK" in result.stdout


@pytest.mark.skipif(LANGCHAIN_AVAILABLE, reason="langchain-core is installed")
def test_tools_build_returns_none_without_langchain():
    graph = SimpleNamespace()
    assert SemanticaKGTool(graph).build() is None
    assert SemanticaDecisionTool(graph).build() is None
