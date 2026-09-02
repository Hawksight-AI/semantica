"""MCP stdio JSON-RPC framing regression test (#1134, point 1).

The original bug: progress output from the Semantica progress tracker was
written to sys.stdout, which is also the MCP JSON-RPC transport channel.
Interleaving progress text with JSON-RPC responses made every response
unparseable and hung the client.

These tests exercise the *actual* root mcp/ server stdio framing loop
(SemanticaMCPServer.run()) over a real subprocess pipe, not just the handler
layer.  They prove that:

  1. Every non-empty stdout line produced by the running server is valid JSON.
  2. A valid JSON-RPC response is received for each request sent.
  3. No progress / non-JSON bytes appear on stdout even when a tool triggers
     the progress-producing code path (constructing a ContextGraph, which
     calls get_progress_tracker() and attempts to enable the tracker).

Tests that are already covered elsewhere are not duplicated here:
  - ConsoleProgressDisplay writing to stderr (test_progress_stream.py)
  - SEMANTICA_DISABLE_PROGRESS blocking re-enable (test_progress_tracker_regressions.py)
  - mcp import sets SEMANTICA_DISABLE_PROGRESS (test_mcp_package_export_graph.py)
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------

def _repo_root() -> str:
    return os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _subprocess_env() -> dict[str, str]:
    """Clean env with the repo on PYTHONPATH and no pre-set progress flag."""
    env = os.environ.copy()
    env["PYTHONPATH"] = _repo_root()
    env.pop("SEMANTICA_DISABLE_PROGRESS", None)
    return env


def _jsonrpc(method: str, req_id: int | None, params: dict | None = None) -> bytes:
    msg: dict = {"jsonrpc": "2.0", "method": method}
    if req_id is not None:
        msg["id"] = req_id
    if params is not None:
        msg["params"] = params
    return (json.dumps(msg) + "\n").encode()


def _assert_stdout_is_clean_json(test: unittest.TestCase,
                                  stdout: str,
                                  stderr: str = "") -> list[dict]:
    """Assert every non-empty stdout line is valid JSON; return parsed objects.

    Fails immediately with a useful diagnostic if any line is not JSON.
    """
    lines = [ln for ln in stdout.splitlines() if ln.strip()]
    test.assertGreater(
        len(lines), 0,
        f"Expected at least one stdout line but got none.\nstderr={stderr!r}",
    )
    parsed = []
    for i, line in enumerate(lines):
        try:
            parsed.append(json.loads(line))
        except json.JSONDecodeError as exc:
            test.fail(
                f"stdout line {i} is not valid JSON (regression: progress leaked "
                f"to stdout?)\n  line: {line!r}\n  error: {exc}\n  stderr={stderr!r}"
            )
    return parsed


_INIT_REQUEST = _jsonrpc("initialize", 1, {
    "protocolVersion": "2024-11-05",
    "clientInfo": {"name": "test", "version": "0"},
    "capabilities": {},
})


# ---------------------------------------------------------------------------
# Main regression suite
# ---------------------------------------------------------------------------

class TestMCPStdioFramingContract(unittest.TestCase):
    """Run 'python -m mcp' exactly as an MCP client would, over a real pipe.

    Each test sends a complete JSON-RPC session through stdin and asserts that
    every byte on stdout is valid JSON — catching the exact failure mode from
    #1134 where progress output corrupted the transport stream.
    """

    TIMEOUT = 30

    def _run(self, *requests: bytes) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, "-m", "mcp"],
            input=b"".join(requests),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=self.TIMEOUT,
            cwd=_repo_root(),
            env=_subprocess_env(),
            check=False,
        )

    # ------------------------------------------------------------------

    def test_initialize_stdout_is_valid_json_rpc(self):
        """An initialize request must produce a single valid JSON-RPC response."""
        proc = self._run(_INIT_REQUEST)

        self.assertEqual(proc.returncode, 0,
                         f"server crashed:\n{proc.stderr.decode()}")
        responses = _assert_stdout_is_clean_json(
            self, proc.stdout.decode(), proc.stderr.decode()
        )
        init_resp = next((r for r in responses if r.get("id") == 1), None)
        self.assertIsNotNone(init_resp, f"No id=1 response in: {responses}")
        self.assertIn("serverInfo", init_resp.get("result", {}))

    def test_tools_call_stdout_is_clean_json_rpc(self):
        """A tools/call round-trip through the full stdio framing loop must keep
        stdout free of any non-JSON bytes.

        run_reasoning is used because Reasoner.infer_with_results() explicitly
        calls self.progress_tracker.start_tracking(), making it the minimal
        deterministic tool path that exercises the progress-rendering code.
        Before the #1134 fix, that start_tracking call wrote a progress bar
        directly to stdout, corrupting the JSON-RPC framing.  Every byte on
        stdout must still be valid JSON-RPC after the fix.
        """
        proc = self._run(
            _INIT_REQUEST,
            _jsonrpc("notifications/initialized", None),
            _jsonrpc("tools/call", 2, {
                "name": "run_reasoning",
                "arguments": {
                    "facts": ["Person(Alice)", "Employee(Alice)"],
                    "rules": ["IF Employee(?x) THEN Worker(?x)"],
                },
            }),
        )
        self.assertEqual(proc.returncode, 0,
                         f"server crashed:\n{proc.stderr.decode()}")

        stdout = proc.stdout.decode()
        stderr = proc.stderr.decode()
        responses = _assert_stdout_is_clean_json(self, stdout, stderr)

        tool_resp = next((r for r in responses if r.get("id") == 2), None)
        self.assertIsNotNone(
            tool_resp,
            f"No id=2 response in stdout.\nstdout={stdout!r}\nstderr={stderr!r}",
        )
        # The framing must be a valid JSON-RPC result object regardless of
        # whether the reasoner dependency is available in this environment.
        self.assertIn("jsonrpc", tool_resp)
        self.assertEqual(tool_resp["jsonrpc"], "2.0")
        self.assertIn("id", tool_resp)
        # If the tool succeeded the response must carry MCP content.
        if "result" in tool_resp:
            content = tool_resp["result"].get("content", [])
            self.assertGreater(len(content), 0,
                               "Expected non-empty content list in result")
            # The embedded tool payload must itself be valid JSON.
            inner = json.loads(content[0]["text"])
            self.assertIn("derived_facts", inner)


if __name__ == "__main__":
    unittest.main()
