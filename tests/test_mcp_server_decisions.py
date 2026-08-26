"""Regression tests for MCP decision queries."""

import unittest

from semantica import mcp_server
from semantica.context import ContextGraph


class TestQueryDecisionsTool(unittest.TestCase):
    def setUp(self):
        self._old_graph = mcp_server._graph
        mcp_server._graph = ContextGraph(advanced_analytics=True)

    def tearDown(self):
        mcp_server._graph = self._old_graph

    def test_category_filter_returns_decision_recorded_in_same_session(self):
        """Decision categories are exposed by find_nodes inside metadata."""
        recorded = mcp_server._tool_record_decision(
            {
                "category": "architecture",
                "scenario": "Choose the decision-log persistence layer",
                "reasoning": "Postgres provides durable transactional storage.",
                "outcome": "postgres",
                "confidence": 0.9,
            }
        )

        result = mcp_server._tool_query_decisions({"category": "architecture"})

        self.assertNotIn("error", result)
        self.assertEqual(len(result["decisions"]), 1)
        self.assertEqual(result["decisions"][0]["id"], recorded["decision_id"])
        self.assertEqual(result["decisions"][0]["metadata"]["category"], "architecture")


if __name__ == "__main__":
    unittest.main()
