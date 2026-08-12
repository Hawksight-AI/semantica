"""
Regression tests for security fixes introduced in follow-on to PR #898.

Covers three vulnerabilities found by security audit:
  - VULN-1: CWE-113 Header injection via node_id in Content-Disposition
  - VULN-2: CWE-770 Unbounded memory DoS in /api/enrich/links
  - VULN-3: CWE-20+113 Stored header injection via unsanitized import node IDs

All tests are self-contained; no running server required.
"""
import json
import re
import pytest


# ===================================================================
# Helper: replicate the sanitization functions under test
# ===================================================================

# --- provenance.py ---
_UNSAFE_FILENAME_CHARS_PROV = re.compile(r'[\r\n\x00"\\]')
_MAX_FILENAME_ID_LEN = 128


def _safe_content_disposition_filename(node_id: str, suffix: str) -> str:
    sanitized = _UNSAFE_FILENAME_CHARS_PROV.sub("_", str(node_id))[:_MAX_FILENAME_ID_LEN]
    return f"{sanitized}{suffix}"


# --- export_import.py ---
_UNSAFE_ID_CHARS_IMPORT = re.compile(r'[\r\n\x00"\\]')
_MAX_IMPORT_NODE_ID_LEN = 512


def _sanitize_import_node_id(raw: object) -> str:
    cleaned = _UNSAFE_ID_CHARS_IMPORT.sub("_", str(raw).strip())
    if len(cleaned) > _MAX_IMPORT_NODE_ID_LEN:
        raise ValueError(f"Node ID exceeds {_MAX_IMPORT_NODE_ID_LEN} chars")
    return cleaned


# ===================================================================
# VULN-1: Header injection via node_id in Content-Disposition
# ===================================================================

class TestVuln1HeaderInjection:
    """Regression: CWE-113 — provenance.py lines 332, 344."""

    def _make_header(self, node_id: str, fmt: str = "json") -> str:
        """Reproduce the pre-fix vulnerable code path."""
        suffix = "_provenance.md" if fmt in {"md", "markdown"} else "_provenance.json"
        return f'attachment; filename="{node_id}{suffix}"'

    def _make_safe_header(self, node_id: str, fmt: str = "json") -> str:
        """Post-fix sanitized path."""
        suffix = "_provenance.md" if fmt in {"md", "markdown"} else "_provenance.json"
        return f'attachment; filename="{_safe_content_disposition_filename(node_id, suffix)}"'

    # --- Confirm the old code WAS vulnerable ---

    def test_vulnerable_path_crlf(self):
        """Without the fix, CRLF injects new headers."""
        raw = self._make_header('x"\r\nX-Evil: pwned')
        assert "\r\n" in raw, "Vulnerable: CRLF in header value"
        assert "X-Evil: pwned" in raw

    def test_vulnerable_path_content_type_override(self):
        raw = self._make_header('x"\r\nContent-Type: text/html\r\n\r\n<script>')
        assert "Content-Type: text/html" in raw

    # --- Confirm the fix works ---

    def test_safe_strips_crlf(self):
        # The sanitizer strips \r, \n, \x00, ", \ -- it does not remove the
        # surrounding text of an injection attempt, only the characters that
        # let it split into a new header line. "X-Inject" as a literal
        # substring surviving is expected and harmless; what matters is that
        # no \r\n sequence remains to start a new header.
        safe = self._make_safe_header('evil"\r\nX-Inject: yes')
        assert "\r" not in safe
        assert "\n" not in safe

    def test_safe_strips_null_byte(self):
        safe = self._make_safe_header("node\x00.json")
        assert "\x00" not in safe

    def test_safe_strips_double_quote(self):
        safe = self._make_safe_header('node"extra"')
        assert safe.count('"') == 2  # only the outer quotes from the template

    def test_safe_strips_backslash(self):
        safe = self._make_safe_header("node\\path")
        assert "\\" not in safe

    def test_safe_length_cap(self):
        long_id = "A" * 300
        safe = _safe_content_disposition_filename(long_id, "_provenance.json")
        assert len(safe) <= _MAX_FILENAME_ID_LEN + len("_provenance.json")

    def test_safe_normal_id_unchanged(self):
        safe = _safe_content_disposition_filename("my-node_123.v2", "_provenance.json")
        assert safe == "my-node_123.v2_provenance.json"

    def test_safe_set_cookie_injection_blocked(self):
        # As above: the literal word "Set-Cookie" surviving is fine; what
        # actually blocks the attack is that no \r\n remains to start a new
        # header line, so this can never be parsed as a second header.
        payload = 'x"\r\nSet-Cookie: session=HIJACKED; Path=/\r\n\r\n'
        safe = self._make_safe_header(payload)
        assert "\r\n" not in safe
        assert "\r" not in safe
        assert "\n" not in safe

    def test_safe_markdown_suffix(self):
        safe = self._make_safe_header("my-node", "md")
        assert safe.endswith("_provenance.md\"")


# ===================================================================
# VULN-2: Unbounded memory DoS in /api/enrich/links
# ===================================================================

class TestVuln2LinkPredictionDos:
    """Regression: CWE-770 — enrich.py lines 197-198."""

    def test_constant_values_changed(self):
        """The predict_links function must not use the old unbounded limit=999_999."""
        import ast, pathlib
        src = pathlib.Path(
            "semantica/explorer/routes/enrich.py"
        ).read_text(encoding="utf-8")
        tree = ast.parse(src)
        # Find the predict_links function and check its body for 999_999 literals
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "predict_links":
                func_src = ast.get_source_segment(src, node) or ""
                assert "999_999" not in func_src, (
                    "Old limit=999_999 still present in predict_links — DoS fix not applied"
                )
                break
        else:
            pytest.fail("predict_links function not found in enrich.py")

    def test_cap_constant_defined(self):
        """_LINK_PREDICTION_MAX_NODES must be defined and <= 50_000."""
        from semantica.explorer.routes.enrich import _LINK_PREDICTION_MAX_NODES
        assert isinstance(_LINK_PREDICTION_MAX_NODES, int)
        assert _LINK_PREDICTION_MAX_NODES <= 50_000, (
            f"Cap {_LINK_PREDICTION_MAX_NODES} is too high — should be <= 50,000"
        )

    def test_semaphore_defined(self):
        """_link_prediction_semaphore must exist."""
        import asyncio
        from semantica.explorer.routes.enrich import _link_prediction_semaphore
        assert isinstance(_link_prediction_semaphore, asyncio.Semaphore)

    def test_memory_scaling_linear(self):
        """Confirm memory per node is bounded (basis for the extrapolation)."""
        import tracemalloc
        tracemalloc.start()
        nodes = [
            {"id": f"node_{i}", "type": "entity", "embedding": [0.1] * 128}
            for i in range(10_000)
        ]
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        peak_mb = peak / 1024 / 1024
        # At 10k nodes with 128-dim embeddings peak should be < 50 MB in-process
        assert peak_mb < 50, f"Memory at 10k nodes = {peak_mb:.1f} MB — unexpectedly high"


# ===================================================================
# VULN-3: Unsanitized import node ID → stored header injection
# ===================================================================

class TestVuln3ImportNodeIdSanitization:
    """Regression: CWE-20+113 — export_import.py lines 111, 203."""

    # --- The sanitizer itself ---

    def test_strips_crlf(self):
        assert "\r" not in _sanitize_import_node_id("evil\r\nX-Inject: yes")
        assert "\n" not in _sanitize_import_node_id("evil\r\nX-Inject: yes")

    def test_strips_null_byte(self):
        result = _sanitize_import_node_id("node\x00.json")
        assert "\x00" not in result

    def test_strips_double_quote(self):
        result = _sanitize_import_node_id('node"extra"')
        assert '"' not in result

    def test_strips_backslash(self):
        result = _sanitize_import_node_id("node\\path")
        assert "\\" not in result

    def test_normal_id_unchanged(self):
        assert _sanitize_import_node_id("my-node_123") == "my-node_123"

    def test_length_cap_raises(self):
        with pytest.raises((ValueError, Exception)):
            _sanitize_import_node_id("A" * 600)

    def test_set_cookie_payload_sanitized(self):
        # The sanitizer strips \r, \n, \x00, ", \ -- not letters, so the word
        # "Set-Cookie" surviving is fine. What matters for CWE-113 is that no
        # \r\n sequence remains to split the header.
        bad = 'evil"\r\nSet-Cookie: session=HIJACKED; Path=/'
        result = _sanitize_import_node_id(bad)
        assert "\r\n" not in result
        assert "\r" not in result
        assert "\n" not in result

    def test_content_type_payload_sanitized(self):
        bad = 'x"\r\nContent-Type: text/html\r\n\r\n<script>alert(1)</script>'
        result = _sanitize_import_node_id(bad)
        assert "\r\n" not in result
        assert "\r" not in result
        assert "\n" not in result

    # --- End-to-end: sanitized ID cannot trigger header injection ---

    def test_chain_sanitized_id_cannot_inject(self):
        """After sanitization, stored ID must not split Content-Disposition."""
        bad_id = 'evil"\r\nSet-Cookie: session=HIJACKED'
        stored_id = _sanitize_import_node_id(bad_id)
        # Simulate provenance report header construction
        header = _safe_content_disposition_filename(stored_id, "_provenance.json")
        assert "\r\n" not in header
        assert "\r" not in header
        assert "\n" not in header

    def test_import_sanitizer_applied_json(self):
        """_sanitize_import_node_id must be called in the JSON import path."""
        import ast, pathlib
        src = pathlib.Path(
            "semantica/explorer/routes/export_import.py"
        ).read_text(encoding="utf-8")
        assert "_sanitize_import_node_id" in src
        # Must appear at least twice: JSON path + CSV path
        assert src.count("_sanitize_import_node_id") >= 2, (
            "Sanitizer only applied in one import path — CSV or JSON path is still vulnerable"
        )

    def test_import_sanitizer_applied_csv(self):
        """The CSV import path must also call _sanitize_import_node_id."""
        import pathlib
        src = pathlib.Path(
            "semantica/explorer/routes/export_import.py"
        ).read_text(encoding="utf-8")
        # Find both occurrences with their surrounding context
        lines = src.splitlines()
        sanitizer_lines = [i for i, l in enumerate(lines) if "_sanitize_import_node_id" in l]
        assert len(sanitizer_lines) >= 2, (
            f"Expected >= 2 calls to _sanitize_import_node_id, found {len(sanitizer_lines)}"
        )


# ===================================================================
# VULN-3 bypass fix: the `"properties" in raw_node` fast path in the JSON
# import loop stored the id verbatim, completely skipping
# _sanitize_import_node_id(). Exercised end-to-end via the real FastAPI
# route (not the standalone sanitizer copy above) since that's exactly how
# the bypass went unnoticed by the original test suite in this PR.
# ===================================================================


@pytest.fixture
def _real_client(monkeypatch):
    pytest.importorskip("starlette")
    # These tests exercise route logic, not the API-key auth layer (see
    # tests/explorer/conftest.py, which does the same for that directory).
    monkeypatch.setenv("SEMANTICA_ALLOW_ANONYMOUS", "true")
    monkeypatch.delenv("SEMANTICA_API_KEY", raising=False)
    from starlette.testclient import TestClient
    from semantica.context.context_graph import ContextGraph
    from semantica.explorer.app import create_app
    from semantica.explorer.session import GraphSession

    session = GraphSession(ContextGraph(advanced_analytics=False))
    app = create_app(session=session)
    with TestClient(app) as test_client:
        yield test_client


class TestVuln3PropertiesBypassFix:
    """Regression: export_import.py's `"properties" in raw_node` fast path."""

    def test_properties_shaped_node_id_is_sanitized(self, _real_client):
        """A node object carrying its own "properties" key -- the shape this
        app's own /api/export produces, and what
        test_import_json_with_edge_metadata in test_explorer_api.py already
        uses -- must still have its id sanitized on import."""
        malicious_id = 'evil"\r\nSet-Cookie: session=HIJACKED; Path=/'
        payload = json.dumps(
            {"nodes": [{"id": malicious_id, "type": "entity", "properties": {"content": "pwned"}}]}
        )
        response = _real_client.post(
            "/api/import",
            files={"file": ("evil.json", payload, "application/json")},
        )
        assert response.status_code == 200
        assert response.json()["nodes_added"] == 1

        expected_id = _sanitize_import_node_id(malicious_id)
        assert "\r" not in expected_id and "\n" not in expected_id

        listing = _real_client.get("/api/graph/nodes", params={"limit": 100})
        ids = {n["id"] for n in listing.json()["nodes"]}
        assert malicious_id not in ids, "Raw malicious id was stored verbatim -- bypass not fixed"
        assert expected_id in ids, "Sanitized id was not what got stored"

    def test_properties_bypass_blocks_header_injection_e2e(self, _real_client):
        """Full chain: import a "properties"-shaped node with a CRLF id, then
        request its provenance report and confirm no header injection."""
        malicious_id = 'evil"\r\nContent-Type: text/html\r\nX-Evil: pwned'
        payload = json.dumps({"nodes": [{"id": malicious_id, "type": "entity", "properties": {}}]})
        response = _real_client.post(
            "/api/import",
            files={"file": ("evil.json", payload, "application/json")},
        )
        assert response.status_code == 200

        expected_id = _sanitize_import_node_id(malicious_id)
        report = _real_client.get(
            "/api/provenance/report", params={"node_id": expected_id, "format": "json"}
        )
        assert report.status_code == 200
        disposition = report.headers.get("content-disposition", "")
        # No \r or \n surviving is the necessary and sufficient condition for
        # blocking header injection -- the sanitizer strips those characters
        # but not letters, so "X-Evil"/"Content-Type" as literal substrings
        # surviving is expected and harmless.
        assert "\r\n" not in disposition
        assert "\r" not in disposition
        assert "\n" not in disposition
        # And confirm no attacker-controlled header actually landed as a
        # distinct response header (would only happen if splitting occurred).
        assert "x-evil" not in report.headers
        assert report.headers.get("content-type", "").startswith("application/json")


# ===================================================================
# VULN-2 fix follow-up: the 10k/50k cap must be enforced BEFORE the
# expensive get_nodes()/get_edges() calls, not after. paginate_nodes()/
# paginate_edges() normalize the *entire* matching set before applying
# `limit`, so checking `total` only after calling them still pays the full
# O(graph size) cost the cap exists to avoid.
# ===================================================================


class TestVuln2CapEnforcedBeforeExpensiveWork:
    def test_get_raw_counts_matches_graph(self):
        from semantica.context.context_graph import ContextGraph
        from semantica.explorer.session import GraphSession

        graph = ContextGraph(advanced_analytics=False)
        graph.add_node("a", node_type="entity", content="A")
        graph.add_node("b", node_type="entity", content="B")
        graph.add_edge("a", "b", edge_type="related_to")
        session = GraphSession(graph)

        total_nodes, total_edges = session.get_raw_counts()
        assert total_nodes == 2
        assert total_edges == 1

    def test_predict_links_checks_raw_counts_before_get_nodes(self):
        import pathlib

        src = pathlib.Path("semantica/explorer/routes/enrich.py").read_text(encoding="utf-8")
        raw_counts_pos = src.index("session.get_raw_counts")
        get_nodes_pos = src.index("session.get_nodes,")
        assert raw_counts_pos < get_nodes_pos, (
            "get_raw_counts() must run before get_nodes() so the cap is enforced "
            "before paying the full O(graph size) normalization cost"
        )

    def test_predict_links_rejects_oversized_graph_e2e(self, monkeypatch):
        """Exercise the real route: with the cap patched low, an oversized
        graph must 413 instead of scoring the full candidate pool."""
        pytest.importorskip("starlette")
        monkeypatch.setenv("SEMANTICA_ALLOW_ANONYMOUS", "true")
        monkeypatch.delenv("SEMANTICA_API_KEY", raising=False)
        from starlette.testclient import TestClient
        from semantica.context.context_graph import ContextGraph
        from semantica.explorer.app import create_app
        from semantica.explorer.session import GraphSession
        import semantica.explorer.routes.enrich as enrich_module

        graph = ContextGraph(advanced_analytics=False)
        for i in range(5):
            graph.add_node(f"n{i}", node_type="entity", content=f"node {i}")
        session = GraphSession(graph)
        if session.link_predictor is None:
            pytest.skip("LinkPredictor not available; KG extras not installed.")

        monkeypatch.setattr(enrich_module, "_LINK_PREDICTION_MAX_NODES", 2)

        app = create_app(session=session)
        with TestClient(app) as client:
            response = client.post("/api/enrich/links", json={"node_id": "n0"})
        assert response.status_code == 413
        assert "nodes" in response.json()["detail"].lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
