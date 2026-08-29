"""Regression tests for the MCP export_graph tool (issue: all branches broken).

The MCP server's export_graph tool failed on every format in 0.6.5/0.6.6:
  - json:   JSONExporter().export(graph) called without the required file_path
            argument -> TypeError, surfaced as {"error": ...}
  - RDF:    RDFExporter().export_to_rdf(graph, ...) received the ContextGraph
            object instead of the canonical kg dict -> AttributeError
  - all:    the RDF path printed a rich progress bar to stdout, corrupting the
            stdio JSON-RPC framing and hanging the client (observed: 300s
            timeout over MCP, <1s directly).

The fix: convert the graph with ContextGraph.to_kg_dict() before handing it to
the exporters, serialize json to a string, and force SEMANTICA_DISABLE_PROGRESS
for the server process (stdout is the protocol channel, not a console).
"""

import json
import os
import unittest

from semantica import mcp_server
from semantica.context import ContextGraph


def _graph_with_content() -> ContextGraph:
    graph = ContextGraph(advanced_analytics=True)
    graph.add_node("n1", node_type="entity", properties={"text": "hello"})
    graph.add_node("n2", node_type="entity", properties={"text": "world"})
    graph.add_edge("n1", "n2", "related_to")
    return graph


class TestExportGraphTool(unittest.TestCase):

    def setUp(self):
        self._old_graph = mcp_server._graph
        mcp_server._graph = _graph_with_content()

    def tearDown(self):
        mcp_server._graph = self._old_graph

    def test_json_branch_returns_string_data_not_error(self):
        result = mcp_server._tool_export_graph({"format": "json"})
        self.assertNotIn("error", result)
        self.assertEqual(result["format"], "json")
        payload = json.loads(result["data"])
        self.assertEqual(len(payload["entities"]), 2)
        self.assertEqual(len(payload["relationships"]), 1)

    def test_jsonld_branch_returns_string_data_not_error(self):
        result = mcp_server._tool_export_graph({"format": "json-ld"})
        self.assertNotIn("error", result)
        self.assertEqual(result["format"], "json-ld")
        self.assertIsInstance(result["data"], str)
        self.assertGreater(len(result["data"]), 0)

    def test_turtle_branch_returns_string_data_not_error(self):
        result = mcp_server._tool_export_graph({"format": "turtle"})
        self.assertNotIn("error", result)
        self.assertIsInstance(result["data"], str)
        self.assertIn("@prefix", result["data"])

    def test_all_rdf_formats_succeed(self):
        for fmt in ("turtle", "ttl", "nt", "xml", "json-ld"):
            with self.subTest(fmt=fmt):
                result = mcp_server._tool_export_graph({"format": fmt})
                self.assertNotIn("error", result, fmt)
                self.assertIsInstance(result["data"], str)

    def test_progress_is_disabled_for_the_server_process(self):
        self.assertEqual(os.environ.get("SEMANTICA_DISABLE_PROGRESS"), "1")

    def test_unsupported_format_returns_error_not_mislabeled_json(self):
        """A format outside the declared enum (typo, unsupported value, or a
        client that skips schema validation) must error, not silently return
        JSON data mislabeled with the requested format string."""
        result = mcp_server._tool_export_graph({"format": "yaml"})
        self.assertIn("error", result)
        self.assertIn("yaml", result["error"])

    def test_export_graph_schema_enum_matches_handled_formats(self):
        """The tool's declared inputSchema enum must not drift from the set
        of formats the handler actually accepts."""
        tool = next(t for t in mcp_server.TOOLS if t["name"] == "export_graph")
        schema_enum = set(tool["inputSchema"]["properties"]["format"]["enum"])
        self.assertEqual(schema_enum, set(mcp_server._EXPORT_GRAPH_FORMATS))


if __name__ == "__main__":
    unittest.main()
