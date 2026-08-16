"""
End-to-end integration tests against the REAL crewai package.

These run in a subprocess because the stubs in ``conftest.py`` install a fake
``crewai`` module into ``sys.modules`` for the whole pytest session — the same
interpreter can never see both.  Each test launches a fresh interpreter; if
crewai is genuinely not installed there, the test is skipped.

This covers the failure class the stubs cannot: ``Crew``-level serialization
(list[BaseTool] inside Agent.tools), checkpoint restore via ``model_validate``,
and knowledge-source behaviour with a real ``Crew``.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]

_SCRIPT = textwrap.dedent(
    """
    import os
    import json
    import sys

    sys.path.insert(0, os.getcwd())

    try:
        import crewai
    except ImportError:
        print("CREWAI_IMPORT_FAILED")
        sys.exit(2)

    import crewai as crewai_mod
    from crewai import Agent, Task, Crew

    from semantica.context import ContextGraph
    from integrations.crewai import (
        SemanticaKGTool,
        SemanticaDecisionTool,
        SemanticaKnowledgeSource,
    )

    os.environ["CREWAI_DESERIALIZE_CALLBACKS"] = "1"

    # --- 1. Crew-level serialization round-trip ------------------------------
    graph = ContextGraph()
    graph.add_node(node_id="privacy", node_type="policy",
                   content="privacy policy: no data sharing")
    tool = SemanticaKGTool(graph=graph)

    decision_ctx = SemanticaDecisionTool()
    decision_tool = SemanticaDecisionTool(context=decision_ctx.context)

    agent = Agent(role="researcher", goal="answer questions",
                  backstory="retrieves from a knowledge graph",
                  tools=[tool, decision_tool])
    task = Task(description="answer", expected_output="an answer", agent=agent)
    crew = Crew(agents=[agent], tasks=[task])

    dump = crew.model_dump(mode="json")
    agents = dump["agents"]
    assert len(agents) == 1, f"expected 1 agent, got {len(agents)}"
    dumped_tools = agents[0]["tools"]
    assert len(dumped_tools) == 2, f"expected 2 tools, got {len(dumped_tools)}"
    for t in dumped_tools:
        assert isinstance(t, dict), f"tool not serialized to dict: {type(t)}"
        assert "graph" not in t, "live graph leaked into serialized tool"
        assert "context" not in t, "live context leaked into serialized tool"
        assert "ner_extractor" not in t, "extractor leaked into serialized tool"

    # --- 2. Restore a tool from the crew dump --------------------------------
    kg_dump = dumped_tools[0]
    assert kg_dump["name"] == "semantica_knowledge_graph", kg_dump["name"]
    restored = SemanticaKGTool.model_validate(kg_dump)
    assert restored.graph is not None, "restored tool did not self-heal a graph"
    q = json.loads(restored._run(action="query_graph", query="privacy"))
    assert "results" in q, f"restored tool query_graph failed: {q}"

    # --- 3. Knowledge source with no embedder must not crash a Crew ----------
    ks = SemanticaKnowledgeSource(graph=graph)
    agent2 = Agent(role="researcher2", goal="answer",
                   backstory="retrieves from knowledge")
    task2 = Task(description="q", expected_output="a", agent=agent2)
    crew2 = Crew(agents=[agent2], tasks=[task2],
                 knowledge_sources=[ks])
    assert ks.chunks, "knowledge source retained no chunks in memory"
    assert crew2.knowledge is not None, "crew.knowledge not created"

    print("REAL_CREWAI_OK")
    """
)


class TestRealCrewAIIntegration(unittest.TestCase):

    def _run(self) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, "-c", _SCRIPT],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=240,
        )

    def test_crew_level_round_trip_with_real_crewai(self):
        proc = self._run()
        if proc.returncode == 2:
            self.skipTest("real crewai is not installed in this environment")
        self.assertEqual(
            proc.returncode,
            0,
            msg=f"subprocess failed:\n{proc.stdout}\n{proc.stderr}",
        )
        self.assertIn("REAL_CREWAI_OK", proc.stdout)


if __name__ == "__main__":
    unittest.main()
