"""Tests for the public in-process tool entry point (issue #1355).

``semantica.mcp_server.call_tool`` is the shared dispatch used by both the
JSON-RPC ``tools/call`` handler and the ``semantica mcp call`` CLI command,
replacing the CLI's former import of the unpackaged ``mcp.session`` module.
"""

import unittest
from unittest.mock import patch

from semantica import mcp_server
from semantica.mcp_server import TOOLS, UnknownToolError, call_tool


class TestCallTool(unittest.TestCase):

    def test_known_tool_dispatches_to_handler(self):
        """A catalog tool is invoked in-process with the arguments dict.

        Empty args hit extract_entities' own validation before any heavy
        imports, which is enough to prove dispatch reached the handler.
        """
        result = call_tool("extract_entities", {})
        self.assertEqual(result, {"error": "text is required"})

    def test_unknown_tool_raises_unknown_tool_error(self):
        with self.assertRaises(UnknownToolError):
            call_tool("no_such_tool", {})

    def test_unknown_tool_error_is_not_a_key_error(self):
        """A handler's own KeyError (missing required arg) must remain
        distinguishable from an unknown tool name."""
        self.assertFalse(issubclass(UnknownToolError, KeyError))


class TestToolsCallDispatch(unittest.TestCase):

    @staticmethod
    def _tools_call(name, arguments):
        return mcp_server._handle(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": name, "arguments": arguments},
            }
        )

    def test_unknown_tool_returns_method_not_found(self):
        response = self._tools_call("no_such_tool", {})
        self.assertEqual(response["error"]["code"], -32601)

    def test_handler_key_error_is_internal_error_not_unknown_tool(self):
        def _boom(args):
            raise KeyError("category")

        fake = {"name": "boom", "description": "", "inputSchema": {}, "_handler": _boom}
        with patch.object(mcp_server, "TOOLS", TOOLS + [fake]):
            response = self._tools_call("boom", {})
        self.assertEqual(response["error"]["code"], -32603)

    def test_known_tool_returns_result_content(self):
        response = self._tools_call("extract_entities", {})
        self.assertIn("content", response["result"])


if __name__ == "__main__":
    unittest.main()
