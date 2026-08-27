"""Regression tests for the standalone mcp/ package export_graph tool.

The mcp/ server (python -m mcp / python -m mcp.server) had two failures on
every RDF export format:

  1. AttributeError: 'ContextGraph' object has no attribute 'get'
     handle_export_graph() in mcp/tools/export.py called
     RDFExporter().export_to_rdf(graph, ...) passing the raw ContextGraph
     object instead of the canonical kg dict expected by the exporter.

  2. stdout progress corruption
     RDFExporter.__init__ instantiated the Semantica progress-tracker
     singleton, which wrote a progress bar to sys.stdout before the
     AttributeError was raised.  stdout is the MCP stdio JSON-RPC transport,
     so this interleaved non-JSON bytes corrupted framing for every client.

Fixes applied:
  - mcp/tools/export.py: convert with graph.to_kg_dict() before export_to_rdf()
  - mcp/__init__.py: os.environ["SEMANTICA_DISABLE_PROGRESS"] = "1" at
    package initialisation, before any tool handler can instantiate
    RDFExporter and therefore before the tracker singleton is created.
"""

from __future__ import annotations

import io
import os
import sys
import subprocess
import unittest

import semantica.utils.progress_tracker as _progress_module


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_graph():
    """Return a ContextGraph with two entities and one relationship."""
    from semantica.context.context_graph import ContextGraph
    g = ContextGraph()
    g.add_node("n1", node_type="entity")
    g.add_node("n2", node_type="entity")
    g.add_edge("n1", "n2", "related_to")
    return g


def _reset_progress_singleton():
    """Destroy any cached progress-tracker singleton so the next call
    to get_progress_tracker() reads the current environment variable."""
    _progress_module.ProgressTracker._instance = None
    _progress_module._global_tracker = None


# ---------------------------------------------------------------------------
# RDF export correctness
# ---------------------------------------------------------------------------

class TestMCPPackageExportGraphRDF(unittest.TestCase):
    """handle_export_graph() must return a non-empty RDF string for every
    supported RDF format, not an error dict."""

    def setUp(self):
        # Inject a known graph into the mcp/ session so handlers don't try to
        # build a full ContextGraph (which requires heavy ML dependencies).
        import mcp.session as _session
        self._orig_graph = _session._graph
        _session._graph = _make_graph()

    def tearDown(self):
        import mcp.session as _session
        _session._graph = self._orig_graph

    def test_turtle_returns_non_empty_string(self):
        from mcp.tools.export import handle_export_graph
        result = handle_export_graph({"format": "turtle"})
        self.assertNotIn("error", result, result)
        self.assertIsInstance(result["data"], str)
        self.assertGreater(len(result["data"]), 0)
        # Turtle output must carry prefix declarations
        self.assertIn("@prefix", result["data"])

    def test_ttl_alias_returns_non_empty_string(self):
        from mcp.tools.export import handle_export_graph
        result = handle_export_graph({"format": "ttl"})
        self.assertNotIn("error", result, result)
        self.assertIsInstance(result["data"], str)
        self.assertGreater(len(result["data"]), 0)

    def test_nt_returns_non_empty_string(self):
        from mcp.tools.export import handle_export_graph
        result = handle_export_graph({"format": "nt"})
        self.assertNotIn("error", result, result)
        self.assertIsInstance(result["data"], str)
        self.assertGreater(len(result["data"]), 0)

    def test_xml_returns_non_empty_string(self):
        from mcp.tools.export import handle_export_graph
        result = handle_export_graph({"format": "xml"})
        self.assertNotIn("error", result, result)
        self.assertIsInstance(result["data"], str)
        self.assertGreater(len(result["data"]), 0)

    def test_jsonld_returns_non_empty_string(self):
        from mcp.tools.export import handle_export_graph
        result = handle_export_graph({"format": "json-ld"})
        self.assertNotIn("error", result, result)
        self.assertIsInstance(result["data"], str)
        self.assertGreater(len(result["data"]), 0)

    def test_all_rdf_formats_succeed(self):
        from mcp.tools.export import handle_export_graph
        for fmt in ("turtle", "ttl", "nt", "xml", "json-ld"):
            with self.subTest(fmt=fmt):
                result = handle_export_graph({"format": fmt})
                self.assertNotIn("error", result, f"format={fmt}: {result}")
                self.assertIsInstance(result["data"], str)
                self.assertGreater(len(result["data"]), 0)

    def test_rdf_branch_does_not_raise_context_graph_attribute_error(self):
        """The pre-fix code passed ContextGraph directly to export_to_rdf(),
        causing AttributeError: 'ContextGraph' object has no attribute 'get'.
        Verify that error does not appear in the result."""
        from mcp.tools.export import handle_export_graph
        result = handle_export_graph({"format": "turtle"})
        if "error" in result:
            self.assertNotIn("'ContextGraph' object has no attribute 'get'",
                             result["error"])


# ---------------------------------------------------------------------------
# stdout protection — subprocess-based to avoid process-state cross-contamination
# ---------------------------------------------------------------------------

class TestMCPPackageStdoutProtection(unittest.TestCase):
    """The standalone mcp/ server must not write any progress bytes to stdout.
    stdout is the MCP JSON-RPC transport channel.

    These tests use a subprocess to get a clean process state where
    SEMANTICA_DISABLE_PROGRESS has not yet been set, so we can verify that
    importing mcp and running an export produces no progress bytes on stdout.
    """

    def _run_in_subprocess(self, code: str, timeout: int = 30) -> subprocess.CompletedProcess:
        """Run a Python snippet in a clean subprocess with the repo on sys.path."""
        repo_root = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..")
        )
        env = os.environ.copy()
        env["PYTHONPATH"] = repo_root
        # Start with a clean slate — no pre-set disable flag
        env.pop("SEMANTICA_DISABLE_PROGRESS", None)
        return subprocess.run(
            [sys.executable, "-c", code],
            cwd=repo_root,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
        )

    def test_importing_mcp_sets_disable_progress(self):
        """Importing the mcp package must set SEMANTICA_DISABLE_PROGRESS=1
        before any tool handler runs."""
        code = (
            "import os; "
            "import mcp; "  # triggers mcp/__init__.py
            "print(os.environ.get('SEMANTICA_DISABLE_PROGRESS', 'NOT SET'))"
        )
        result = self._run_in_subprocess(code)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("1", result.stdout)

    def test_rdf_export_writes_no_progress_to_stdout(self):
        """An RDF export via handle_export_graph() must not write any Semantica
        progress bytes to stdout.  The only stdout bytes should be the explicit
        print() call at the end of the snippet."""
        code = """
import os, sys
# Ensure clean state
os.environ.pop("SEMANTICA_DISABLE_PROGRESS", None)

import mcp  # sets SEMANTICA_DISABLE_PROGRESS=1
import mcp.session as session
from semantica.context.context_graph import ContextGraph

g = ContextGraph()
g.add_node("n1", node_type="entity")
g.add_node("n2", node_type="entity")
g.add_edge("n1", "n2", "related_to")
session._graph = g

# Intercept stdout writes to detect any progress output
written = []
_orig = sys.stdout.write
def _capture(s):
    written.append(s)
    return _orig(s)
sys.stdout.write = _capture

from mcp.tools.export import handle_export_graph
result = handle_export_graph({"format": "turtle"})

sys.stdout.write = _orig

# Only our explicit output below should be in written
# (the sentinel line is added after restoring stdout)
progress_writes = [s for s in written]
print("RESULT_OK:" + str("error" not in result))
print("STDOUT_WRITES:" + str(len(progress_writes)))
"""
        proc = self._run_in_subprocess(code)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        # Extract the printed lines
        lines = proc.stdout.strip().splitlines()
        result_ok_line = next((l for l in lines if l.startswith("RESULT_OK:")), None)
        writes_line = next((l for l in lines if l.startswith("STDOUT_WRITES:")), None)
        self.assertIsNotNone(result_ok_line, f"stdout: {proc.stdout!r}")
        self.assertIsNotNone(writes_line, f"stdout: {proc.stdout!r}")
        self.assertEqual(result_ok_line, "RESULT_OK:True",
                         f"export returned error; stdout={proc.stdout!r}, stderr={proc.stderr!r}")
        n_writes = int(writes_line.split(":")[1])
        self.assertEqual(n_writes, 0,
                         f"Expected 0 progress writes to stdout, got {n_writes}; "
                         f"stdout={proc.stdout!r}")


if __name__ == "__main__":
    unittest.main()
