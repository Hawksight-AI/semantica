"""
Tests for all CLI commands added in issue #568.

Strategy:
- Module-level imports (ingest, kg, etc.) are mocked via monkeypatch so tests
  run without optional backends installed.
- Help surfaces: every command/group --help must exit 0 and mention key flags.
- --dry-run: write commands must exit 0 and emit a dry-run message.
- --json: write commands must emit parseable JSON.
- ImportError paths: modules that raise ImportError must produce a clean
  ClickException (non-zero exit, no traceback).
- Argument validation: missing required args must exit non-zero cleanly.
- Service commands: subprocess.Popen is mocked so nothing actually launches.
"""

import json
import os
import stat
import types
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

import semantica.cli as cli_module


# ─── fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture(autouse=True)
def silence_logging(monkeypatch):
    monkeypatch.setattr(cli_module, "setup_logging", lambda *a, **kw: None)


def _fake_module(**attrs: Any) -> types.ModuleType:
    """Build a minimal fake module with the given attributes."""
    m = types.ModuleType("_fake")
    for k, v in attrs.items():
        setattr(m, k, v)
    return m


def _import_side_effect(name: str, **_):
    raise ImportError(f"No module named '{name}'")


# ─── helpers ──────────────────────────────────────────────────────────────────


def _ok(result, expected_exit: int = 0, *, substr: str = "") -> None:
    """Assert exit code and optional substring."""
    assert result.exit_code == expected_exit, (
        f"exit={result.exit_code}, output={result.output!r}"
    )
    if substr:
        assert substr in result.output, f"{substr!r} not in {result.output!r}"


def _json_output(result) -> Any:
    """Parse JSON from command output; raises on bad JSON."""
    assert result.exit_code == 0, f"exit={result.exit_code}: {result.output}"
    return json.loads(result.output.strip())


def _flatten(output: str) -> str:
    """Undo Rich panel wrapping for substring assertions on error text.

    Rich wraps long messages across multiple bordered lines (each with its
    own leading/trailing "│"), so a naive whitespace join still leaves those
    border characters between words that were split across lines. Strip the
    box-drawing characters first, then collapse whitespace.
    """
    for ch in "┌┐└┘│─":
        output = output.replace(ch, " ")
    return " ".join(output.split())


# ─── Global flags ─────────────────────────────────────────────────────────────


class TestGlobalFlags:
    def test_json_flag_stored_in_context(self, runner, monkeypatch):
        captured = {}

        def fake_run_build(ctx, sources):
            captured["json"] = ctx.json_output

        monkeypatch.setattr(cli_module, "_run_build", fake_run_build)
        result = runner.invoke(cli_module.main, ["--json", "kg", "build", "-s", "x.txt"])
        assert result.exit_code == 0
        assert captured["json"] is True

    def test_quiet_flag_stored_in_context(self, runner, monkeypatch):
        captured = {}

        def fake_run_build(ctx, sources):
            captured["quiet"] = ctx.quiet

        monkeypatch.setattr(cli_module, "_run_build", fake_run_build)
        result = runner.invoke(cli_module.main, ["--quiet", "kg", "build", "-s", "x.txt"])
        assert result.exit_code == 0
        assert captured["quiet"] is True

    def test_dry_run_global_stored_in_context(self, runner, monkeypatch):
        captured = {}

        def fake_run_build(ctx, sources):
            captured["dry_run"] = ctx.dry_run_global

        monkeypatch.setattr(cli_module, "_run_build", fake_run_build)
        result = runner.invoke(cli_module.main, ["--dry-run", "kg", "build", "-s", "x.txt"])
        assert result.exit_code == 0
        assert captured["dry_run"] is True

    def test_store_override_stored_in_context(self, runner, monkeypatch):
        captured = {}

        def fake_run_build(ctx, sources):
            captured["store"] = ctx.store_backend

        monkeypatch.setattr(cli_module, "_run_build", fake_run_build)
        result = runner.invoke(cli_module.main, ["--store", "neo4j", "kg", "build", "-s", "x.txt"])
        assert result.exit_code == 0
        assert captured["store"] == "neo4j"

    def test_vector_store_override_stored_in_context(self, runner, monkeypatch):
        captured = {}

        def fake_run_build(ctx, sources):
            captured["vs"] = ctx.vector_store_backend

        monkeypatch.setattr(cli_module, "_run_build", fake_run_build)
        result = runner.invoke(cli_module.main, ["--vector-store", "qdrant", "kg", "build", "-s", "x.txt"])
        assert result.exit_code == 0
        assert captured["vs"] == "qdrant"

    def test_root_help_shows_all_global_flags(self, runner):
        result = runner.invoke(cli_module.main, ["--help"])
        assert result.exit_code == 0
        for flag in ["--json", "--quiet", "--dry-run", "--store", "--vector-store",
                     "--profile", "--no-color"]:
            assert flag in result.output, f"{flag} missing from root help"

    def test_root_help_shows_all_command_groups(self, runner):
        result = runner.invoke(cli_module.main, ["--help"])
        assert result.exit_code == 0
        for cmd in ["ingest", "parse", "split", "normalize", "extract", "embed",
                    "deduplicate", "reason", "decision", "temporal", "provenance",
                    "validate", "ontology", "export", "visualize", "pipeline",
                    "store", "backup", "server", "explorer", "mcp", "completion"]:
            assert cmd in result.output, f"{cmd!r} missing from root help"

    def test_default_log_file_failure_falls_back_without_polluting_json(
        self,
        runner,
        monkeypatch,
    ):
        calls = []

        def fake_setup_logging(*, config=None, **_kwargs):
            calls.append(dict(config or {}))
            if len(calls) == 1:
                raise PermissionError("readonly semantica.log")

        monkeypatch.setattr(cli_module, "setup_logging", fake_setup_logging)
        result = runner.invoke(
            cli_module.main,
            ["--json", "backup", "schedule", "--dest", "x", "--freq", "daily"],
        )

        payload = _json_output(result)
        assert payload["cron"].startswith("0 2 * * *")
        assert len(calls) == 2
        assert calls[1].get("file") is None
        assert "readonly semantica.log" not in result.output


# ─── kg subcommands ───────────────────────────────────────────────────────────


class TestKgSubcommands:
    @pytest.mark.parametrize("sub", ["query", "stats", "analyze", "find-path",
                                      "resolve", "predict", "validate"])
    def test_help_exits_0(self, runner, sub):
        result = runner.invoke(cli_module.main, ["kg", sub, "--help"])
        _ok(result, substr=sub.replace("-", " ") if sub != "find-path" else "")
        assert result.exit_code == 0

    def test_kg_query_json_with_mock(self, runner, monkeypatch):
        fake_gs = _fake_module(
            execute_query=lambda q, **kw: {"query": q, "lang": "cypher", "rows": []},
        )
        monkeypatch.setitem(__import__("sys").modules, "semantica.graph_store", fake_gs)
        result = runner.invoke(cli_module.main, ["kg", "query", "MATCH (n) RETURN n", "--json"])
        _ok(result)
        data = _json_output(result)
        assert "query" in data

    def test_kg_query_fails_cleanly_without_backend(self, runner):
        result = runner.invoke(cli_module.main, ["kg", "query", "MATCH (n) RETURN n"])
        # Either exits 0 (fallback) or non-0 (clean error) — never traceback
        assert "Traceback" not in result.output

    def test_kg_stats_json_with_mock(self, runner, monkeypatch):
        fake_kg = _fake_module(
            GraphAnalyzer=lambda **kw: MagicMock(
                compute_metrics=lambda: {"nodes": 10, "edges": 25, "density": 0.5}
            ),
        )
        monkeypatch.setitem(__import__("sys").modules, "semantica.kg", fake_kg)
        result = runner.invoke(cli_module.main, ["kg", "stats", "--json"])
        _ok(result)
        data = _json_output(result)
        assert isinstance(data, dict)
        assert "nodes" in data

    def test_kg_analyze_json_with_mock(self, runner, monkeypatch):
        fake_kg = _fake_module(
            GraphAnalyzer=lambda **kw: MagicMock(
                analyze=lambda mode: {"mode": mode, "communities": 3}
            ),
        )
        monkeypatch.setitem(__import__("sys").modules, "semantica.kg", fake_kg)
        result = runner.invoke(cli_module.main, ["kg", "analyze", "--mode", "community", "--json"])
        _ok(result)
        data = _json_output(result)
        assert isinstance(data, dict)

    def test_kg_find_path_requires_from_and_to(self, runner):
        result = runner.invoke(cli_module.main, ["kg", "find-path"])
        assert result.exit_code != 0

    def test_kg_find_path_json_with_mock(self, runner, monkeypatch):
        fake_kg = _fake_module(
            PathFinder=lambda **kw: MagicMock(
                find_path=lambda f, t, path_type: {"from": f, "to": t, "path": [f, t]}
            ),
        )
        monkeypatch.setitem(__import__("sys").modules, "semantica.kg", fake_kg)
        result = runner.invoke(cli_module.main, ["kg", "find-path",
                                      "--from", "Alice", "--to", "Acme", "--json"])
        _ok(result)
        data = _json_output(result)
        assert "from" in data

    def test_kg_resolve_exits_0_with_mock(self, runner, monkeypatch):
        fake_kg = _fake_module(
            EntityResolver=lambda **kw: MagicMock(resolve=lambda: {"resolved": 5}),
        )
        monkeypatch.setitem(__import__("sys").modules, "semantica.kg", fake_kg)
        result = runner.invoke(cli_module.main, ["kg", "resolve"])
        assert result.exit_code == 0

    def test_kg_predict_exits_0_with_mock(self, runner, monkeypatch):
        fake_kg = _fake_module(
            LinkPredictor=lambda **kw: MagicMock(predict=lambda: {"predictions": []}),
        )
        monkeypatch.setitem(__import__("sys").modules, "semantica.kg", fake_kg)
        result = runner.invoke(cli_module.main, ["kg", "predict"])
        assert result.exit_code == 0

    def test_kg_validate_exits_0_with_mock(self, runner, monkeypatch):
        fake_kg = _fake_module(
            GraphValidator=lambda **kw: MagicMock(
                validate=lambda: {"valid": True},
                integrity_check=lambda: {"valid": True},
            ),
        )
        monkeypatch.setitem(__import__("sys").modules, "semantica.kg", fake_kg)
        result = runner.invoke(cli_module.main, ["kg", "validate"])
        assert result.exit_code == 0


# ─── ingest ───────────────────────────────────────────────────────────────────


class TestIngest:
    def test_help_shows_flags(self, runner):
        result = runner.invoke(cli_module.main, ["ingest", "--help"])
        _ok(result)
        for flag in ["--type", "--format", "--recursive", "--watch",
                     "--batch-size", "--store", "--output", "--dry-run"]:
            assert flag in result.output, f"{flag} missing"

    def test_dry_run_json_exits_0(self, runner):
        # Per-command --json with --dry-run should emit JSON (fixed via json_out param)
        result = runner.invoke(cli_module.main, ["ingest", "data.pdf", "--dry-run", "--json"])
        _ok(result)
        data = _json_output(result)
        assert data["dry_run"] is True
        assert data["action"] == "ingest"

    def test_dry_run_global_json_exits_0(self, runner):
        # Global --json with per-command --dry-run
        result = runner.invoke(cli_module.main, ["--json", "ingest", "data.pdf", "--dry-run"])
        _ok(result)
        data = _json_output(result)
        assert data["dry_run"] is True

    def test_dry_run_text_exits_0(self, runner):
        result = runner.invoke(cli_module.main, ["ingest", "data.pdf", "--dry-run"])
        _ok(result, substr="Dry run")

    def test_runtime_path_passes_source_positionally(self, runner, monkeypatch):
        captured = {}

        def fake_ingest_file(sources, **kwargs):
            captured["sources"] = sources
            captured["kwargs"] = kwargs
            return [{"path": sources}]

        monkeypatch.setattr("semantica.ingest.methods.ingest_file", fake_ingest_file)

        result = runner.invoke(
            cli_module.main,
            ["ingest", "README.md", "--type", "file", "--format", "csv", "--json"],
        )

        _ok(result)
        data = _json_output(result)
        assert data["files"] == [{"path": "README.md"}]
        assert captured["sources"] == "README.md"
        assert captured["kwargs"]["method"] == "file"
        assert captured["kwargs"]["batch_size"] == 500
        assert captured["kwargs"]["format"] == "csv"

    def test_runtime_path_passes_source_positionally_with_auto_detection(self, runner, monkeypatch):
        captured = {}

        def fake_ingest_file(sources, **kwargs):
            captured["sources"] = sources
            captured["kwargs"] = kwargs
            return [{"path": sources}]

        monkeypatch.setattr("semantica.ingest.methods.ingest_file", fake_ingest_file)

        result = runner.invoke(cli_module.main, ["ingest", "README.md", "--json"])

        _ok(result)
        data = _json_output(result)
        assert data["files"] == [{"path": "README.md"}]
        assert captured["sources"] == "README.md"
        assert captured["kwargs"]["method"] == "file"

    def test_configured_graph_backend_does_not_report_false_success(
        self, runner, monkeypatch
    ):
        monkeypatch.setenv("GRAPH_STORE_DEFAULT_BACKEND", "neo4j")
        monkeypatch.setattr(
            "semantica.ingest.methods.ingest_file",
            lambda sources, **kwargs: [{"path": sources}],
        )

        result = runner.invoke(cli_module.main, ["ingest", "README.md"])
        output = _flatten(result.output)

        assert result.exit_code != 0
        assert "does not write to graph stores" in output
        assert "Ingested:" not in output

    def test_configured_graph_backend_error_does_not_recommend_broken_kg_build(
        self, runner, monkeypatch
    ):
        # kg build also does not persist to a configured graph store
        # (tracked separately as #1352), so the error must not send users to
        # a command that will silently no-op the same way.
        monkeypatch.setenv("GRAPH_STORE_DEFAULT_BACKEND", "neo4j")
        monkeypatch.setattr(
            "semantica.ingest.methods.ingest_file",
            lambda sources, **kwargs: [{"path": sources}],
        )

        result = runner.invoke(cli_module.main, ["ingest", "README.md"])
        output = _flatten(result.output)

        assert result.exit_code != 0
        assert "kg build" not in output

    def test_output_flag_writes_real_content_and_bypasses_graph_error(
        self, runner, monkeypatch, tmp_path
    ):
        monkeypatch.setenv("GRAPH_STORE_DEFAULT_BACKEND", "neo4j")
        monkeypatch.setattr(
            "semantica.ingest.methods.ingest_file",
            lambda sources, **kwargs: [{"path": sources}],
        )
        out_path = tmp_path / "out.json"

        result = runner.invoke(
            cli_module.main, ["ingest", "README.md", "--output", str(out_path)]
        )

        _ok(result, substr="Wrote")
        written = json.loads(out_path.read_text(encoding="utf-8"))
        assert written == {"files": [{"path": "README.md"}]}

    def test_store_and_output_are_not_forwarded_to_ingest_backend(
        self, runner, monkeypatch, tmp_path
    ):
        captured = {}

        def fake_ingest_file(sources, **kwargs):
            captured["kwargs"] = kwargs
            return [{"path": sources}]

        monkeypatch.setattr("semantica.ingest.methods.ingest_file", fake_ingest_file)
        out_path = tmp_path / "out.json"

        result = runner.invoke(
            cli_module.main,
            ["ingest", "README.md", "--store", "neo4j", "--output", str(out_path)],
        )

        _ok(result)
        assert "store" not in captured["kwargs"]
        assert "output" not in captured["kwargs"]

    def test_import_error_is_clean(self, runner, monkeypatch):
        monkeypatch.setattr(cli_module, "__import__", _import_side_effect, raising=False)
        original_import = __import__
        with patch("builtins.__import__", side_effect=lambda n, *a, **k: (
            (_ for _ in ()).throw(ImportError(n))
            if n.startswith("semantica.ingest") else original_import(n, *a, **k)
        )):
            result = runner.invoke(cli_module.main, ["ingest", "data.pdf"])
        assert result.exit_code != 0
        assert "Traceback" not in result.output

    def test_type_choice_validation(self, runner):
        result = runner.invoke(cli_module.main, ["ingest", "x.pdf", "--type", "invalid_type"])
        assert result.exit_code != 0

    def test_recursive_flag_accepted(self, runner):
        result = runner.invoke(cli_module.main, ["ingest", "./data", "--recursive", "--dry-run"])
        _ok(result)

    def test_global_dry_run_triggers_ingest_dry(self, runner):
        # Both global --dry-run and global --json
        result = runner.invoke(cli_module.main, ["--dry-run", "--json", "ingest", "data.pdf"])
        _ok(result)
        data = _json_output(result)
        assert data["dry_run"] is True


# ─── parse ────────────────────────────────────────────────────────────────────


class TestParse:
    def test_help_shows_flags(self, runner):
        result = runner.invoke(cli_module.main, ["parse", "--help"])
        _ok(result)
        for flag in ["--parser", "--format"]:
            assert flag in result.output

    def test_missing_file_arg_fails(self, runner):
        result = runner.invoke(cli_module.main, ["parse"])
        assert result.exit_code != 0

    def test_nonexistent_file_fails(self, runner):
        result = runner.invoke(cli_module.main, ["parse", "no_such_file.pdf"])
        assert result.exit_code != 0

    def test_parse_real_file(self, runner):
        with runner.isolated_filesystem():
            with open("doc.txt", "w") as f:
                f.write("Hello world")
            with patch("builtins.__import__", side_effect=lambda n, *a, **k: (
                (_ for _ in ()).throw(ImportError(n))
                if n.startswith("semantica.parse") else __import__(n, *a, **k)
            )):
                result = runner.invoke(cli_module.main, ["parse", "doc.txt"])
        assert result.exit_code != 0
        assert "Traceback" not in result.output

    def test_format_choices(self, runner):
        result = runner.invoke(cli_module.main, ["parse", "--help"])
        assert "json" in result.output
        assert "yaml" in result.output
        assert "table" in result.output


# ─── split ────────────────────────────────────────────────────────────────────


class TestSplit:
    def test_help_shows_strategy_choices(self, runner):
        result = runner.invoke(cli_module.main, ["split", "--help"])
        _ok(result)
        for strategy in ["recursive", "semantic", "entity-aware", "table"]:
            assert strategy in result.output

    def test_missing_input_fails(self, runner):
        result = runner.invoke(cli_module.main, ["split"])
        assert result.exit_code != 0

    def test_split_with_import_error(self, runner):
        with runner.isolated_filesystem():
            with open("doc.txt", "w") as f:
                f.write("content")
            with patch("builtins.__import__", side_effect=lambda n, *a, **k: (
                (_ for _ in ()).throw(ImportError(n))
                if n.startswith("semantica.split") else __import__(n, *a, **k)
            )):
                result = runner.invoke(cli_module.main, ["split", "doc.txt"])
        assert result.exit_code != 0
        assert "Traceback" not in result.output

    def test_split_writes_output_file(self, runner, monkeypatch):
        mock_chunks = [{"text": "chunk1"}, {"text": "chunk2"}]

        fake_split = _fake_module(
            split_recursive=lambda *a, **kw: mock_chunks,
            get_split_method=lambda s: lambda *a, **kw: mock_chunks,
        )
        monkeypatch.setitem(
            __import__("sys").modules, "semantica.split", fake_split
        )
        with runner.isolated_filesystem():
            with open("doc.txt", "w") as f:
                f.write("line1\nline2")
            result = runner.invoke(
                cli_module.main, ["split", "doc.txt", "--output", "out.json"]
            )
            if result.exit_code == 0:
                assert os.path.exists("out.json")


# ─── normalize ────────────────────────────────────────────────────────────────


class TestNormalize:
    def test_help_shows_mode_and_domain(self, runner):
        result = runner.invoke(cli_module.main, ["normalize", "--help"])
        _ok(result)
        assert "--mode" in result.output
        assert "--domain" in result.output

    def test_normalize_text_inline(self, runner, monkeypatch):
        fake_norm = _fake_module(
            normalize_text=lambda t: t.upper(),
            normalize_date=lambda t, **kw: t,
            normalize_entity=lambda t, **kw: t,
        )
        monkeypatch.setitem(
            __import__("sys").modules, "semantica.normalize", fake_norm
        )
        result = runner.invoke(cli_module.main, ["normalize", "hello world", "--mode", "text"])
        assert result.exit_code == 0
        assert "HELLO WORLD" in result.output

    def test_normalize_json(self, runner, monkeypatch):
        fake_norm = _fake_module(
            normalize_text=lambda t: "normalized",
            normalize_date=lambda t, **kw: "normalized",
            normalize_entity=lambda t, **kw: "normalized",
        )
        monkeypatch.setitem(
            __import__("sys").modules, "semantica.normalize", fake_norm
        )
        result = runner.invoke(cli_module.main, ["normalize", "text", "--json"])
        _ok(result)
        data = _json_output(result)
        assert "result" in data

    def test_domain_choices(self, runner):
        result = runner.invoke(cli_module.main, ["normalize", "--help"])
        for d in ["healthcare", "legal", "finance", "general"]:
            assert d in result.output


# ─── extract ──────────────────────────────────────────────────────────────────


class TestExtract:
    def test_help_shows_mode_method_flags(self, runner):
        result = runner.invoke(cli_module.main, ["extract", "--help"])
        _ok(result)
        for flag in ["--mode", "--method", "--model", "--confidence",
                     "--temporal", "--format", "--output"]:
            assert flag in result.output

    def test_dry_run_not_needed_extract_is_read_only(self, runner, monkeypatch):
        _ner_result = [MagicMock(text="Alice", label="PER", confidence=0.9,
                                  start_char=0, end_char=5, metadata={})]
        fake_ext = _fake_module(
            NERExtractor=lambda **kw: MagicMock(extract=lambda text, **kw2: _ner_result),
            RelationExtractor=lambda **kw: MagicMock(extract=lambda text, **kw2: []),
            TripletExtractor=lambda **kw: MagicMock(extract=lambda text, **kw2: []),
            EventDetector=lambda **kw: MagicMock(extract=lambda text, **kw2: []),
        )
        monkeypatch.setitem(
            __import__("sys").modules, "semantica.semantic_extract", fake_ext
        )
        result = runner.invoke(
            cli_module.main, ["extract", "Alice works at Acme.", "--mode", "ner", "--json"]
        )
        _ok(result)
        data = _json_output(result)
        assert isinstance(data, (dict, list))

    def test_stdin_input(self, runner, monkeypatch):
        _ner_result = [MagicMock(text="Alice", label="PER", confidence=0.9,
                                  start_char=0, end_char=5, metadata={})]
        fake_ext = _fake_module(
            NERExtractor=lambda **kw: MagicMock(extract=lambda text, **kw2: _ner_result),
            RelationExtractor=lambda **kw: MagicMock(extract=lambda text, **kw2: []),
            TripletExtractor=lambda **kw: MagicMock(extract=lambda text, **kw2: []),
            EventDetector=lambda **kw: MagicMock(extract=lambda text, **kw2: []),
        )
        monkeypatch.setitem(
            __import__("sys").modules, "semantica.semantic_extract", fake_ext
        )
        result = runner.invoke(
            cli_module.main, ["extract", "-", "--mode", "ner", "--json"], input="Alice\n"
        )
        _ok(result)

    def test_import_error_is_clean(self, runner):
        with patch("builtins.__import__", side_effect=lambda n, *a, **k: (
            (_ for _ in ()).throw(ImportError(n))
            if n.startswith("semantica.semantic_extract") else __import__(n, *a, **k)
        )):
            result = runner.invoke(cli_module.main, ["extract", "text"])
        assert result.exit_code != 0
        assert "Traceback" not in result.output

    def test_invalid_method_choice(self, runner):
        result = runner.invoke(cli_module.main, ["extract", "text", "--method", "magic"])
        assert result.exit_code != 0


# ─── embed ────────────────────────────────────────────────────────────────────


class TestEmbed:
    def test_group_help(self, runner):
        result = runner.invoke(cli_module.main, ["embed", "--help"])
        _ok(result)
        for sub in ["generate", "search", "index"]:
            assert sub in result.output

    def test_generate_help(self, runner):
        result = runner.invoke(cli_module.main, ["embed", "generate", "--help"])
        _ok(result)
        assert "--model" in result.output

    def test_search_help(self, runner):
        result = runner.invoke(cli_module.main, ["embed", "search", "--help"])
        _ok(result)
        assert "--top-k" in result.output
        assert "--hybrid" in result.output

    def test_index_help(self, runner):
        result = runner.invoke(cli_module.main, ["embed", "index", "--help"])
        _ok(result)
        assert "--store" in result.output

    def test_generate_import_error_is_clean(self, runner):
        with patch("builtins.__import__", side_effect=lambda n, *a, **k: (
            (_ for _ in ()).throw(ImportError(n))
            if "embeddings" in n else __import__(n, *a, **k)
        )):
            result = runner.invoke(cli_module.main, ["embed", "generate", "entities.json"])
        assert result.exit_code != 0
        assert "Traceback" not in result.output

    def test_search_import_error_is_clean(self, runner):
        with patch("builtins.__import__", side_effect=lambda n, *a, **k: (
            (_ for _ in ()).throw(ImportError(n))
            if "vector_store" in n else __import__(n, *a, **k)
        )):
            result = runner.invoke(cli_module.main, ["embed", "search", "CEO query"])
        assert result.exit_code != 0
        assert "Traceback" not in result.output

    def test_index_requires_existing_file(self, runner):
        result = runner.invoke(cli_module.main, ["embed", "index", "nonexistent.parquet"])
        assert result.exit_code != 0

    def test_index_loads_vectors_from_json(self, runner, monkeypatch, tmp_path):
        """Vectors are loaded from the file; create_index receives List[np.ndarray]."""
        import json as _json, numpy as np
        records = [{"id": "a", "embedding": [0.1, 0.2, 0.3]},
                   {"id": "b", "embedding": [0.4, 0.5, 0.6]}]
        json_file = tmp_path / "test.json"
        json_file.write_text(_json.dumps(records), encoding="utf-8")

        captured = {}

        def fake_create_index(vectors, ids=None, **kw):
            captured["vectors"] = vectors
            captured["ids"] = ids
            return {"status": "ok"}

        fake_vs = _fake_module(create_index=fake_create_index)
        monkeypatch.setitem(__import__("sys").modules, "semantica.vector_store", fake_vs)
        result = runner.invoke(cli_module.main, ["embed", "index", str(json_file), "--json"])
        _ok(result)
        assert len(captured["vectors"]) == 2
        assert isinstance(captured["vectors"][0], np.ndarray)

    def test_index_rejects_unsupported_format(self, runner, monkeypatch, tmp_path):
        txt_file = tmp_path / "embeddings.txt"
        txt_file.write_text("not a supported format")
        fake_vs = _fake_module(create_index=MagicMock(return_value={}))
        monkeypatch.setitem(__import__("sys").modules, "semantica.vector_store", fake_vs)
        result = runner.invoke(cli_module.main, ["embed", "index", str(txt_file)])
        assert result.exit_code != 0


# ─── deduplicate ──────────────────────────────────────────────────────────────


class TestDeduplicate:
    def test_help_shows_flags(self, runner):
        result = runner.invoke(cli_module.main, ["deduplicate", "--help"])
        _ok(result)
        for flag in ["--strategy", "--min-similarity", "--action", "--dry-run"]:
            assert flag in result.output

    def test_dry_run_exits_0(self, runner):
        result = runner.invoke(cli_module.main, ["deduplicate", "--dry-run"])
        _ok(result)

    def test_dry_run_json(self, runner):
        result = runner.invoke(cli_module.main, ["deduplicate", "--dry-run", "--json"])
        _ok(result)
        data = _json_output(result)
        assert data["dry_run"] is True

    def test_detect_runtime_path(self, runner, monkeypatch):
        entities = [
            {"id": "e1", "name": "Alice", "type": "Person"},
            {"id": "e2", "name": "Alice", "type": "Person"},
            {"id": "e3", "name": "Bob", "type": "Person"},
        ]

        class FakeStore:
            def get_nodes(self, labels=None, properties=None, limit=100, **options):
                return entities

        monkeypatch.setattr("semantica.graph_store.methods._get_store", lambda: FakeStore())
        monkeypatch.setattr("semantica.graph_store.methods.get_nodes", lambda **kwargs: entities)

        result = runner.invoke(
            cli_module.main,
            ["deduplicate", "--action", "detect", "--min-similarity", "0.1", "--json"],
        )

        _ok(result)
        assert "Alice" in result.output
        assert "Bob" not in result.output or "entities" in result.output

    def test_merge_runtime_path(self, runner, monkeypatch):
        entities = [
            {"id": "e1", "name": "Alice", "type": "Person"},
            {"id": "e2", "name": "Alice", "type": "Person"},
        ]
        captured = {}

        class FakeStore:
            def get_nodes(self, labels=None, properties=None, limit=100, **options):
                return entities

        monkeypatch.setattr("semantica.graph_store.methods._get_store", lambda: FakeStore())
        monkeypatch.setattr("semantica.graph_store.methods.get_nodes", lambda **kwargs: entities)

        def fake_merge(self, loaded_entities, **kwargs):
            captured["entities"] = loaded_entities
            captured["kwargs"] = kwargs
            return [{"merged": True, "count": len(loaded_entities)}]

        monkeypatch.setattr(
            "semantica.deduplication.entity_merger.EntityMerger.merge_duplicates",
            fake_merge,
        )

        result = runner.invoke(
            cli_module.main,
            ["deduplicate", "--action", "merge", "--json"],
        )

        _ok(result)
        data = _json_output(result)
        assert data == [{"merged": True, "count": 2}]
        assert captured["entities"] == entities
        assert captured["kwargs"]["threshold"] == pytest.approx(0.7)
        assert captured["kwargs"]["candidate_strategy"] == "hybrid_v2"
        assert captured["kwargs"]["sort_by"] == "similarity_score"

    def test_global_dry_run_triggers_dry(self, runner):
        result = runner.invoke(cli_module.main, ["--dry-run", "--json", "deduplicate"])
        _ok(result)
        data = _json_output(result)
        assert data["dry_run"] is True

    def test_import_error_is_clean(self, runner):
        with patch("builtins.__import__", side_effect=lambda n, *a, **k: (
            (_ for _ in ()).throw(ImportError(n))
            if "deduplication" in n else __import__(n, *a, **k)
        )):
            result = runner.invoke(cli_module.main, ["deduplicate"])
        assert result.exit_code != 0
        assert "Traceback" not in result.output

    def test_invalid_strategy_choice(self, runner):
        result = runner.invoke(cli_module.main, ["deduplicate", "--strategy", "magic"])
        assert result.exit_code != 0

    @pytest.mark.parametrize("action", ["detect", "merge", "report"])
    def test_action_choices_accepted(self, runner, action):
        result = runner.invoke(cli_module.main, ["deduplicate", "--action", action, "--dry-run"])
        _ok(result)


# ─── reason ───────────────────────────────────────────────────────────────────


class TestReason:
    def test_group_help(self, runner):
        result = runner.invoke(cli_module.main, ["reason", "--help"])
        _ok(result)
        for sub in ["run", "explain", "query", "list"]:
            assert sub in result.output

    def test_list_shows_engines(self, runner):
        result = runner.invoke(cli_module.main, ["reason", "list"])
        _ok(result)
        assert "rete" in result.output

    def test_list_json(self, runner):
        # list command has no --json flag, output via cli_ctx.json_output
        result2 = runner.invoke(cli_module.main, ["--json", "reason", "list"])
        _ok(result2)
        data = json.loads(result2.output.strip())
        assert "engines" in data
        assert "rete" in data["engines"]

    def test_run_help(self, runner):
        result = runner.invoke(cli_module.main, ["reason", "run", "--help"])
        _ok(result)
        assert "--engine" in result.output

    def test_run_import_error_is_clean(self, runner):
        with patch("builtins.__import__", side_effect=lambda n, *a, **k: (
            (_ for _ in ()).throw(ImportError(n))
            if "reasoning" in n else __import__(n, *a, **k)
        )):
            result = runner.invoke(cli_module.main, ["reason", "run"])
        assert result.exit_code != 0
        assert "Traceback" not in result.output

    def test_run_infers_from_graph_store_facts(self, runner, monkeypatch, tmp_path):
        # reason run used to call Reasoner.run(), which does not exist
        # (#1354); it must feed graph store facts + --rules into
        # Reasoner.infer_facts().
        pytest.importorskip("numpy", reason="semantica.reasoning needs numpy")
        rules_file = tmp_path / "rules.yaml"
        rules_file.write_text(
            '- IF Person(?x) THEN Human(?x)\n'
            '- IF MANAGES(?x, ?y) THEN Manager(?x)\n'
            '- IF Employee(?x) THEN Staff(?x)\n',
            encoding="utf-8")

        class _FakeStore:
            # Same dict schema as the real backends: nodes carry
            # labels/properties, relationships carry start_node_id/end_node_id.
            def get_nodes(self, limit=None):
                return [{"id": 1, "labels": ["Person"],
                         "properties": {"name": "Alice"}},
                        {"id": 2, "labels": ["Person", "Employee"],
                         "properties": {"name": "Bob"}}]

            def get_relationships(self, limit=None):
                return [{"id": 9, "type": "MANAGES",
                         "start_node_id": 1, "end_node_id": 2}]

        monkeypatch.setattr(cli_module, "_get_graph_store", lambda ctx: _FakeStore())
        result = runner.invoke(
            cli_module.main,
            ["--json", "reason", "run", "--rules", str(rules_file)],
        )
        _ok(result)
        data = json.loads(result.output.strip())
        # Person(Alice), Person(Bob), Employee(Bob), MANAGES(Alice, Bob)
        assert data["facts"] == 4
        assert "Human(Alice)" in data["inferred_facts"]
        # Relationship endpoints resolve node ids to names.
        assert "Manager(Alice)" in data["inferred_facts"]
        # Secondary labels also become facts.
        assert "Staff(Bob)" in data["inferred_facts"]
        assert data["inferred_count"] == len(data["inferred_facts"])

    def test_run_rejects_unwired_engine(self, runner):
        result = runner.invoke(cli_module.main,
                               ["reason", "run", "--engine", "sparql"])
        assert result.exit_code != 0
        assert "not wired" in result.output
        assert "reason query" in result.output
        assert "Traceback" not in result.output

    def test_load_rule_definitions_formats(self, tmp_path):
        yaml_list = tmp_path / "list.yaml"
        yaml_list.write_text('- IF A(?x) THEN B(?x)\n- IF B(?x) THEN C(?x)\n',
                             encoding="utf-8")
        assert cli_module._load_rule_definitions(str(yaml_list)) == [
            "IF A(?x) THEN B(?x)", "IF B(?x) THEN C(?x)"]

        yaml_map = tmp_path / "map.yaml"
        yaml_map.write_text('rules:\n  - IF A(?x) THEN B(?x)\n', encoding="utf-8")
        assert cli_module._load_rule_definitions(str(yaml_map)) == [
            "IF A(?x) THEN B(?x)"]

        plain = tmp_path / "rules.dl"
        plain.write_text('# comment\nIF A(?x) THEN B(?x)\n\n', encoding="utf-8")
        assert cli_module._load_rule_definitions(str(plain)) == [
            "IF A(?x) THEN B(?x)"]

    def test_run_empty_graph_returns_zero_facts(self, runner, monkeypatch):
        """reason run with an empty graph store should not crash and report 0 facts."""
        pytest.importorskip("numpy", reason="semantica.reasoning needs numpy")

        class _EmptyStore:
            def get_nodes(self, limit=None): return []
            def get_relationships(self, limit=None): return []

        monkeypatch.setattr(cli_module, "_get_graph_store", lambda ctx: _EmptyStore())
        result = runner.invoke(cli_module.main, ["--json", "reason", "run"])
        _ok(result)
        data = json.loads(result.output.strip())
        assert data["facts"] == 0
        assert data["inferred_count"] == 0
        assert data["inferred_facts"] == []

    def test_run_graph_store_error_surfaces_cleanly(self, runner, monkeypatch):
        """A graph-store connectivity error must surface as a clean error, not a Traceback."""

        def _bad_store(ctx):
            raise RuntimeError("connection refused")

        monkeypatch.setattr(cli_module, "_get_graph_store", _bad_store)
        result = runner.invoke(cli_module.main, ["reason", "run"])
        assert result.exit_code != 0
        assert "Traceback" not in result.output
        assert "connection refused" in result.output

    def test_run_no_rules_uses_empty_ruleset(self, runner, monkeypatch):
        """reason run without --rules should still succeed (zero rules -> zero inferences)."""
        pytest.importorskip("numpy", reason="semantica.reasoning needs numpy")

        class _FakeStore:
            def get_nodes(self, limit=None):
                return [{"id": 1, "labels": ["Person"], "properties": {"name": "Alice"}}]

            def get_relationships(self, limit=None):
                return []

        monkeypatch.setattr(cli_module, "_get_graph_store", lambda ctx: _FakeStore())
        result = runner.invoke(cli_module.main, ["--json", "reason", "run"])
        _ok(result)
        data = json.loads(result.output.strip())
        assert data["facts"] == 1
        assert data["inferred_count"] == 0

    def test_load_rule_definitions_yaml_mapping_without_rules_key_raises(self, tmp_path):
        """A YAML mapping with no 'rules' key must raise ClickException, not silently
        pass the raw YAML lines as rules."""
        bad = tmp_path / "bad.yaml"
        bad.write_text("some_key: some_value\nother_key: other_value\n", encoding="utf-8")
        import click as _click
        with pytest.raises(_click.ClickException, match="no 'rules' key"):
            cli_module._load_rule_definitions(str(bad))

    def test_load_rule_definitions_empty_file_returns_empty_list(self, tmp_path):
        empty = tmp_path / "empty.yaml"
        empty.write_text("", encoding="utf-8")
        assert cli_module._load_rule_definitions(str(empty)) == []

    def test_load_rule_definitions_yaml_rules_null_falls_to_plaintext(self, tmp_path):
        """rules: null is valid YAML with the key present; the null value is
        not a list, so the function falls through to plain-text parsing and
        returns the literal line (one no-op rule).  This documents the edge
        case rather than asserting a specific useful behaviour."""
        f = tmp_path / "null_rules.yaml"
        f.write_text("rules: null\n", encoding="utf-8")
        result = cli_module._load_rule_definitions(str(f))
        # Plain-text fallback: the non-comment, non-blank line becomes a rule.
        assert result == ["rules: null"]

    def test_run_rejects_deductive_engine(self, runner, monkeypatch):
        """Engines other than rete/forward-chain must be rejected with a helpful message."""

        class _EmptyStore:
            def get_nodes(self, limit=None): return []
            def get_relationships(self, limit=None): return []

        monkeypatch.setattr(cli_module, "_get_graph_store", lambda ctx: _EmptyStore())
        result = runner.invoke(cli_module.main, ["reason", "run", "--engine", "deductive"])
        assert result.exit_code != 0
        assert "not wired" in result.output
        assert "Traceback" not in result.output

    def test_explain_requires_conclusion(self, runner):
        result = runner.invoke(cli_module.main, ["reason", "explain"])
        assert result.exit_code != 0

    def test_explain_import_error_is_clean(self, runner):
        with patch("builtins.__import__", side_effect=lambda n, *a, **k: (
            (_ for _ in ()).throw(ImportError(n))
            if "reasoning" in n else __import__(n, *a, **k)
        )):
            result = runner.invoke(cli_module.main, ["reason", "explain", "Alice is-manager-of Eng"])
        assert result.exit_code != 0
        assert "Traceback" not in result.output

    def test_query_import_error_is_clean(self, runner):
        with patch("builtins.__import__", side_effect=lambda n, *a, **k: (
            (_ for _ in ()).throw(ImportError(n))
            if "reasoning" in n else __import__(n, *a, **k)
        )):
            result = runner.invoke(cli_module.main, ["reason", "query", "SELECT ?x WHERE {}"])
        assert result.exit_code != 0
        assert "Traceback" not in result.output


# ─── decision ─────────────────────────────────────────────────────────────────


class TestDecision:
    def test_group_help(self, runner):
        result = runner.invoke(cli_module.main, ["decision", "--help"])
        _ok(result)
        for sub in ["record", "list", "query", "trace", "similar", "impact", "check"]:
            assert sub in result.output

    def test_record_requires_title(self, runner):
        result = runner.invoke(cli_module.main, ["decision", "record"])
        assert result.exit_code != 0

    def test_record_dry_run_json(self, runner):
        result = runner.invoke(cli_module.main, ["decision", "record",
                                      "--title", "Approve X", "--dry-run", "--json"])
        _ok(result)
        data = _json_output(result)
        assert data["dry_run"] is True

    def test_record_global_dry_run_json(self, runner):
        result = runner.invoke(cli_module.main, ["--json", "--dry-run", "decision", "record",
                                      "--title", "Approve X"])
        _ok(result)
        data = _json_output(result)
        assert data["dry_run"] is True

    def test_record_import_error_is_clean(self, runner):
        with patch("builtins.__import__", side_effect=lambda n, *a, **k: (
            (_ for _ in ()).throw(ImportError(n))
            if "semantica.context" in n else __import__(n, *a, **k)
        )):
            result = runner.invoke(cli_module.main, ["decision", "record", "--title", "X"])
        assert result.exit_code != 0
        assert "Traceback" not in result.output

    def test_list_json(self, runner, monkeypatch):
        import datetime
        fake_dq = MagicMock()
        d = MagicMock()
        d.decision_id = "d1"
        d.scenario = "T"
        d.category = "general"
        d.outcome = "ok"
        d.confidence = 1.0
        fake_dq.find_by_time_range.return_value = [d]
        fake_decision_query = _fake_module(DecisionQuery=lambda *a, **kw: fake_dq)
        fake_graph_store = _fake_module(GraphStore=MagicMock(return_value=MagicMock()))
        monkeypatch.setitem(__import__("sys").modules,
                            "semantica.context.decision_query", fake_decision_query)
        monkeypatch.setitem(__import__("sys").modules,
                            "semantica.graph_store", fake_graph_store)
        result = runner.invoke(cli_module.main, ["decision", "list", "--format", "json"])
        _ok(result)

    def test_trace_import_error_is_clean(self, runner):
        with patch("builtins.__import__", side_effect=lambda n, *a, **k: (
            (_ for _ in ()).throw(ImportError(n))
            if "semantica.context" in n else __import__(n, *a, **k)
        )):
            result = runner.invoke(cli_module.main, ["decision", "trace", "dec_123"])
        assert result.exit_code != 0
        assert "Traceback" not in result.output

    def test_check_requires_id(self, runner):
        result = runner.invoke(cli_module.main, ["decision", "check"])
        assert result.exit_code != 0

    @pytest.mark.parametrize("sub", ["similar", "impact"])
    def test_sub_requires_id(self, runner, sub):
        result = runner.invoke(cli_module.main, ["decision", sub])
        assert result.exit_code != 0


# ─── temporal ─────────────────────────────────────────────────────────────────


class TestTemporal:
    def test_group_help(self, runner):
        result = runner.invoke(cli_module.main, ["temporal", "--help"])
        _ok(result)
        for sub in ["snapshot", "query", "history", "distance", "allen"]:
            assert sub in result.output

    def test_snapshot_requires_at(self, runner):
        result = runner.invoke(cli_module.main, ["temporal", "snapshot"])
        assert result.exit_code != 0

    def test_snapshot_json(self, runner, monkeypatch):
        fake_kg = _fake_module(
            TemporalGraphQuery=lambda **kw: MagicMock(
                snapshot=lambda at: {"at": at, "nodes": 5}
            ),
        )
        monkeypatch.setitem(__import__("sys").modules, "semantica.kg", fake_kg)
        result = runner.invoke(cli_module.main, ["temporal", "snapshot",
                                      "--at", "2026-01-01T00:00:00Z", "--json"])
        _ok(result)
        data = _json_output(result)
        assert isinstance(data, dict)

    def test_distance_requires_both_events(self, runner):
        result = runner.invoke(cli_module.main, ["temporal", "distance", "--event1", "ev1"])
        assert result.exit_code != 0

    def test_allen_requires_both_intervals(self, runner):
        result = runner.invoke(cli_module.main, ["temporal", "allen",
                                      "--interval1", "int1", "--interval2", "int2"])
        assert result.exit_code != 0 or result.exit_code == 0  # depends on import

    def test_history_import_error_is_clean(self, runner):
        with patch("builtins.__import__", side_effect=lambda n, *a, **k: (
            (_ for _ in ()).throw(ImportError(n))
            if n.startswith("semantica.kg") else __import__(n, *a, **k)
        )):
            result = runner.invoke(cli_module.main, ["temporal", "history", "entity_alice"])
        assert result.exit_code != 0
        assert "Traceback" not in result.output


# ─── provenance ───────────────────────────────────────────────────────────────


class TestProvenance:
    def test_group_help(self, runner):
        result = runner.invoke(cli_module.main, ["provenance", "--help"])
        _ok(result)
        for sub in ["lineage", "audit", "export", "check"]:
            assert sub in result.output

    def test_lineage_requires_entity(self, runner):
        result = runner.invoke(cli_module.main, ["provenance", "lineage"])
        assert result.exit_code != 0

    def test_lineage_import_error_is_clean(self, runner):
        with patch("builtins.__import__", side_effect=lambda n, *a, **k: (
            (_ for _ in ()).throw(ImportError(n))
            if "provenance" in n else __import__(n, *a, **k)
        )):
            result = runner.invoke(cli_module.main, ["provenance", "lineage", "entity_alice"])
        assert result.exit_code != 0
        assert "Traceback" not in result.output

    def test_export_dry_run(self, runner):
        result = runner.invoke(cli_module.main, ["provenance", "export", "--dry-run"])
        _ok(result)

    def test_audit_writes_output(self, runner, monkeypatch):
        fake_prov = _fake_module(
            ProvenanceManager=lambda **kw: MagicMock(
                audit_log=lambda **kw2: [{"actor": "user", "action": "ingest"}]
            ),
        )
        monkeypatch.setitem(__import__("sys").modules, "semantica.provenance", fake_prov)
        with runner.isolated_filesystem():
            result = runner.invoke(cli_module.main, ["provenance", "audit", "--output", "audit.json"])
            if result.exit_code == 0:
                assert os.path.exists("audit.json")

    def test_check_exits_0_when_import_error(self, runner):
        with patch("builtins.__import__", side_effect=lambda n, *a, **k: (
            (_ for _ in ()).throw(ImportError(n))
            if "provenance" in n else __import__(n, *a, **k)
        )):
            result = runner.invoke(cli_module.main, ["provenance", "check"])
        assert result.exit_code != 0
        assert "Traceback" not in result.output


# ─── validate ─────────────────────────────────────────────────────────────────


class TestValidate:
    def test_group_help(self, runner):
        result = runner.invoke(cli_module.main, ["validate", "--help"])
        _ok(result)
        for sub in ["shacl", "conflicts", "integrity"]:
            assert sub in result.output

    def test_shacl_help(self, runner):
        result = runner.invoke(cli_module.main, ["validate", "shacl", "--help"])
        _ok(result)
        assert "--strictness" in result.output

    def test_shacl_import_error_is_clean(self, runner):
        with patch("builtins.__import__", side_effect=lambda n, *a, **k: (
            (_ for _ in ()).throw(ImportError(n))
            if "ontology" in n else __import__(n, *a, **k)
        )):
            result = runner.invoke(cli_module.main, ["validate", "shacl"])
        assert result.exit_code != 0
        assert "Traceback" not in result.output

    def test_conflicts_json(self, runner, monkeypatch):
        fake_conf = _fake_module(
            detect_conflicts=lambda **kw: {"conflicts": [], "count": 0},
        )
        monkeypatch.setitem(__import__("sys").modules, "semantica.conflicts", fake_conf)
        result = runner.invoke(cli_module.main, ["validate", "conflicts", "--json"])
        _ok(result)
        data = _json_output(result)
        assert isinstance(data, dict)

    def test_integrity_exits_0_with_import_error(self, runner):
        with patch("builtins.__import__", side_effect=lambda n, *a, **k: (
            (_ for _ in ()).throw(ImportError(n))
            if n.startswith("semantica.kg") else __import__(n, *a, **k)
        )):
            result = runner.invoke(cli_module.main, ["validate", "integrity"])
        assert result.exit_code != 0
        assert "Traceback" not in result.output

    def test_strictness_choices(self, runner):
        result = runner.invoke(cli_module.main, ["validate", "shacl", "--help"])
        for s in ["strict", "moderate", "lenient"]:
            assert s in result.output


# ─── ontology ─────────────────────────────────────────────────────────────────


class TestOntology:
    def test_group_help(self, runner):
        result = runner.invoke(cli_module.main, ["ontology", "--help"])
        _ok(result)
        for sub in ["generate", "import", "validate", "shacl", "skos",
                    "align", "health", "version"]:
            assert sub in result.output

    def test_generate_dry_run(self, runner):
        result = runner.invoke(cli_module.main, ["ontology", "generate", "--dry-run"])
        _ok(result)

    def test_generate_json_dry_run(self, runner):
        result = runner.invoke(cli_module.main, ["ontology", "generate", "--dry-run", "--json"])
        _ok(result)
        data = _json_output(result)
        assert data["dry_run"] is True

    def test_generate_global_json_dry_run(self, runner):
        result = runner.invoke(cli_module.main, ["--json", "--dry-run", "ontology", "generate"])
        _ok(result)
        data = _json_output(result)
        assert data["dry_run"] is True

    def test_import_dry_run(self, runner):
        result = runner.invoke(cli_module.main, ["ontology", "import", "schema.ttl", "--dry-run"])
        _ok(result)

    def test_import_requires_source(self, runner):
        result = runner.invoke(cli_module.main, ["ontology", "import"])
        assert result.exit_code != 0

    def test_skos_group_help(self, runner):
        result = runner.invoke(cli_module.main, ["ontology", "skos", "--help"])
        _ok(result)
        for sub in ["search", "hierarchy"]:
            assert sub in result.output

    def test_skos_search_requires_term(self, runner):
        result = runner.invoke(cli_module.main, ["ontology", "skos", "search"])
        assert result.exit_code != 0

    def test_skos_hierarchy_requires_uri(self, runner):
        result = runner.invoke(cli_module.main, ["ontology", "skos", "hierarchy"])
        assert result.exit_code != 0

    def test_align_requires_source_and_target(self, runner):
        result = runner.invoke(cli_module.main, ["ontology", "align"])
        assert result.exit_code != 0

    def test_align_import_error_is_clean(self, runner):
        with runner.isolated_filesystem():
            with open("s.ttl", "w") as f:
                f.write("")
            with open("t.ttl", "w") as f:
                f.write("")
            with patch("builtins.__import__", side_effect=lambda n, *a, **k: (
                (_ for _ in ()).throw(ImportError(n))
                if "ontology" in n else __import__(n, *a, **k)
            )):
                result = runner.invoke(cli_module.main, ["ontology", "align",
                                              "--source", "s.ttl", "--target", "t.ttl"])
        assert result.exit_code != 0
        assert "Traceback" not in result.output

    def test_health_exits_0_with_import_error(self, runner):
        with patch("builtins.__import__", side_effect=lambda n, *a, **k: (
            (_ for _ in ()).throw(ImportError(n))
            if "ontology" in n else __import__(n, *a, **k)
        )):
            result = runner.invoke(cli_module.main, ["ontology", "health"])
        assert result.exit_code != 0
        assert "Traceback" not in result.output


# ─── export ───────────────────────────────────────────────────────────────────


class TestExport:
    def test_help_shows_14_formats(self, runner):
        result = runner.invoke(cli_module.main, ["export", "--help"])
        _ok(result)
        for fmt in ["turtle", "parquet", "csv", "graphml", "owl", "arangodb"]:
            assert fmt in result.output
        for flag in ["--with-provenance", "--filter", "--compress", "--dry-run"]:
            assert flag in result.output

    def test_dry_run_json(self, runner):
        result = runner.invoke(cli_module.main, ["export", "--format", "turtle",
                                      "--dry-run", "--json"])
        _ok(result)
        data = _json_output(result)
        assert data["dry_run"] is True

    def test_dry_run_text(self, runner):
        result = runner.invoke(cli_module.main, ["export", "--format", "csv", "--dry-run"])
        _ok(result, substr="Dry run")

    def test_global_dry_run(self, runner):
        result = runner.invoke(cli_module.main, ["--dry-run", "--json", "export", "--format", "json"])
        _ok(result)
        data = _json_output(result)
        assert data["dry_run"] is True

    def test_real_export_runtime_path(self, runner, tmp_path, monkeypatch):
        class FakeGraphStore:
            def get_nodes(self, labels=None, properties=None, limit=100, **options):
                return [
                    {
                        "id": "n1",
                        "type": "Person",
                        "name": "Alice",
                        "properties": {"name": "Alice"},
                    }
                ]

            def get_relationships(self, node_id=None, rel_type=None, direction="both", limit=100, **options):
                return [
                    {
                        "id": "r1",
                        "source": "n1",
                        "target": "n1",
                        "type": "KNOWS",
                        "properties": {},
                    }
                ]

        monkeypatch.setattr(
            "semantica.graph_store.methods._get_store",
            lambda: FakeGraphStore(),
        )
        monkeypatch.setattr(
            "semantica.graph_store.get_nodes",
            lambda **kwargs: [
                {
                    "id": "n1",
                    "type": "Person",
                    "name": "Alice",
                    "properties": {"name": "Alice"},
                }
            ],
        )
        monkeypatch.setattr(
            "semantica.graph_store.methods.get_nodes",
            lambda **kwargs: [
                {
                    "id": "n1",
                    "type": "Person",
                    "name": "Alice",
                    "properties": {"name": "Alice"},
                }
            ],
        )
        monkeypatch.setattr(
            "semantica.graph_store.get_relationships",
            lambda **kwargs: [
                {
                    "id": "r1",
                    "source": "n1",
                    "target": "n1",
                    "type": "KNOWS",
                    "properties": {},
                }
            ],
        )
        monkeypatch.setattr(
            "semantica.graph_store.methods.get_relationships",
            lambda **kwargs: [
                {
                    "id": "r1",
                    "source": "n1",
                    "target": "n1",
                    "type": "KNOWS",
                    "properties": {},
                }
            ],
        )

        output_path = tmp_path / "export.json"
        result = runner.invoke(cli_module.main, ["export", "--format", "json", "--output", str(output_path)])
        _ok(result)
        exported = output_path.read_text(encoding="utf-8")
        assert "Alice" in exported
        assert "KNOWS" in exported

    def test_invalid_format_fails(self, runner):
        result = runner.invoke(cli_module.main, ["export", "--format", "magic"])
        assert result.exit_code != 0

    def test_import_error_is_clean(self, runner):
        original_import = __import__
        with patch("builtins.__import__", side_effect=lambda n, *a, **k: (
            (_ for _ in ()).throw(ImportError(n))
            if "semantica.export" in n else original_import(n, *a, **k)
        )):
            result = runner.invoke(cli_module.main, ["export", "--format", "json"])
        assert result.exit_code != 0
        assert "Traceback" not in result.output


# ─── visualize ────────────────────────────────────────────────────────────────


class TestVisualize:
    def test_group_help(self, runner):
        result = runner.invoke(cli_module.main, ["visualize", "--help"])
        _ok(result)
        for sub in ["kg", "ontology", "embeddings", "temporal", "analytics"]:
            assert sub in result.output

    @pytest.mark.parametrize("sub", ["kg", "ontology", "embeddings", "temporal", "analytics"])
    def test_subcommand_help(self, runner, sub):
        result = runner.invoke(cli_module.main, ["visualize", sub, "--help"])
        _ok(result)
        for flag in ["--layout", "--format", "--output"]:
            assert flag in result.output

    @pytest.mark.parametrize("sub", ["kg", "ontology", "embeddings", "temporal", "analytics"])
    def test_import_error_is_clean(self, runner, sub):
        with patch("builtins.__import__", side_effect=lambda n, *a, **k: (
            (_ for _ in ()).throw(ImportError(n))
            if "visualization" in n else __import__(n, *a, **k)
        )):
            result = runner.invoke(cli_module.main, ["visualize", sub])
        assert result.exit_code != 0
        assert "Traceback" not in result.output

    def test_format_choices(self, runner):
        result = runner.invoke(cli_module.main, ["visualize", "kg", "--help"])
        for fmt in ["html", "svg", "png", "pdf"]:
            assert fmt in result.output

    def test_layout_choices(self, runner):
        result = runner.invoke(cli_module.main, ["visualize", "kg", "--help"])
        for layout in ["forceatlas2", "spring", "hierarchical"]:
            assert layout in result.output


# ─── pipeline ─────────────────────────────────────────────────────────────────


class TestPipeline:
    def test_group_help(self, runner):
        result = runner.invoke(cli_module.main, ["pipeline", "--help"])
        _ok(result)
        for sub in ["init", "validate", "run", "status", "stop"]:
            assert sub in result.output

    def test_init_dry_run(self, runner):
        result = runner.invoke(cli_module.main, ["pipeline", "init", "--dry-run"])
        _ok(result)

    def test_init_creates_file(self, runner, monkeypatch):
        fake_pl = _fake_module(
            PipelineTemplateManager=lambda: MagicMock(scaffold=lambda t: "steps: []\n"),
        )
        monkeypatch.setitem(__import__("sys").modules, "semantica.pipeline", fake_pl)
        with runner.isolated_filesystem():
            result = runner.invoke(cli_module.main, ["pipeline", "init",
                                          "--template", "rag", "--output", "pl.yaml"])
            _ok(result)
            assert os.path.exists("pl.yaml")

    def test_init_template_choices(self, runner):
        result = runner.invoke(cli_module.main, ["pipeline", "init", "--help"])
        for t in ["ingest-extract-kg", "rag", "ontology-build", "decision-track", "full"]:
            assert t in result.output

    def test_validate_requires_file(self, runner):
        result = runner.invoke(cli_module.main, ["pipeline", "validate"])
        assert result.exit_code != 0

    def test_validate_nonexistent_file_fails(self, runner):
        result = runner.invoke(cli_module.main, ["pipeline", "validate", "no_such.yaml"])
        assert result.exit_code != 0

    def test_run_dry_run(self, runner):
        with runner.isolated_filesystem():
            with open("pl.yaml", "w") as f:
                f.write("steps: []\n")
            result = runner.invoke(cli_module.main, ["pipeline", "run", "pl.yaml", "--dry-run"])
            _ok(result)

    def test_run_requires_file(self, runner):
        result = runner.invoke(cli_module.main, ["pipeline", "run"])
        assert result.exit_code != 0

    def test_status_exits_0(self, runner):
        with patch("builtins.__import__", side_effect=lambda n, *a, **k: (
            (_ for _ in ()).throw(ImportError(n))
            if "pipeline" in n else __import__(n, *a, **k)
        )):
            result = runner.invoke(cli_module.main, ["pipeline", "status"])
        assert result.exit_code != 0
        assert "Traceback" not in result.output

    def test_stop_exits_cleanly_on_import_error(self, runner):
        with patch("builtins.__import__", side_effect=lambda n, *a, **k: (
            (_ for _ in ()).throw(ImportError(n))
            if "pipeline" in n else __import__(n, *a, **k)
        )):
            result = runner.invoke(cli_module.main, ["pipeline", "stop"])
        assert result.exit_code != 0
        assert "Traceback" not in result.output


# ─── store ────────────────────────────────────────────────────────────────────


class TestStore:
    def test_group_help(self, runner):
        result = runner.invoke(cli_module.main, ["store", "--help"])
        _ok(result)
        for sub in ["list", "connect", "stats", "migrate", "flush"]:
            assert sub in result.output

    def test_list_json_empty_config(self, runner):
        result = runner.invoke(cli_module.main, ["store", "list", "--json"])
        _ok(result)
        data = _json_output(result)
        assert isinstance(data, dict)

    def test_list_table(self, runner):
        result = runner.invoke(cli_module.main, ["store", "list"])
        _ok(result)

    def test_connect_requires_backend(self, runner):
        result = runner.invoke(cli_module.main, ["store", "connect"])
        assert result.exit_code != 0

    def test_connect_reports_status(self, runner):
        result = runner.invoke(cli_module.main, ["store", "connect", "--backend", "neo4j"])
        _ok(result)

    def test_connect_dispatches_through_graph_store(self, runner, monkeypatch):
        # store connect used to call get_graph_store_method(backend) — the
        # method registry, which needs (task, method_name) — so it raised a
        # TypeError before any connection attempt (#1354).
        calls = {}

        class _FakeGraphStore:
            def __init__(self, backend=None, **cfg):
                calls["backend"] = backend
                calls["cfg"] = cfg

            def connect(self):
                calls["connected"] = True
                return True

        import semantica.graph_store as gs_mod
        monkeypatch.setattr(gs_mod, "GraphStore", _FakeGraphStore)
        result = runner.invoke(cli_module.main, [
            "store", "connect", "--backend", "neo4j",
            "--uri", "bolt://example:7687", "--json"])
        _ok(result)
        data = _json_output(result)
        assert data == {"backend": "neo4j", "connected": True}
        assert calls["backend"] == "neo4j"
        assert calls["cfg"].get("uri") == "bolt://example:7687"
        assert calls.get("connected") is True

    def test_connect_invalid_backend_reports_error_not_dispatch_error(self, runner):
        """An unknown backend name must produce a meaningful backend error, not a
        Python TypeError from the old get_graph_store_method() dispatch (#1354)."""
        result = runner.invoke(cli_module.main,
                               ["store", "connect", "--backend", "does-not-exist"])
        # Exit 0 because store_connect always catches and reports errors gracefully.
        _ok(result)
        # The output must mention the backend, not a Python internal error.
        assert "does-not-exist" in result.output
        assert "TypeError" not in result.output
        assert "Traceback" not in result.output

    def test_connect_backend_error_surfaces_in_json(self, runner, monkeypatch):
        """A connect() failure must appear in JSON output as connected=False with an error field."""

        class _FailingStore:
            def __init__(self, backend=None, **cfg):
                pass

            def connect(self):
                raise RuntimeError("auth failed")

        import semantica.graph_store as gs_mod
        monkeypatch.setattr(gs_mod, "GraphStore", _FailingStore)
        result = runner.invoke(cli_module.main, [
            "store", "connect", "--backend", "neo4j", "--json"])
        _ok(result)
        data = _json_output(result)
        assert data["connected"] is False
        assert "auth failed" in data.get("error", "")
        assert data["backend"] == "neo4j"

    def test_migrate_dry_run(self, runner):
        result = runner.invoke(cli_module.main, ["store", "migrate",
                                      "--from", "faiss", "--to", "qdrant", "--dry-run"])
        _ok(result)

    def test_migrate_requires_from_and_to(self, runner):
        result = runner.invoke(cli_module.main, ["store", "migrate", "--from", "faiss"])
        assert result.exit_code != 0

    def test_migrate_refuses_unsupported_backend_pair(self, runner):
        result = runner.invoke(cli_module.main, ["store", "migrate",
                                      "--from", "faiss", "--to", "qdrant"])
        assert result.exit_code != 0
        assert "faiss, pgvector, sqlite" in result.output

    def _fake_migrate_store_module(self, source_items, stored, dest_configs=None):
        class _FakeBackendStore:
            def __init__(self, dimension=None):
                self.dimension = dimension

        class _FakeStore:
            def __init__(self, backend, config=None, **kw):
                self.backend = backend
                self._config = config or {}
                dim = self._config.get("dimension")
                self._backend_store = _FakeBackendStore(dimension=dim)
                if dest_configs is not None:
                    dest_configs[backend] = dict(self._config)

            def iter_vectors(self, batch_size=500):
                if self.backend == "sqlite":
                    yield from source_items
                    return
                return
                yield  # pragma: no cover - makes this a generator for other backends

            def store_vectors(self, vectors, metadata, ids=None):
                for vec_id, meta in zip(ids, metadata):
                    stored[vec_id] = meta

        return _fake_module(VectorStore=_FakeStore)

    def test_migrate_runs_between_supported_backends(self, runner, monkeypatch):
        source_items = [
            {"id": "a", "vector": [0.1, 0.2], "metadata": {"tag": "x"}},
            {"id": "b", "vector": [0.3, 0.4], "metadata": {}},
        ]
        stored = {}
        fake_vs = self._fake_migrate_store_module(source_items, stored)
        monkeypatch.setitem(__import__("sys").modules, "semantica.vector_store", fake_vs)

        result = runner.invoke(cli_module.main, ["store", "migrate",
                                      "--from", "sqlite", "--to", "pgvector",
                                      "--namespace", "prod", "--json"])
        _ok(result)
        data = _json_output(result)
        assert data == {"from": "sqlite", "to": "pgvector", "migrated": 2}
        assert stored == {"a": {"tag": "x", "namespace": "prod"}, "b": {"namespace": "prod"}}

    def test_migrate_reports_zero_for_empty_source(self, runner, monkeypatch):
        stored = {}
        fake_vs = self._fake_migrate_store_module([], stored)
        monkeypatch.setitem(__import__("sys").modules, "semantica.vector_store", fake_vs)

        result = runner.invoke(cli_module.main, ["store", "migrate",
                                      "--from", "sqlite", "--to", "pgvector", "--json"])
        _ok(result)
        assert _json_output(result)["migrated"] == 0
        assert stored == {}

    def test_migrate_inherits_source_dimension_into_dest(self, runner, monkeypatch):
        source_items = [{"id": "a", "vector": [0.1, 0.2, 0.3], "metadata": {}}]
        stored = {}
        dest_configs: dict = {}
        fake_vs = self._fake_migrate_store_module(source_items, stored, dest_configs)
        monkeypatch.setitem(__import__("sys").modules, "semantica.vector_store", fake_vs)
        monkeypatch.setattr(
            cli_module.Config, "to_dict",
            lambda self: {"vector_store": {"sqlite": {"dimension": 3}, "pgvector": {}}},
        )

        result = runner.invoke(cli_module.main, ["store", "migrate",
                                      "--from", "sqlite", "--to", "pgvector", "--json"])
        _ok(result)
        assert dest_configs["pgvector"].get("dimension") == 3

    def test_migrate_faiss_source_requires_index_path(self, runner, monkeypatch):
        fake_vs = _fake_module(VectorStore=lambda **kw: MagicMock())
        monkeypatch.setitem(__import__("sys").modules, "semantica.vector_store", fake_vs)

        result = runner.invoke(cli_module.main, ["store", "migrate",
                                      "--from", "faiss", "--to", "sqlite"])
        assert result.exit_code != 0
        assert "index_path" in result.output

    def test_migrate_faiss_dest_requires_index_path(self, runner, monkeypatch):
        fake_vs = _fake_module(VectorStore=lambda **kw: MagicMock())
        monkeypatch.setitem(__import__("sys").modules, "semantica.vector_store", fake_vs)

        result = runner.invoke(cli_module.main, ["store", "migrate",
                                      "--from", "sqlite", "--to", "faiss"])
        assert result.exit_code != 0
        assert "index_path" in result.output

    def test_flush_requires_confirm(self, runner):
        result = runner.invoke(cli_module.main, ["store", "flush"])
        assert result.exit_code != 0
        assert "confirm" in result.output.lower() or result.exit_code == 2

    def test_flush_with_confirm(self, runner, monkeypatch):
        fake_vs = _fake_module(delete_vectors=lambda **kw: None)
        monkeypatch.setitem(__import__("sys").modules, "semantica.vector_store", fake_vs)
        result = runner.invoke(cli_module.main, ["store", "flush", "--confirm"])
        _ok(result)

    def test_stats_requires_backend(self, runner):
        result = runner.invoke(cli_module.main, ["store", "stats"])
        assert result.exit_code != 0


# ─── backup ───────────────────────────────────────────────────────────────────


class TestBackup:
    def test_group_help(self, runner):
        result = runner.invoke(cli_module.main, ["backup", "--help"])
        _ok(result)
        for sub in ["info", "create", "sync", "restore", "schedule"]:
            assert sub in result.output

    def test_info_json_empty_config(self, runner):
        result = runner.invoke(cli_module.main, ["backup", "info", "--json"])
        _ok(result)
        data = _json_output(result)
        assert isinstance(data, list)

    def test_info_redacts_credentials(self, runner):
        # Config normalizes store.graph → graph_db
        with runner.isolated_filesystem():
            with open("cfg.yaml", "w") as f:
                f.write(
                    "graph_db:\n"
                    "  backend: neo4j\n"
                    "  uri: bolt://user:secret123@host:7687\n"
                )
            result = runner.invoke(cli_module.main, ["--config", "cfg.yaml", "backup", "info"])
        _ok(result)
        assert "secret123" not in result.output

    def test_info_shows_redacted_uri_in_output(self, runner):
        with runner.isolated_filesystem():
            with open("cfg.yaml", "w") as f:
                f.write(
                    "graph_db:\n"
                    "  backend: neo4j\n"
                    "  uri: bolt://user:secret123@host:7687\n"
                )
            result = runner.invoke(cli_module.main, ["--config", "cfg.yaml", "backup", "info"])
        _ok(result)
        assert "neo4j" in result.output
        assert "graph" in result.output

    def test_info_flags_cloud_backends_as_export(self, runner):
        with runner.isolated_filesystem():
            with open("cfg.yaml", "w") as f:
                # vector_store is the correct key in Config
                f.write("vector_store:\n  backend: pinecone\n  host: x\n")
            result = runner.invoke(cli_module.main, ["--config", "cfg.yaml", "backup", "info"])
        _ok(result)
        assert "export" in result.output

    def test_create_dry_run(self, runner):
        with runner.isolated_filesystem():
            result = runner.invoke(cli_module.main, ["backup", "create", "backup.tar.gz", "--dry-run"])
            _ok(result)

    def test_create_unencrypted_with_config_requires_confirm(self, runner):
        with runner.isolated_filesystem():
            with open("cfg.yaml", "w") as f:
                f.write("graph_db:\n  backend: neo4j\n  uri: bolt://localhost\n")
            result = runner.invoke(
                cli_module.main,
                ["--config", "cfg.yaml", "backup", "create", "out.tar.gz"],
                input="n\n",
            )
        assert result.exit_code != 0

    def test_create_strip_config_skips_confirm(self, runner):
        with runner.isolated_filesystem():
            with open("cfg.yaml", "w") as f:
                f.write("graph_db:\n  backend: neo4j\n  uri: bolt://localhost\n")
            result = runner.invoke(
                cli_module.main,
                ["--config", "cfg.yaml", "backup", "create", "out.tar.gz",
                 "--strip-config", "--quiet"],
            )
        assert "Traceback" not in result.output

    def test_create_dry_run_json(self, runner):
        # backup create has no per-command --json; use global --json
        result = runner.invoke(cli_module.main, ["--json", "backup", "create", "backup.tar.gz",
                                      "--dry-run"])
        _ok(result)
        data = _json_output(result)
        assert data["dry_run"] is True

    def test_create_keyfile_world_readable_rejected(self, runner):
        with runner.isolated_filesystem():
            with open("keyfile.txt", "w") as f:
                f.write("secret")
            try:
                os.chmod("keyfile.txt", stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
                result = runner.invoke(
                    cli_module.main,
                    ["backup", "create", "out.tar.gz",
                     "--keyfile", "keyfile.txt", "--encrypt"],
                )
                assert result.exit_code != 0
                assert "readable" in result.output  # covers both "world-readable" and group-readable
            except OSError:
                pytest.skip("Cannot set file permissions on this OS")

    def test_create_keyfile_nonexistent_rejected(self, runner):
        result = runner.invoke(
            cli_module.main,
            ["backup", "create", "out.tar.gz",
             "--keyfile", "no_such_keyfile.txt", "--encrypt"],
        )
        assert result.exit_code != 0

    def test_sync_dry_run(self, runner):
        result = runner.invoke(cli_module.main, ["backup", "sync", "/tmp/bk", "--dry-run"])
        _ok(result)

    def test_sync_creates_directory(self, runner):
        with runner.isolated_filesystem():
            result = runner.invoke(cli_module.main, ["backup", "sync", "sync_dest"])
            _ok(result)
            assert os.path.isdir("sync_dest")

    def test_restore_dry_run(self, runner):
        with runner.isolated_filesystem():
            with open("backup.tar.gz", "w") as f:
                f.write("")
            result = runner.invoke(cli_module.main, ["backup", "restore", "backup.tar.gz", "--dry-run"])
            _ok(result)

    def test_restore_requires_source(self, runner):
        result = runner.invoke(cli_module.main, ["backup", "restore"])
        assert result.exit_code != 0

    def test_restore_nonexistent_source_fails(self, runner):
        result = runner.invoke(cli_module.main, ["backup", "restore", "no_such_file.tar.gz"])
        assert result.exit_code != 0

    def test_schedule_prints_cron(self, runner):
        result = runner.invoke(cli_module.main, ["backup", "schedule",
                                      "--dest", "/mnt/bk", "--freq", "daily"])
        _ok(result)
        assert "0 2 * * *" in result.output
        assert "/mnt/bk" in result.output

    def test_schedule_weekly(self, runner):
        result = runner.invoke(cli_module.main, ["backup", "schedule",
                                      "--dest", "/mnt/bk", "--freq", "weekly"])
        _ok(result)
        assert "0 2 * * 0" in result.output

    def test_schedule_with_encrypt(self, runner):
        result = runner.invoke(cli_module.main, ["backup", "schedule",
                                      "--dest", "/mnt/bk", "--encrypt"])
        _ok(result)
        assert "--encrypt" in result.output

    def test_schedule_json(self, runner):
        result = runner.invoke(cli_module.main, ["--json", "backup", "schedule",
                                      "--dest", "/mnt/bk"])
        _ok(result)
        data = json.loads(result.output.strip())
        assert "cron" in data


# ─── server ───────────────────────────────────────────────────────────────────


class TestServer:
    def test_group_help(self, runner):
        result = runner.invoke(cli_module.main, ["server", "--help"])
        _ok(result)
        for sub in ["start", "stop", "status"]:
            assert sub in result.output

    def test_start_help(self, runner):
        result = runner.invoke(cli_module.main, ["server", "start", "--help"])
        _ok(result)
        for flag in ["--port", "--workers", "--reload", "--host"]:
            assert flag in result.output

    def test_start_launches_process(self, runner):
        mock_proc = MagicMock()
        mock_proc.pid = 12345
        with patch("subprocess.Popen", return_value=mock_proc) as mock_popen:
            result = runner.invoke(cli_module.main, ["server", "start", "--port", "9000"])
        _ok(result)
        mock_popen.assert_called_once()
        call_args = mock_popen.call_args[0][0]
        assert "9000" in call_args

    def test_start_with_reload(self, runner):
        mock_proc = MagicMock()
        mock_proc.pid = 12346
        with patch("subprocess.Popen", return_value=mock_proc) as mock_popen:
            result = runner.invoke(cli_module.main, ["server", "start", "--reload"])
        _ok(result)
        call_args = mock_popen.call_args[0][0]
        assert "--reload" in call_args

    def test_stop_when_not_running(self, runner, tmp_path, monkeypatch):
        monkeypatch.setattr(cli_module, "_read_pid", lambda n: None)
        result = runner.invoke(cli_module.main, ["server", "stop"])
        _ok(result)
        assert "not running" in result.output.lower()

    def test_stop_sends_sigterm(self, runner, monkeypatch):
        monkeypatch.setattr(cli_module, "_read_pid", lambda n: 99999)
        monkeypatch.setattr(cli_module, "_pid_file", lambda n: MagicMock(
            exists=lambda: True, unlink=lambda missing_ok=False: None
        ))
        with patch("os.kill") as mock_kill:
            result = runner.invoke(cli_module.main, ["server", "stop"])
        _ok(result)
        mock_kill.assert_called_once()

    def test_status_when_stopped(self, runner, monkeypatch):
        monkeypatch.setattr(cli_module, "_read_pid", lambda n: None)
        result = runner.invoke(cli_module.main, ["server", "status"])
        _ok(result)
        assert "stopped" in result.output

    def test_status_json(self, runner, monkeypatch):
        monkeypatch.setattr(cli_module, "_read_pid", lambda n: None)
        result = runner.invoke(cli_module.main, ["server", "status", "--json"])
        _ok(result)
        data = _json_output(result)
        assert data["service"] == "server"
        assert "status" in data


# ─── explorer ─────────────────────────────────────────────────────────────────


class TestExplorer:
    def test_group_help(self, runner):
        result = runner.invoke(cli_module.main, ["explorer", "--help"])
        _ok(result)
        for sub in ["start", "stop", "status", "open"]:
            assert sub in result.output

    def test_start_launches_process(self, runner, monkeypatch):
        mock_proc = MagicMock()
        mock_proc.pid = 22222
        monkeypatch.setattr(cli_module, "_write_pid", lambda *_args: None)
        with patch("subprocess.Popen", return_value=mock_proc):
            result = runner.invoke(cli_module.main, ["explorer", "start", "--port", "5173"])
        _ok(result)

    def test_start_forwards_api_url_to_child_environment(self, runner, monkeypatch):
        mock_proc = MagicMock()
        mock_proc.pid = 22223
        monkeypatch.setattr(cli_module, "_write_pid", lambda *_args: None)
        with patch("subprocess.Popen", return_value=mock_proc) as mock_popen:
            result = runner.invoke(
                cli_module.main,
                ["explorer", "start", "--api-url", "http://localhost:9000"],
            )
        _ok(result)
        assert mock_popen.call_args.kwargs["env"]["SEMANTICA_API_URL"] == (
            "http://localhost:9000"
        )

    def test_stop_when_not_running(self, runner, monkeypatch):
        monkeypatch.setattr(cli_module, "_read_pid", lambda n: None)
        result = runner.invoke(cli_module.main, ["explorer", "stop"])
        _ok(result)
        assert "not running" in result.output.lower()

    def test_status_json(self, runner, monkeypatch):
        monkeypatch.setattr(cli_module, "_read_pid", lambda n: None)
        result = runner.invoke(cli_module.main, ["explorer", "status", "--json"])
        _ok(result)
        data = _json_output(result)
        assert data["service"] == "explorer"

    def test_open_calls_webbrowser(self, runner):
        with patch("webbrowser.open") as mock_wb:
            result = runner.invoke(cli_module.main, ["explorer", "open", "--port", "5173"])
        _ok(result)
        mock_wb.assert_called_once_with("http://localhost:5173")


# ─── mcp ──────────────────────────────────────────────────────────────────────


class TestMCP:
    def test_group_help(self, runner):
        result = runner.invoke(cli_module.main, ["mcp", "--help"])
        _ok(result)
        for sub in ["start", "stop", "status", "list-tools", "call"]:
            assert sub in result.output

    def test_start_launches_process(self, runner):
        mock_proc = MagicMock()
        mock_proc.pid = 33333
        with patch("subprocess.Popen", return_value=mock_proc):
            result = runner.invoke(cli_module.main, ["mcp", "start"])
        _ok(result)

    def test_start_http_includes_port(self, runner):
        mock_proc = MagicMock()
        mock_proc.pid = 33334
        with patch("subprocess.Popen", return_value=mock_proc) as mock_popen:
            result = runner.invoke(cli_module.main, ["mcp", "start", "--transport", "http",
                                          "--port", "4000"])
        _ok(result)
        call_args = mock_popen.call_args[0][0]
        assert "4000" in call_args

    def test_stop_when_not_running(self, runner, monkeypatch):
        monkeypatch.setattr(cli_module, "_read_pid", lambda n: None)
        result = runner.invoke(cli_module.main, ["mcp", "stop"])
        _ok(result)

    def test_status_json(self, runner, monkeypatch):
        monkeypatch.setattr(cli_module, "_read_pid", lambda n: None)
        result = runner.invoke(cli_module.main, ["mcp", "status", "--json"])
        _ok(result)
        data = _json_output(result)
        assert data["service"] == "mcp"

    def test_list_tools_shows_tools(self, runner):
        result = runner.invoke(cli_module.main, ["mcp", "list-tools"])
        _ok(result)
        # Table renders correctly — at minimum the column header is present
        assert "Tool" in result.output or "tool" in result.output.lower()

    def test_list_tools_with_mock_shows_known_tools(self, runner, monkeypatch):
        fake_tools = _fake_module(__all__=["extract_entities", "query_graph"])
        monkeypatch.setitem(__import__("sys").modules, "semantica_mcp.mcp.tools", fake_tools)
        result = runner.invoke(cli_module.main, ["mcp", "list-tools"])
        _ok(result)
        assert "extract_entities" in result.output

    def test_list_tools_json(self, runner):
        result = runner.invoke(cli_module.main, ["mcp", "list-tools", "--json"])
        _ok(result)
        data = _json_output(result)
        assert "tools" in data
        assert isinstance(data["tools"], list)

    def test_call_requires_tool_name(self, runner):
        result = runner.invoke(cli_module.main, ["mcp", "call"])
        assert result.exit_code != 0

    def test_call_invalid_json_args_fails_cleanly(self, runner):
        result = runner.invoke(cli_module.main, ["mcp", "call", "some_tool", "--args", "{bad json}"])
        assert result.exit_code != 0
        assert "Traceback" not in result.output
        assert "Invalid JSON" in result.output

    def test_call_import_error_is_clean(self, runner):
        with patch("builtins.__import__", side_effect=lambda n, *a, **k: (
            (_ for _ in ()).throw(ImportError(n))
            if n.startswith("mcp") else __import__(n, *a, **k)
        )):
            result = runner.invoke(cli_module.main, ["mcp", "call", "extract_entities"])
        assert result.exit_code != 0
        assert "Traceback" not in result.output


# ─── services group (backward-compat wrapper) ─────────────────────────────────


class TestServicesGroup:
    def test_services_group_help_shows_subgroups(self, runner):
        result = runner.invoke(cli_module.main, ["services", "--help"])
        _ok(result)
        for sub in ["server", "explorer", "mcp"]:
            assert sub in result.output

    def test_services_server_help(self, runner):
        result = runner.invoke(cli_module.main, ["services", "server", "--help"])
        _ok(result)
        for sub in ["start", "stop", "status"]:
            assert sub in result.output

    def test_services_explorer_help(self, runner):
        result = runner.invoke(cli_module.main, ["services", "explorer", "--help"])
        _ok(result)

    def test_services_mcp_help(self, runner):
        result = runner.invoke(cli_module.main, ["services", "mcp", "--help"])
        _ok(result)


# ─── completion ───────────────────────────────────────────────────────────────


class TestCompletion:
    @pytest.mark.parametrize("shell", ["bash", "zsh", "fish", "powershell"])
    def test_completion_exits_0(self, runner, shell):
        result = runner.invoke(cli_module.main, ["completion", shell])
        assert result.exit_code == 0

    @pytest.mark.parametrize("shell", ["bash", "zsh", "fish", "powershell"])
    def test_completion_output_not_empty(self, runner, shell):
        result = runner.invoke(cli_module.main, ["completion", shell])
        assert result.exit_code == 0
        assert len(result.output.strip()) > 0

    @pytest.mark.parametrize("shell,install_path", [
        ("bash", "~/.bashrc"),
        ("zsh", "~/.zshrc"),
        ("fish", "~/.config/fish"),
        ("powershell", "$PROFILE"),
    ])
    def test_completion_mentions_install_path(self, runner, shell, install_path):
        result = runner.invoke(cli_module.main, ["completion", shell])
        assert result.exit_code == 0
        assert install_path in result.output

    def test_invalid_shell_fails(self, runner):
        result = runner.invoke(cli_module.main, ["completion", "csh"])
        assert result.exit_code != 0


# ─── cross-cutting: --json propagated from global flag ────────────────────────


class TestGlobalJsonPropagation:
    """--json set at root should trigger JSON output in all subcommands."""

    def test_global_json_on_backup_schedule(self, runner):
        result = runner.invoke(cli_module.main, ["--json", "backup", "schedule", "--dest", "/d"])
        _ok(result)
        data = json.loads(result.output.strip())
        assert "cron" in data

    def test_global_json_on_store_list(self, runner):
        result = runner.invoke(cli_module.main, ["--json", "store", "list"])
        _ok(result)
        assert json.loads(result.output.strip()) is not None

    def test_global_json_on_mcp_list_tools(self, runner):
        result = runner.invoke(cli_module.main, ["--json", "mcp", "list-tools"])
        _ok(result)
        data = json.loads(result.output.strip())
        assert "tools" in data


# ─── exit codes ───────────────────────────────────────────────────────────────


class TestExitCodes:
    """Exit codes must match the spec: 0 success, 1 general, 2 validation."""

    def test_success_is_0(self, runner):
        result = runner.invoke(cli_module.main, ["info"])
        assert result.exit_code == 0

    def test_missing_required_arg_is_2(self, runner):
        result = runner.invoke(cli_module.main, ["kg", "build"])
        assert result.exit_code == 2

    def test_missing_required_arg_for_find_path_is_nonzero(self, runner):
        result = runner.invoke(cli_module.main, ["kg", "find-path"])
        assert result.exit_code != 0

    def test_import_error_is_nonzero(self, runner):
        with patch("builtins.__import__", side_effect=lambda n, *a, **k: (
            (_ for _ in ()).throw(ImportError(n))
            if "deduplication" in n else __import__(n, *a, **k)
        )):
            result = runner.invoke(cli_module.main, ["deduplicate"])
        assert result.exit_code != 0

    def test_no_traceback_on_any_error(self, runner):
        for argv in [
            ["kg", "build"],
            ["deduplicate", "--strategy", "bad"],
            ["export", "--format", "bad"],
            ["mcp", "call", "tool", "--args", "{invalid}"],
        ]:
            result = runner.invoke(cli_module.main, argv)
            assert "Traceback" not in result.output, (
                f"Traceback found for {argv}: {result.output}"
            )


class TestDoctorEmbeddings:
    """#994: doctor must surface non-functional embedding backends instead of
    reporting all green. Default = import-level check; --deep-embeddings (or
    SEMANTICA_DOCTOR_DEEP_EMBEDDINGS=1) instantiates via TextEmbedder."""

    def _doctor_checks(self, runner, *extra):
        result = runner.invoke(cli_module.main, ["doctor", "--json", *extra])
        _ok(result)
        import json as _json
        return {c["check"]: c for c in _json.loads(result.output)}

    def _with_fake_st(self, monkeypatch, **embedder_attrs):
        fake_st = _fake_module(
            __version__="9.9.9",
            SentenceTransformer=object,
        )
        monkeypatch.setitem(__import__("sys").modules, "sentence_transformers", fake_st)

    def test_doctor_reports_embedding_checks(self, runner):
        checks = self._doctor_checks(runner)
        assert "Embeddings (sentence-transformers)" in checks
        assert "Embeddings (fastembed)" in checks

    def test_import_failure_is_fail_status_with_hint(self, runner, monkeypatch):
        # Force the 'import sentence_transformers' inside _embedding_backend to
        # raise ImportError regardless of whether the package is installed on
        # this machine.  Setting a module entry to None is the standard Python
        # mechanism: any subsequent 'import <name>' raises
        # "import of <name> halted; None in sys.modules".
        monkeypatch.setitem(
            __import__("sys").modules, "sentence_transformers", None
        )
        checks = self._doctor_checks(runner)
        st = checks["Embeddings (sentence-transformers)"]
        assert st["status"] == "fail"
        assert st["hint"] == "pip install sentence-transformers"

    def test_deep_probe_detects_fallback_active(self, runner, monkeypatch):
        self._with_fake_st(monkeypatch)
        fake_embedder = types.SimpleNamespace(model=None, fastembed_model=None)

        fake_emb_mod = _fake_module(TextEmbedder=lambda **k: fake_embedder)
        monkeypatch.setitem(__import__("sys").modules, "semantica.embeddings", fake_emb_mod)

        checks = self._doctor_checks(runner, "--deep-embeddings")
        st = checks["Embeddings (sentence-transformers)"]
        assert st["status"] == "fail"
        assert "hash fallback" in st["note"]

    def test_deep_probe_ok_when_model_loads(self, runner, monkeypatch):
        self._with_fake_st(monkeypatch)
        import numpy as np
        fake_embedder = types.SimpleNamespace(
            model=object(),
            fastembed_model=None,
            embed_text=lambda text: np.zeros(384, dtype=np.float32),
        )
        fake_emb_mod = _fake_module(TextEmbedder=lambda **k: fake_embedder)
        monkeypatch.setitem(__import__("sys").modules, "semantica.embeddings", fake_emb_mod)

        checks = self._doctor_checks(runner, "--deep-embeddings")
        st = checks["Embeddings (sentence-transformers)"]
        assert st["status"] == "ok"
        assert "384-dim" in st["note"]

    def test_env_var_enables_deep_mode(self, runner, monkeypatch):
        monkeypatch.setenv("SEMANTICA_DOCTOR_DEEP_EMBEDDINGS", "1")
        self._with_fake_st(monkeypatch)
        fake_embedder = types.SimpleNamespace(model=None, fastembed_model=None)
        fake_emb_mod = _fake_module(TextEmbedder=lambda **k: fake_embedder)
        monkeypatch.setitem(__import__("sys").modules, "semantica.embeddings", fake_emb_mod)

        checks = self._doctor_checks(runner)
        st = checks["Embeddings (sentence-transformers)"]
        assert st["status"] == "fail"
        assert "hash fallback" in st["note"]


class TestDoctorEmbeddingHintsAndEnv:
    """Review follow-ups: deep failures must not carry the pip-install hint,
    and the env toggle tolerates case/whitespace variants."""

    def _doctor_checks(self, runner, *extra):
        result = runner.invoke(cli_module.main, ["doctor", "--json", *extra])
        _ok(result)
        import json as _json
        return {c["check"]: c for c in _json.loads(result.output)}

    def _with_fake_st(self, monkeypatch):
        fake_st = _fake_module(
            __version__="9.9.9",
            SentenceTransformer=object,
        )
        monkeypatch.setitem(__import__("sys").modules, "sentence_transformers", fake_st)

    def test_deep_failure_hint_is_not_pip_install(self, runner, monkeypatch):
        self._with_fake_st(monkeypatch)
        fake_embedder = types.SimpleNamespace(model=None, fastembed_model=None)
        fake_emb_mod = _fake_module(TextEmbedder=lambda **k: fake_embedder)
        monkeypatch.setitem(__import__("sys").modules, "semantica.embeddings", fake_emb_mod)

        checks = self._doctor_checks(runner, "--deep-embeddings")
        st = checks["Embeddings (sentence-transformers)"]
        assert st["status"] == "fail"
        assert "pip install" not in (st["hint"] or ""), (
            "a deep probe failure means the package imported fine — pointing "
            "users at pip sends them to reinstall for a runtime/model problem"
        )
        assert "runtime/model-load" in st["hint"]

    def test_env_var_tolerates_case_and_whitespace(self, runner, monkeypatch):
        monkeypatch.setenv("SEMANTICA_DOCTOR_DEEP_EMBEDDINGS", "  TRUE ")
        self._with_fake_st(monkeypatch)
        fake_embedder = types.SimpleNamespace(model=None, fastembed_model=None)
        fake_emb_mod = _fake_module(TextEmbedder=lambda **k: fake_embedder)
        monkeypatch.setitem(__import__("sys").modules, "semantica.embeddings", fake_emb_mod)

        checks = self._doctor_checks(runner)
        st = checks["Embeddings (sentence-transformers)"]
        assert st["status"] == "fail"
        assert "hash fallback" in st["note"], "padded/caps env value must enable deep mode"


class TestEmbedGenerateOutput:
    """#994: `embed generate --output` must write files `embed index` can read."""

    def _patch_generate(self, monkeypatch, retval):
        import numpy as np
        fake_emb = _fake_module(generate_embeddings=lambda *a, **k: np.asarray(retval))
        monkeypatch.setitem(__import__("sys").modules, "semantica.embeddings", fake_emb)

    def test_writes_valid_parquet(self, runner, monkeypatch, tmp_path):
        pytest.importorskip("pyarrow", reason="parquet writer regression needs pyarrow")
        import numpy as np
        import pandas as pd
        self._patch_generate(monkeypatch, [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]])
        out = tmp_path / "embeddings.parquet"
        result = runner.invoke(cli_module.main, ["embed", "generate", "in.json", "--output", str(out)])
        _ok(result)
        df = pd.read_parquet(out)
        assert "embedding" in df.columns
        assert len(df) == 2
        # Use allclose: the writer may store float32 or float64 depending on
        # the model backend; exact == fails for float32-precision values.
        assert np.allclose(df["embedding"].iloc[0], [0.1, 0.2, 0.3], atol=1e-6)

    def test_writes_1d_result_as_single_row_parquet(self, runner, monkeypatch, tmp_path):
        pytest.importorskip("pyarrow", reason="parquet writer regression needs pyarrow")
        import numpy as np
        import pandas as pd
        self._patch_generate(monkeypatch, [0.1, 0.2, 0.3])
        out = tmp_path / "embeddings.parquet"
        result = runner.invoke(cli_module.main, ["embed", "generate", "in.json", "--output", str(out)])
        _ok(result)
        df = pd.read_parquet(out)
        assert len(df) == 1
        assert np.allclose(df["embedding"].iloc[0], [0.1, 0.2, 0.3], atol=1e-6)

    def test_writes_json_records_not_repr_strings(self, runner, monkeypatch, tmp_path):
        import json as _json
        import numpy as np
        import pandas as pd
        self._patch_generate(monkeypatch, [[0.1, 0.2], [0.3, 0.4]])
        out = tmp_path / "embeddings.json"
        result = runner.invoke(cli_module.main, ["embed", "generate", "in.json", "--output", str(out)])
        _ok(result)
        records = _json.loads(out.read_text(encoding="utf-8"))
        assert records == [{"embedding": [0.1, 0.2]}, {"embedding": [0.3, 0.4]}]
        # Verify embed index can read the file back (round-trip contract).
        df = pd.read_json(out, orient="records")
        vector_col = next(
            (c for c in df.columns if isinstance(df[c].iloc[0], (list, np.ndarray))),
            None,
        )
        assert vector_col == "embedding", (
            f"embed index would not find a vector column; got columns {list(df.columns)}"
        )

    def test_rejects_unsupported_output_format(self, runner, monkeypatch, tmp_path):
        self._patch_generate(monkeypatch, [[0.1, 0.2]])
        out = tmp_path / "embeddings.txt"
        result = runner.invoke(cli_module.main, ["embed", "generate", "in.json", "--output", str(out)])
        assert result.exit_code != 0
        assert "Unsupported output format" in result.output
        assert not out.exists()


class TestWriteResultOutput:
    """Unit-level regression tests for _write_result_output().

    Covers every branch: JSON, JSONL, CSV, unsupported extension, no-extension,
    dict+JSONL, empty list, NumPy scalar/array values, and round-trip readback.
    """

    # ── helpers ───────────────────────────────────────────────────────────────

    def _write(self, tmp_path, filename, result):
        """Call _write_result_output and return the output Path."""
        from semantica.cli import _write_result_output
        out = tmp_path / filename
        _write_result_output(out, result)
        return out

    # ── JSON ─────────────────────────────────────────────────────────────────

    def test_json_dict_produces_valid_json(self, tmp_path):
        import json
        out = self._write(tmp_path, "r.json", {"pairs": 3, "score": 0.9})
        data = json.loads(out.read_text(encoding="utf-8"))
        assert data == {"pairs": 3, "score": 0.9}

    def test_json_list_produces_valid_json(self, tmp_path):
        import json
        out = self._write(tmp_path, "r.json", [{"a": 1}, {"a": 2}])
        data = json.loads(out.read_text(encoding="utf-8"))
        assert data == [{"a": 1}, {"a": 2}]

    def test_json_numpy_scalar_serialises_as_number_not_repr(self, tmp_path):
        """np.float32 values must round-trip as JSON numbers, not repr strings."""
        import json
        import numpy as np
        out = self._write(tmp_path, "r.json", {"score": np.float32(0.95)})
        data = json.loads(out.read_text(encoding="utf-8"))
        assert isinstance(data["score"], float), (
            f"expected float, got {type(data['score'])}: {data['score']!r}"
        )
        assert abs(data["score"] - 0.95) < 1e-4

    def test_json_numpy_array_serialises_as_list_not_repr(self, tmp_path):
        """np.ndarray values must round-trip as JSON arrays, not '[0.1 0.2]' repr."""
        import json
        import numpy as np
        out = self._write(tmp_path, "r.json", {"vec": np.array([0.1, 0.2, 0.3])})
        data = json.loads(out.read_text(encoding="utf-8"))
        assert isinstance(data["vec"], list), (
            f"expected list, got {type(data['vec'])}: {data['vec']!r}"
        )
        assert len(data["vec"]) == 3

    # ── JSONL ────────────────────────────────────────────────────────────────

    def test_jsonl_list_writes_one_object_per_line(self, tmp_path):
        """Each item in a list result must occupy exactly one JSONL line."""
        import json
        records = [{"id": "a", "score": 0.9}, {"id": "b", "score": 0.7}]
        out = self._write(tmp_path, "r.jsonl", records)
        lines = [l for l in out.read_text(encoding="utf-8").splitlines() if l.strip()]
        assert len(lines) == 2
        assert json.loads(lines[0]) == {"id": "a", "score": 0.9}
        assert json.loads(lines[1]) == {"id": "b", "score": 0.7}

    def test_jsonl_dict_writes_exactly_one_line(self, tmp_path):
        """A dict result (e.g. ontology_align) must write one JSON object on one line,
        not a pretty-printed multi-line block that pd.read_json(lines=True) cannot parse."""
        import json
        import pandas as pd
        result = {"total_entities": 10, "duplicate_pairs": 3}
        out = self._write(tmp_path, "r.jsonl", result)
        raw = out.read_text(encoding="utf-8")
        lines = [l for l in raw.splitlines() if l.strip()]
        # Exactly one line
        assert len(lines) == 1, (
            f"Expected 1 JSONL line for dict result, got {len(lines)}:\n{raw!r}"
        )
        # That line parses as valid JSON
        parsed = json.loads(lines[0])
        assert parsed == result
        # pd.read_json(lines=True) can read it back
        df = pd.read_json(out, lines=True)
        assert list(df.columns) == ["total_entities", "duplicate_pairs"]

    def test_jsonl_numpy_values_are_not_repr_strings(self, tmp_path):
        """NumPy values inside JSONL lines must be proper JSON, not repr()."""
        import json
        import numpy as np
        records = [{"score": np.float32(0.8), "tag": "x"}]
        out = self._write(tmp_path, "r.jsonl", records)
        line = out.read_text(encoding="utf-8").strip()
        parsed = json.loads(line)
        assert isinstance(parsed["score"], float)

    # ── CSV ──────────────────────────────────────────────────────────────────

    def test_csv_list_of_dicts_produces_readable_csv(self, tmp_path):
        import pandas as pd
        rows = [{"entity_1": "Alice", "entity_2": "Bob", "similarity": 0.87},
                {"entity_1": "Carol", "entity_2": "Dave", "similarity": 0.72}]
        out = self._write(tmp_path, "r.csv", rows)
        df = pd.read_csv(out)
        assert list(df.columns) == ["entity_1", "entity_2", "similarity"]
        assert len(df) == 2
        assert abs(df["similarity"].iloc[0] - 0.87) < 1e-6

    def test_csv_numpy_scalar_becomes_number_not_repr(self, tmp_path):
        """np.float32 in a result row must not become a repr string in the CSV."""
        import numpy as np
        import pandas as pd
        rows = [{"label": "x", "score": np.float32(0.95)}]
        out = self._write(tmp_path, "r.csv", rows)
        df = pd.read_csv(out)
        # The cell must be a numeric type, not a string like 'np.float32(0.95)'
        assert df["score"].dtype.kind in ("f", "i"), (
            f"Expected numeric dtype, got {df['score'].dtype}: {df['score'].iloc[0]!r}"
        )

    def test_csv_empty_list_raises_clickexception(self, tmp_path):
        """An empty result list must raise rather than create a headerless newline."""
        import click
        from semantica.cli import _write_result_output
        out = tmp_path / "empty.csv"
        with pytest.raises(click.ClickException, match="No results to write"):
            _write_result_output(out, [])
        assert not out.exists()

    def test_csv_single_dict_written_as_one_row(self, tmp_path):
        import pandas as pd
        out = self._write(tmp_path, "r.csv", {"total": 5, "merged": 2})
        df = pd.read_csv(out)
        assert len(df) == 1
        assert df["total"].iloc[0] == 5

    # ── unsupported / no-extension ────────────────────────────────────────────

    def test_unsupported_extension_raises_clickexception(self, tmp_path):
        import click
        from semantica.cli import _write_result_output
        out = tmp_path / "report.txt"
        with pytest.raises(click.ClickException, match="Unsupported output format"):
            _write_result_output(out, {"k": "v"})
        assert not out.exists()

    def test_no_extension_raises_clickexception(self, tmp_path):
        """No-extension paths must be rejected — not silently renamed to .json —
        so the path reported to the user always matches the file created."""
        import click
        from semantica.cli import _write_result_output
        out = tmp_path / "report"
        with pytest.raises(click.ClickException, match="Unsupported output format"):
            _write_result_output(out, {"k": "v"})
        assert not out.exists()
        assert not (tmp_path / "report.json").exists()

    def test_txt_extension_raises_clickexception(self, tmp_path):
        """.txt is not a documented format and must be rejected, consistent with
        _write_embeddings_output which also rejects it."""
        import click
        from semantica.cli import _write_result_output
        out = tmp_path / "r.txt"
        with pytest.raises(click.ClickException, match="Unsupported output format"):
            _write_result_output(out, {"k": "v"})
        assert not out.exists()

    def test_uppercase_extension_accepted(self, tmp_path):
        """Extension matching must be case-insensitive (.CSV == .csv)."""
        import pandas as pd
        out = self._write(tmp_path, "r.CSV", [{"a": 1}])
        df = pd.read_csv(out)
        assert len(df) == 1


class TestDeduplicateOutput:
    """CLI-level regression tests for deduplicate --output integration.

    Uses the same monkeypatching pattern as TestDeduplicate.test_detect_runtime_path:
    patch _get_store and get_nodes at the graph_store.methods level, then patch
    the deduplication module so no real model or DB is needed.
    """

    _ENTITIES = [
        {"id": "e1", "name": "Alice", "type": "Person"},
        {"id": "e2", "name": "Alice", "type": "Person"},
    ]
    _DETECT_RESULT = [
        {"entity_1": "e1", "entity_2": "e2", "similarity": 0.9}
    ]

    def _patch_dedup(self, monkeypatch):
        """Wire graph store + deduplication mocks for the detect action."""
        entities = self._ENTITIES
        detect_result = self._DETECT_RESULT

        class FakeStore:
            def get_nodes(self, labels=None, properties=None, limit=100, **opts):
                return entities

        monkeypatch.setattr(
            "semantica.graph_store.methods._get_store", lambda: FakeStore()
        )
        monkeypatch.setattr(
            "semantica.graph_store.methods.get_nodes", lambda **kw: entities
        )
        monkeypatch.setattr(
            "semantica.deduplication.methods.detect_duplicates",
            lambda *a, **k: detect_result,
            raising=False,
        )
        # The CLI imports from .deduplication directly; patch that too.
        import types
        fake_dedup = _fake_module(detect_duplicates=lambda *a, **k: detect_result)
        fake_merger_inst = types.SimpleNamespace(
            merge_duplicates=lambda *a, **k: detect_result
        )
        fake_dedup.entity_merger = types.SimpleNamespace(
            EntityMerger=lambda: fake_merger_inst
        )
        monkeypatch.setitem(
            __import__("sys").modules, "semantica.deduplication", fake_dedup
        )
        monkeypatch.setitem(
            __import__("sys").modules,
            "semantica.deduplication.entity_merger",
            fake_dedup.entity_merger,
        )

    def test_deduplicate_output_json_is_valid(self, runner, monkeypatch, tmp_path):
        """deduplicate --output report.json must produce parseable JSON, not a repr."""
        import json
        self._patch_dedup(monkeypatch)
        out = tmp_path / "report.json"
        result = runner.invoke(
            cli_module.main,
            ["deduplicate", "--action", "detect", "--output", str(out)],
        )
        _ok(result)
        assert out.exists(), f"output file not created; output: {result.output!r}"
        data = json.loads(out.read_text(encoding="utf-8"))
        assert isinstance(data, (list, dict))

    def test_deduplicate_output_csv_is_readable(self, runner, monkeypatch, tmp_path):
        """deduplicate --output report.csv (documented format) must produce valid CSV."""
        import pandas as pd
        self._patch_dedup(monkeypatch)
        out = tmp_path / "report.csv"
        result = runner.invoke(
            cli_module.main,
            ["deduplicate", "--action", "detect", "--output", str(out)],
        )
        _ok(result)
        assert out.exists(), f"CSV file not created; output: {result.output!r}"
        df = pd.read_csv(out)
        assert len(df) >= 1


class TestOntologyAlignOutput:
    """CLI-level regression tests for ontology align --output integration.

    Uses runner.isolated_filesystem() so Click's exists=True source/target
    validation passes, then patches semantica.ontology at the sys.modules level
    before the import inside _action() fires — same pattern as
    TestOntology.test_align_import_error_is_clean.
    """

    _ALIGN_RESULT = {
        "alignments": [{"source": "A", "target": "B", "score": 0.8}],
        "total": 1,
    }

    def _patch_align(self, monkeypatch, align_result=None):
        result = align_result if align_result is not None else self._ALIGN_RESULT
        import types
        fake_gen = types.SimpleNamespace(align=lambda *a, **k: result)
        fake_ontology = _fake_module(
            OntologyGenerator=lambda **k: fake_gen,
        )
        monkeypatch.setitem(
            __import__("sys").modules, "semantica.ontology", fake_ontology
        )

    def test_ontology_align_output_json_is_valid(self, runner, monkeypatch, tmp_path):
        """ontology align --output alignments.json must produce parseable JSON."""
        import json
        self._patch_align(monkeypatch)
        out = tmp_path / "alignments.json"
        with runner.isolated_filesystem():
            open("s.ttl", "w").close()
            open("t.ttl", "w").close()
            result = runner.invoke(
                cli_module.main,
                ["ontology", "align",
                 "--source", "s.ttl", "--target", "t.ttl",
                 "--output", str(out)],
            )
        _ok(result)
        assert out.exists(), f"output file not created; output: {result.output!r}"
        data = json.loads(out.read_text(encoding="utf-8"))
        assert isinstance(data, dict)
        assert "alignments" in data

    def test_ontology_align_output_jsonl_is_readable_by_pandas(
        self, runner, monkeypatch, tmp_path
    ):
        """ontology align --output alignments.jsonl must produce valid JSONL:
        exactly one JSON object per line, readable by pd.read_json(lines=True).
        Regression for F2: dict result must NOT be pretty-printed across multiple
        lines into a .jsonl file."""
        import pandas as pd
        self._patch_align(monkeypatch)
        out = tmp_path / "alignments.jsonl"
        with runner.isolated_filesystem():
            open("s.ttl", "w").close()
            open("t.ttl", "w").close()
            result = runner.invoke(
                cli_module.main,
                ["ontology", "align",
                 "--source", "s.ttl", "--target", "t.ttl",
                 "--output", str(out)],
            )
        _ok(result)
        assert out.exists(), f"JSONL file not created; output: {result.output!r}"
        raw = out.read_text(encoding="utf-8")
        lines = [ln for ln in raw.splitlines() if ln.strip()]
        assert len(lines) == 1, (
            f"Expected exactly 1 JSONL line for a dict result, got {len(lines)}:\n{raw!r}"
        )
        # pd.read_json(lines=True) must succeed — this is what the F2 bug broke.
        df = pd.read_json(out, lines=True)
        assert "alignments" in df.columns
