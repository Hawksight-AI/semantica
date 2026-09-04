"""
Regression tests for Issue #781 — Causal chain error signaling & fallback parameter forwarding
in semantica_mcp/mcp/tools/decisions.py: handle_get_causal_chain.
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import unittest
from unittest.mock import MagicMock, patch
from semantica_mcp.mcp.tools.decisions import handle_get_causal_chain


class TestMCPDecisionsCausalChain(unittest.TestCase):
    """Test suite covering handle_get_causal_chain execution paths and error shapes."""

    def test_validation_error_missing_decision_id(self):
        """Verify validation error shape when decision_id is missing or empty."""
        response = handle_get_causal_chain({})
        self.assertEqual(
            response,
            {"error": "decision_id is required", "chain": []},
        )
        self.assertNotIn("count", response)
        self.assertNotIn("direction", response)

        response_empty = handle_get_causal_chain({"decision_id": "   "})
        self.assertEqual(
            response_empty,
            {"error": "decision_id is required", "chain": []},
        )

    @patch("semantica_mcp.mcp.tools.decisions.get_graph")
    def test_runtime_outer_exception_shape(self, mock_get_graph):
        """Verify outer exception handler returns standard error shape without count/direction."""
        mock_get_graph.side_effect = RuntimeError("database failure")
        response = handle_get_causal_chain({"decision_id": "dec_101"})
        self.assertEqual(
            response,
            {"error": "database failure", "chain": []},
        )
        self.assertNotIn("count", response)
        self.assertNotIn("direction", response)

    @patch("semantica_mcp.mcp.tools.decisions.get_graph")
    @patch("semantica.context.causal_analyzer.CausalChainAnalyzer")
    def test_unsupported_backend_returns_error(self, mock_analyzer_cls, mock_get_graph):
        """
        Issue #781 regression test:
        Verify that when CausalChainAnalyzer fails to load and graph lacks get_causal_chain,
        an explicit error dictionary is returned rather than a silent empty list.
        """
        mock_analyzer_cls.side_effect = ImportError("mocked import error")
        # Graph object without get_causal_chain attribute
        mock_graph = object()
        mock_get_graph.return_value = mock_graph

        response = handle_get_causal_chain({"decision_id": "dec_202", "direction": "downstream"})
        self.assertEqual(
            response,
            {
                "error": "Causal chain analysis is not supported on this graph backend",
                "chain": [],
            },
        )
        self.assertNotIn("count", response)
        self.assertNotIn("direction", response)

    @patch("semantica_mcp.mcp.tools.decisions.get_graph")
    @patch("semantica.context.causal_analyzer.CausalChainAnalyzer")
    def test_fallback_path_forwards_direction_and_max_depth(self, mock_analyzer_cls, mock_get_graph):
        """Verify fallback graph.get_causal_chain receives direction and max_depth keyword arguments."""
        mock_analyzer_cls.side_effect = ImportError("mocked import error")
        mock_graph = MagicMock()
        mock_graph.get_causal_chain.return_value = ["node_a", "node_b"]
        mock_get_graph.return_value = mock_graph

        response = handle_get_causal_chain(
            {"decision_id": "dec_303", "direction": "upstream", "max_depth": 7}
        )
        mock_graph.get_causal_chain.assert_called_once_with(
            "dec_303",
            direction="upstream",
            max_depth=7,
        )
        self.assertNotIn("error", response)
        self.assertEqual(
            response,
            {"chain": ["node_a", "node_b"], "count": 2, "direction": "upstream"},
        )

    @patch("semantica_mcp.mcp.tools.decisions.get_graph")
    @patch("semantica.context.causal_analyzer.CausalChainAnalyzer")
    def test_fallback_success_response(self, mock_analyzer_cls, mock_get_graph):
        """Verify fallback graph.get_causal_chain default parameters and success response shape."""
        mock_analyzer_cls.side_effect = AttributeError("mocked attr error")
        mock_graph = MagicMock()
        mock_graph.get_causal_chain.return_value = ["node_default"]
        mock_get_graph.return_value = mock_graph

        response = handle_get_causal_chain({"decision_id": "dec_404"})
        mock_graph.get_causal_chain.assert_called_once_with(
            "dec_404",
            direction="downstream",
            max_depth=5,
        )
        self.assertNotIn("error", response)
        self.assertEqual(
            response,
            {"chain": ["node_default"], "count": 1, "direction": "downstream"},
        )

    @patch("semantica_mcp.mcp.tools.decisions.get_graph")
    @patch("semantica.context.causal_analyzer.CausalChainAnalyzer")
    def test_primary_analyzer_success_path(self, mock_analyzer_cls, mock_get_graph):
        """Verify normal operation via CausalChainAnalyzer when available."""
        mock_analyzer_instance = MagicMock()
        mock_analyzer_instance.get_causal_chain.return_value = ["dec_down_1", "dec_down_2"]
        mock_analyzer_cls.return_value = mock_analyzer_instance
        mock_graph = MagicMock()
        mock_get_graph.return_value = mock_graph

        response = handle_get_causal_chain(
            {"decision_id": "dec_505", "direction": "downstream", "max_depth": 4}
        )
        mock_analyzer_cls.assert_called_once_with(graph_store=mock_graph)
        mock_analyzer_instance.get_causal_chain.assert_called_once_with(
            "dec_505",
            direction="downstream",
            max_depth=4,
        )
        self.assertNotIn("error", response)
        self.assertEqual(
            response,
            {"chain": ["dec_down_1", "dec_down_2"], "count": 2, "direction": "downstream"},
        )

    @patch("semantica_mcp.mcp.tools.decisions.get_graph")
    @patch("semantica.context.causal_analyzer.CausalChainAnalyzer")
    def test_fallback_depth_kwarg_signature(self, mock_analyzer_cls, mock_get_graph):
        """Verify fallback works for backends accepting 'depth' kwarg (like OpenClaw)."""
        mock_analyzer_cls.side_effect = ImportError("mocked import error")

        class OpenClawGraphMock:
            def __init__(self):
                self.calls = []

            def get_causal_chain(self, node_id, depth=3):
                self.calls.append((node_id, depth))
                return ["openclaw_a", "openclaw_b"]

        graph_mock = OpenClawGraphMock()
        mock_get_graph.return_value = graph_mock

        response = handle_get_causal_chain(
            {"decision_id": "dec_606", "direction": "upstream", "max_depth": 4}
        )
        self.assertEqual(graph_mock.calls, [("dec_606", 4)])
        self.assertNotIn("error", response)
        self.assertEqual(
            response,
            {"chain": ["openclaw_a", "openclaw_b"], "count": 2, "direction": "upstream"},
        )

    @patch("semantica_mcp.mcp.tools.decisions.get_graph")
    @patch("semantica.context.causal_analyzer.CausalChainAnalyzer")
    def test_fallback_positional_only_signature(self, mock_analyzer_cls, mock_get_graph):
        """Verify fallback works for backends accepting only positional decision_id."""
        mock_analyzer_cls.side_effect = AttributeError("mocked attr error")

        class PositionalOnlyGraphMock:
            def __init__(self):
                self.calls = []

            def get_causal_chain(self, node_id):
                self.calls.append(node_id)
                return ["pos_node"]

        graph_mock = PositionalOnlyGraphMock()
        mock_get_graph.return_value = graph_mock

        response = handle_get_causal_chain({"decision_id": "dec_707"})
        self.assertEqual(graph_mock.calls, ["dec_707"])
        self.assertNotIn("error", response)
        self.assertEqual(
            response,
            {"chain": ["pos_node"], "count": 1, "direction": "downstream"},
        )

    @patch("semantica_mcp.mcp.tools.decisions.get_graph")
    @patch("semantica.context.causal_analyzer.CausalChainAnalyzer")
    def test_input_hardening_and_dos_prevention(
        self, mock_analyzer_cls, mock_get_graph
    ):
        """Verify non-dict args, non-string IDs, and max_depth bounds clamping."""
        self.assertEqual(
            handle_get_causal_chain(None),
            {"error": "args must be a dictionary", "chain": []},
        )
        mock_analyzer_instance = MagicMock()
        mock_analyzer_instance.get_causal_chain.return_value = ["n1"]
        mock_analyzer_cls.return_value = mock_analyzer_instance
        mock_get_graph.return_value = MagicMock()

        # Test integer decision_id and huge max_depth clamping (1000 -> 100)
        resp = handle_get_causal_chain(
            {"decision_id": 12345, "max_depth": 1000}
        )
        self.assertEqual(resp["chain"], ["n1"])
        mock_analyzer_instance.get_causal_chain.assert_called_once_with(
            "12345", direction="downstream", max_depth=100
        )

    @patch("semantica_mcp.mcp.tools.decisions.get_graph")
    @patch("semantica.context.causal_analyzer.CausalChainAnalyzer")
    def test_internal_typeerror_not_masked(self, mock_analyzer_cls, mock_get_graph):
        """Verify internal TypeError inside get_causal_chain is not masked as signature error."""
        mock_analyzer_cls.side_effect = ImportError("mocked import error")

        class BadInternalGraphMock:
            def get_causal_chain(self, node_id, direction="downstream", max_depth=5):
                raise TypeError("unsupported operand type(s) for +: 'int' and 'str'")

        mock_get_graph.return_value = BadInternalGraphMock()
        response = handle_get_causal_chain({"decision_id": "dec_err"})
        self.assertEqual(
            response,
            {
                "error": "unsupported operand type(s) for +: 'int' and 'str'",
                "chain": [],
            },
        )

    @patch("semantica_mcp.mcp.tools.decisions.get_graph")
    @patch("semantica.context.causal_analyzer.CausalChainAnalyzer")
    def test_internal_typeerror_calls_backend_only_once(self, mock_analyzer_cls, mock_get_graph):
        """
        Regression test: a signature that introspects successfully must be called
        exactly once, even if the call itself raises TypeError for reasons unrelated
        to the signature (e.g. a bug inside the backend). Previously this TypeError
        was caught by the same except block used for introspection failures, causing
        an identical retry call before the error was correctly surfaced.
        """
        mock_analyzer_cls.side_effect = ImportError("mocked import error")

        class BadInternalGraphMock:
            def __init__(self):
                self.call_count = 0

            def get_causal_chain(self, node_id, direction="downstream", max_depth=5):
                self.call_count += 1
                raise TypeError("unsupported operand type(s) for +: 'int' and 'str'")

        graph_mock = BadInternalGraphMock()
        mock_get_graph.return_value = graph_mock
        response = handle_get_causal_chain({"decision_id": "dec_err"})
        self.assertEqual(
            response,
            {
                "error": "unsupported operand type(s) for +: 'int' and 'str'",
                "chain": [],
            },
        )
        self.assertEqual(graph_mock.call_count, 1)


if __name__ == "__main__":
    unittest.main()
