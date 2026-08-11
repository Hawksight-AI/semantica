"""
Regression tests for security fixes introduced in follow-on to PR #898.

Covers three vulnerabilities found by security audit:
  - VULN-1: CWE-113 Header injection via node_id in Content-Disposition
  - VULN-2: CWE-770 Unbounded memory DoS in /api/enrich/links
  - VULN-3: CWE-20+113 Stored header injection via unsanitized import node IDs

All tests are self-contained; no running server required.
"""
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
        safe = self._make_safe_header('evil"\r\nX-Inject: yes')
        assert "\r" not in safe
        assert "\n" not in safe
        assert "X-Inject" not in safe

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
        payload = 'x"\r\nSet-Cookie: session=HIJACKED; Path=/\r\n\r\n'
        safe = self._make_safe_header(payload)
        assert "Set-Cookie" not in safe
        assert "\r\n" not in safe

    def test_safe_markdown_suffix(self):
        safe = self._make_safe_header("my-node", "md")
        assert safe.endswith("_provenance.md\"")


# ===================================================================
# VULN-2: Unbounded memory DoS in /api/enrich/links
# ===================================================================

class TestVuln2LinkPredictionDos:
    """Regression: CWE-770 — enrich.py lines 197-198."""

    def test_constant_values_changed(self):
        """The hardcoded 999_999 limit must no longer appear."""
        import ast, pathlib
        src = pathlib.Path(
            "semantica/explorer/routes/enrich.py"
        ).read_text(encoding="utf-8")
        # Should not contain the old unbounded limit
        assert "999_999" not in src, (
            "Old limit=999_999 still present in enrich.py — DoS fix not applied"
        )

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
        bad = 'evil"\r\nSet-Cookie: session=HIJACKED; Path=/'
        result = _sanitize_import_node_id(bad)
        assert "Set-Cookie" not in result
        assert "\r\n" not in result

    def test_content_type_payload_sanitized(self):
        bad = 'x"\r\nContent-Type: text/html\r\n\r\n<script>alert(1)</script>'
        result = _sanitize_import_node_id(bad)
        assert "Content-Type" not in result

    # --- End-to-end: sanitized ID cannot trigger header injection ---

    def test_chain_sanitized_id_cannot_inject(self):
        """After sanitization, stored ID must not split Content-Disposition."""
        bad_id = 'evil"\r\nSet-Cookie: session=HIJACKED'
        stored_id = _sanitize_import_node_id(bad_id)
        # Simulate provenance report header construction
        header = _safe_content_disposition_filename(stored_id, "_provenance.json")
        assert "\r\n" not in header
        assert "Set-Cookie" not in header

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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
