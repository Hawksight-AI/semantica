"""ConsoleProgressDisplay must keep stdout clean for stdio protocols (#1134).

The root-level MCP server speaks newline-delimited JSON-RPC over stdout, so
any progress-bar output written there corrupts the response a strict client
can no longer parse. Progress is diagnostic output and now defaults to
stderr, with ``SEMANTICA_PROGRESS_STREAM=stdout`` restoring the old behavior.
"""

import io
import sys
import unittest
from unittest import mock

from semantica.utils.progress_tracker import ConsoleProgressDisplay, ProgressItem


def _drive_update(display: ConsoleProgressDisplay) -> None:
    item = ProgressItem(
        module="kg",
        submodule="Building",
        status="running",
        progress_percentage=50.0,
        message="Building knowledge graph",
    )
    display.update(item)


class ConsoleProgressDisplayStreamTest(unittest.TestCase):
    def _run_with_captured_streams(self, env: dict):
        stdout, stderr = io.StringIO(), io.StringIO()
        with mock.patch.dict("os.environ", env, clear=False):
            display = ConsoleProgressDisplay(update_interval=0.0)
            # Pin last_update so _should_update lets the update through.
            display.last_update = -1.0
            with mock.patch("sys.stdout", stdout), mock.patch("sys.stderr", stderr):
                _drive_update(display)
        return stdout.getvalue(), stderr.getvalue()

    def test_progress_defaults_to_stderr_and_leaves_stdout_clean(self):
        stdout_text, stderr_text = self._run_with_captured_streams(
            {"SEMANTICA_PROGRESS_STREAM": ""}
        )

        self.assertEqual(
            stdout_text,
            "",
            "stdout must carry no progress output: stdio protocols require it pristine",
        )
        self.assertIn("Building", stderr_text)

    def test_explicit_stdout_stream_restores_old_behavior(self):
        stdout_text, stderr_text = self._run_with_captured_streams(
            {"SEMANTICA_PROGRESS_STREAM": "stdout"}
        )

        self.assertIn("Building", stdout_text)
        self.assertEqual(stderr_text, "")

    def test_invalid_stream_value_falls_back_to_stderr(self):
        stdout_text, stderr_text = self._run_with_captured_streams(
            {"SEMANTICA_PROGRESS_STREAM": "tcp://nowhere"}
        )

        self.assertEqual(stdout_text, "")
        self.assertIn("Building", stderr_text)


if __name__ == "__main__":
    unittest.main()
