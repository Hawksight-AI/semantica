"""Console progress must be written to stderr, never to stdout.

Progress is diagnostic output. Writing it to stdout corrupts any program that
carries a machine-readable protocol there — the stdio MCP servers put
newline-delimited JSON-RPC on stdout, and a progress bar interleaved with a
response body makes that response unparseable (#1134).

Both servers currently defend against this by setting
SEMANTICA_DISABLE_PROGRESS, and a console display is only attached when the
console is interactive. Those are containments, not the fix: they give up
progress output entirely, and every future entry point has to remember them.
Writing to the correct stream in the first place is what these tests pin.
"""

import importlib
import io
import sys

import pytest


@pytest.fixture
def progress_module():
    """Import the real progress_tracker, bypassing a mocked sys.modules entry.

    tests/test_extractors_dispatch.py assigns a MagicMock over
    'semantica.utils.progress_tracker' at import time and never restores it, so
    a plain module-level import here returns mocks when that file has already
    run. Dropping the cached entry re-imports the real module.

    Both bindings are restored afterwards: importing a submodule also rebinds it
    as an attribute of its parent package, so restoring only the sys.modules
    entry would leave `semantica.utils.progress_tracker` and
    `sys.modules["semantica.utils.progress_tracker"]` pointing at different
    objects for every test that follows.
    """
    name = "semantica.utils.progress_tracker"
    attr = name.rsplit(".", 1)[1]
    parent = importlib.import_module("semantica.utils")

    missing = object()
    saved_entry = sys.modules.get(name, missing)
    saved_attr = getattr(parent, attr, missing)

    sys.modules.pop(name, None)
    try:
        module = importlib.import_module(name)
        assert hasattr(module, "__file__"), "expected the real module, got a stand-in"
        yield module
    finally:
        if saved_entry is missing:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = saved_entry

        if saved_attr is missing:
            if hasattr(parent, attr):
                delattr(parent, attr)
        else:
            setattr(parent, attr, saved_attr)


@pytest.fixture
def display_cls(progress_module):
    return progress_module.ConsoleProgressDisplay


@pytest.fixture
def make_item(progress_module):
    def _make(**overrides):
        defaults = dict(
            module="kg",
            submodule="Reasoner",
            message="Inferring facts",
            status="running",
            total_items=10,
            processed_items=3,
        )
        defaults.update(overrides)
        return progress_module.ProgressItem(**defaults)

    return _make


class TestProgressStreamDefaults:
    def test_defaults_to_stderr(self, display_cls):
        assert display_cls().stream is sys.stderr

    def test_default_is_not_stdout(self, display_cls):
        """The whole point: stdout stays clean for protocol traffic."""
        assert display_cls().stream is not sys.stdout

    def test_stream_follows_rebinding(self, display_cls, monkeypatch):
        """Resolved per write, so pytest capture and later rebinds are honoured."""
        display = display_cls()
        replacement = io.StringIO()
        monkeypatch.setattr(sys, "stderr", replacement)
        assert display.stream is replacement

    def test_explicit_stream_overrides_the_default(self, display_cls):
        buffer = io.StringIO()
        assert display_cls(stream=buffer).stream is buffer


class TestProgressWritesGoToTheStream:
    def test_update_writes_to_the_configured_stream(self, display_cls, make_item):
        buffer = io.StringIO()
        display = display_cls(stream=buffer, use_emoji=False, update_interval=0.0)

        display.update(make_item())

        assert buffer.getvalue(), "progress should have been rendered"

    def test_update_writes_nothing_to_stdout(self, display_cls, make_item, monkeypatch):
        """Regression guard for #1134: stdout must stay untouched."""
        fake_stdout = io.StringIO()
        monkeypatch.setattr(sys, "stdout", fake_stdout)
        buffer = io.StringIO()

        display = display_cls(stream=buffer, use_emoji=False, update_interval=0.0)
        display.update(make_item())
        display.clear()

        assert fake_stdout.getvalue() == "", (
            f"console progress leaked to stdout: {fake_stdout.getvalue()!r}"
        )

    def test_default_display_writes_nothing_to_stdout(
        self, display_cls, make_item, monkeypatch
    ):
        """Same guard without an explicit stream, i.e. the real default path."""
        fake_stdout = io.StringIO()
        fake_stderr = io.StringIO()
        monkeypatch.setattr(sys, "stdout", fake_stdout)
        monkeypatch.setattr(sys, "stderr", fake_stderr)

        display = display_cls(use_emoji=False, update_interval=0.0)
        display.update(make_item())

        assert fake_stdout.getvalue() == ""
        assert fake_stderr.getvalue(), "progress should have gone to stderr"

    def test_clear_flushes_the_stream_not_stdout(self, display_cls, monkeypatch):
        flushed = []

        class RecordingStream(io.StringIO):
            def flush(self):
                flushed.append("stream")

        class ExplodingStdout(io.StringIO):
            def flush(self):  # pragma: no cover - fails the test if reached
                raise AssertionError("progress must not flush stdout")

        monkeypatch.setattr(sys, "stdout", ExplodingStdout())
        display = display_cls(
            stream=RecordingStream(), use_emoji=False, update_interval=0.0
        )

        display.clear()

        assert flushed == ["stream"]


class TestEncodingFallback:
    def test_falls_back_when_the_stream_cannot_encode(self, display_cls):
        """A cp1252-style console must not raise on emoji; it degrades instead."""

        class AsciiOnly(io.StringIO):
            encoding = "ascii"

            def write(self, text):
                text.encode("ascii")  # raises UnicodeEncodeError on emoji
                return super().write(text)

        buffer = AsciiOnly()
        display = display_cls(stream=buffer, use_emoji=True, update_interval=0.0)

        display._safe_write("progress \U0001f504 bar\n")

        assert "progress" in buffer.getvalue()


if __name__ == "__main__":
    pytest.main([__file__])
