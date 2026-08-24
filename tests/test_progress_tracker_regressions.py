import os
import subprocess
import sys
import threading
from pathlib import Path

import pytest

import semantica.utils.progress_tracker as progress_module


@pytest.fixture(autouse=True)
def reset_progress_singletons(monkeypatch):
    monkeypatch.delenv("SEMANTICA_DISABLE_PROGRESS", raising=False)
    monkeypatch.delenv("SEMANTICA_FORCE_PROGRESS", raising=False)
    progress_module.ProgressTracker._instance = None
    progress_module._global_tracker = None
    yield
    progress_module.ProgressTracker._instance = None
    progress_module._global_tracker = None


class _FakeStdout:
    """Minimal stdout stand-in with controllable TTY reporting."""

    encoding = "utf-8"

    def __init__(self, tty):
        self._tty = tty
        self.written = []

    def isatty(self):
        return self._tty

    def write(self, text):
        self.written.append(text)
        return len(text)

    def flush(self):
        pass


def _use_stdout(monkeypatch, tty):
    """Point sys.stdout at a fake with the given TTY behaviour, outside Jupyter."""
    stream = _FakeStdout(tty=tty)
    monkeypatch.setattr(sys, "stdout", stream)
    monkeypatch.setattr(
        progress_module.ProgressTracker, "_detect_jupyter", lambda *_: False
    )
    return stream


def _displays_of(tracker, display_cls):
    return [d for d in tracker.displays if isinstance(d, display_cls)]


def _install_tracker_as_singleton(tracker: progress_module.ProgressTracker) -> None:
    progress_module.ProgressTracker._instance = tracker
    progress_module._global_tracker = tracker


def _assert_finishes_quickly(target, timeout: float = 1.0) -> None:
    errors = []

    def runner():
        try:
            target()
        except Exception as exc:  # pragma: no cover - re-raised below
            errors.append(exc)

    thread = threading.Thread(target=runner, daemon=True)
    thread.start()
    thread.join(timeout)

    assert not thread.is_alive(), "operation deadlocked"
    if errors:
        raise errors[0]


def test_start_tracking_pipeline_console_callback_does_not_deadlock():
    tracker = progress_module.ProgressTracker(enabled=True, use_emoji=False, update_interval=0)
    tracker.displays = [progress_module.ConsoleProgressDisplay(use_emoji=False, update_interval=0)]
    _install_tracker_as_singleton(tracker)
    tracker.register_pipeline_modules("pipeline-1", ["core"], {"core": 0})

    _assert_finishes_quickly(
        lambda: tracker.start_tracking(
            module="core",
            submodule="Semantica",
            message="Building",
            pipeline_id="pipeline-1",
        )
    )


def test_update_progress_pipeline_console_callback_does_not_deadlock():
    tracker = progress_module.ProgressTracker(enabled=True, use_emoji=False, update_interval=0)
    _install_tracker_as_singleton(tracker)
    tracker.displays = []
    tracker.register_pipeline_modules("pipeline-1", ["core"], {"core": 0})
    tracking_id = tracker.start_tracking(
        module="core",
        submodule="Semantica",
        message="Building",
        pipeline_id="pipeline-1",
    )
    tracker.displays = [progress_module.ConsoleProgressDisplay(use_emoji=False, update_interval=0)]

    _assert_finishes_quickly(
        lambda: tracker.update_progress(
            tracking_id,
            processed=1,
            total=1,
            message="Processing sources... 1/1",
        )
    )


def test_progress_tracker_constructor_can_disable_progress():
    tracker = progress_module.ProgressTracker(enabled=False)

    assert tracker.enabled is False
    assert tracker.start_tracking(module="core", submodule="test") == ""


def test_disable_progress_env_prevents_reenable(monkeypatch):
    monkeypatch.setenv("SEMANTICA_DISABLE_PROGRESS", "1")
    progress_module.ProgressTracker._instance = None
    progress_module._global_tracker = None

    tracker = progress_module.get_progress_tracker()
    tracker.enabled = True

    assert tracker.enabled is False
    assert tracker.start_tracking(module="core", submodule="test") == ""


def test_console_display_omitted_when_stdout_is_not_a_tty(monkeypatch):
    _use_stdout(monkeypatch, tty=False)

    tracker = progress_module.ProgressTracker(use_emoji=False, update_interval=0)

    assert _displays_of(tracker, progress_module.ConsoleProgressDisplay) == []


def test_console_display_present_when_stdout_is_a_tty(monkeypatch):
    _use_stdout(monkeypatch, tty=True)

    tracker = progress_module.ProgressTracker(use_emoji=False, update_interval=0)

    assert _displays_of(tracker, progress_module.ConsoleProgressDisplay)


def test_file_display_survives_non_tty_stdout(monkeypatch):
    _use_stdout(monkeypatch, tty=False)

    tracker = progress_module.ProgressTracker(use_emoji=False, update_interval=0)

    assert _displays_of(tracker, progress_module.FileProgressDisplay)


def test_force_progress_env_restores_console_display_on_non_tty(monkeypatch):
    monkeypatch.setenv("SEMANTICA_FORCE_PROGRESS", "1")
    _use_stdout(monkeypatch, tty=False)

    tracker = progress_module.ProgressTracker(use_emoji=False, update_interval=0)

    assert _displays_of(tracker, progress_module.ConsoleProgressDisplay)


def test_disable_progress_env_beats_force_progress_env(monkeypatch):
    monkeypatch.setenv("SEMANTICA_DISABLE_PROGRESS", "1")
    monkeypatch.setenv("SEMANTICA_FORCE_PROGRESS", "1")
    stream = _use_stdout(monkeypatch, tty=False)

    tracker = progress_module.ProgressTracker(use_emoji=False, update_interval=0)
    _install_tracker_as_singleton(tracker)

    assert tracker.enabled is False
    assert tracker.start_tracking(module="core", submodule="test") == ""
    assert stream.written == []


def test_non_tty_stdout_stays_silent_after_module_reenables_tracker(monkeypatch):
    stream = _use_stdout(monkeypatch, tty=False)
    tracker = progress_module.ProgressTracker(use_emoji=False, update_interval=0)
    _install_tracker_as_singleton(tracker)

    # Mirrors the ~20 modules that do `self.progress_tracker.enabled = True`.
    tracker.enabled = True
    tracking_id = tracker.start_tracking(
        module="core", submodule="Semantica", message="Building"
    )
    tracker.update_progress(tracking_id, processed=1, total=1, message="Processing")

    assert stream.written == []


def test_build_knowledge_base_subprocess_does_not_deadlock():
    root = Path(__file__).resolve().parents[1]
    runtime_dir = root / "test_data" / "runtime" / f"build-regression-{os.getpid()}"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    sample = runtime_dir / "sample.txt"
    sample.write_text("Semantica builds small local knowledge graphs.", encoding="utf-8")

    code = (
        "from semantica.core import Semantica; "
        f"result = Semantica().build_knowledge_base([{str(sample)!r}], embeddings=False, graph=False); "
        "print(result['statistics']['sources_processed'])"
    )
    env = os.environ.copy()
    env["PYTHONPATH"] = str(root)
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=root,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=15,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "1" in result.stdout
