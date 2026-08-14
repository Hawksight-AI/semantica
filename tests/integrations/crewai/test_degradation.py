"""
Graceful-degradation tests for the CrewAI integration.

These run the integration modules in a fresh subprocess (no conftest crewai
stubs, no real crewai) to prove that every public class remains importable and
functional when ``crewai`` is absent.  A subprocess is used because the other
test files in this directory install crewai stubs into ``sys.modules`` for the
whole pytest session; a subprocess keeps the two scenarios isolated.
"""

from __future__ import annotations

import os
import subprocess
import sys
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

_SCRIPT = r"""
import json
import sys

try:
    import crewai  # noqa: F401
    real_crewai = True
except ImportError:
    real_crewai = False

from integrations.crewai import (
    CREWAI_AVAILABLE,
    SemanticaKGTool,
    SemanticaDecisionTool,
    SemanticaKnowledgeSource,
)
from semantica.context import ContextGraph

assert CREWAI_AVAILABLE == real_crewai, (
    f"CREWAI_AVAILABLE={CREWAI_AVAILABLE} but real crewai={real_crewai}"
)

# --- SemanticaKGTool: importable + functional without crewai -----------------
graph = ContextGraph()
graph.add_node(node_id="privacy", node_type="policy", content="privacy policy doc")

tool = SemanticaKGTool(graph=graph)
assert tool.name == "semantica_knowledge_graph"
assert tool.args_schema is not None

res = json.loads(tool._run(action="query_graph", query="privacy"))
assert res["count"] == 1, res
res = json.loads(tool._run(action="find_related", entity="ghost", hops=1))
assert res["count"] == 0, res

# The public run()/arun() entry points must exist without crewai too.
res = json.loads(tool.run(action="query_graph", query="privacy"))
assert res["count"] == 1, res
import asyncio
res = json.loads(asyncio.run(tool.arun(action="query_graph", query="privacy")))
assert res["count"] == 1, res

# --- SemanticaKnowledgeSource: importable + functional without crewai --------
src = SemanticaKnowledgeSource(graph=graph, chunk_size=40, chunk_overlap=5)
assert src.load_content() != {}
assert src.validate_content() is True
src.add()  # must not raise; chunks kept in memory
assert len(src.chunks) > 0

# --- SemanticaDecisionTool: importable, builds its own context --------------
dt = SemanticaDecisionTool()
assert dt.name == "semantica_decision"
res = json.loads(dt.run(action="find_precedents", scenario="x"))
assert "precedents" in res, res
res = json.loads(asyncio.run(dt.arun(action="find_precedents", scenario="x")))
assert "precedents" in res, res

print("DEGRADATION_OK")
"""


class TestDegradation(unittest.TestCase):

    def test_importable_and_functional_without_crewai(self):
        result = subprocess.run(
            [sys.executable, "-c", _SCRIPT],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=180,
        )
        self.assertEqual(
            result.returncode,
            0,
            msg=(
                f"subprocess failed:\nSTDOUT:\n{result.stdout}\n"
                f"STDERR:\n{result.stderr}"
            ),
        )
        self.assertIn("DEGRADATION_OK", result.stdout)


if __name__ == "__main__":
    unittest.main()
