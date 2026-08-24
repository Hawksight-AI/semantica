"""SSRF hardening tests for OpenClawKGTool.

OpenClawKGTool is designed to speak to a locally-running Semantica REST server
(default: http://localhost:8000).  The fix validates base_url at construction
time so that obviously wrong schemes (file://, ftp://, gopher://, etc.) and
malformed URLs are rejected immediately, while localhost and other private
addresses remain valid because allow_private_ips=True is the correct posture
for this tool's intended use case.

These are construction-time tests; per-request SSRF guarding is not the
contract of this tool (its threat model is operator-configured base_url, not
untrusted per-call URLs).
"""

from __future__ import annotations

import pytest

from integrations.openclaw.mcp_tool import OpenClawKGTool
from semantica.utils.exceptions import ValidationError


class TestOpenClawKGToolBaseUrlValidation:
    """base_url is validated at __init__ time."""

    # ------------------------------------------------------------------
    # Valid base_urls — all must construct without raising
    # ------------------------------------------------------------------

    @pytest.mark.parametrize("url", [
        "http://localhost:8000",
        "http://localhost",
        "http://127.0.0.1:8000",
        "http://127.0.0.1",
        "https://localhost:8443",
        "http://0.0.0.0:8000",
        "http://192.168.1.10:8000",   # LAN Semantica server
        "http://10.0.0.5:8000",       # corporate intranet deployment
        "https://semantica.internal/api",
        "https://semantica.example.com",
    ])
    def test_valid_base_url_accepted(self, url):
        """All reasonable operator-configured base_urls must be accepted."""
        tool = OpenClawKGTool(base_url=url)
        assert tool.base_url == url.rstrip("/")

    # ------------------------------------------------------------------
    # Invalid schemes — must raise at construction
    # ------------------------------------------------------------------

    @pytest.mark.parametrize("url", [
        "file:///etc/passwd",
        "file://localhost/etc/shadow",
        "ftp://example.com/",
        "gopher://example.com/1",
        "dict://example.com/",
        "sftp://example.com/",
        "ldap://example.com/",
        "javascript:alert(1)",
    ])
    def test_invalid_scheme_rejected(self, url):
        """Non-HTTP(S) schemes must be rejected at construction time."""
        with pytest.raises((ValidationError, ValueError)):
            OpenClawKGTool(base_url=url)

    # ------------------------------------------------------------------
    # Malformed URLs
    # ------------------------------------------------------------------

    def test_empty_string_rejected(self):
        with pytest.raises((ValidationError, ValueError)):
            OpenClawKGTool(base_url="")

    def test_no_scheme_rejected(self):
        """A bare hostname without a scheme must be rejected."""
        with pytest.raises((ValidationError, ValueError)):
            OpenClawKGTool(base_url="localhost:8000")

    def test_whitespace_only_rejected(self):
        with pytest.raises((ValidationError, ValueError)):
            OpenClawKGTool(base_url="   ")

    # ------------------------------------------------------------------
    # Default is the documented localhost value
    # ------------------------------------------------------------------

    def test_default_base_url_is_localhost(self):
        """The default must remain http://localhost:8000 for backward compat."""
        tool = OpenClawKGTool()
        assert tool.base_url == "http://localhost:8000"

    def test_trailing_slash_stripped(self):
        """base_url trailing slash must be stripped so paths concatenate cleanly."""
        tool = OpenClawKGTool(base_url="http://localhost:8000/")
        assert tool.base_url == "http://localhost:8000"

    def test_multiple_trailing_slashes_stripped(self):
        tool = OpenClawKGTool(base_url="http://localhost:8000///")
        assert tool.base_url == "http://localhost:8000"

    def test_leading_and_trailing_whitespace_stripped(self):
        """Whitespace around a valid URL must be stripped before storage so
        _post/_get don't build requests with space-padded URLs like
        '  http://localhost:8000  /extract'."""
        tool = OpenClawKGTool(base_url="  http://localhost:8000  ")
        assert tool.base_url == "http://localhost:8000"

    def test_whitespace_plus_trailing_slash_both_stripped(self):
        tool = OpenClawKGTool(base_url="  http://localhost:8000/  ")
        assert tool.base_url == "http://localhost:8000"


class TestOpenClawKGToolFallbackValidation:
    """When semantica.ingest.ssrf is unavailable (ImportError path), the fallback
    must perform the same structural checks as validate_url_for_request:
    non-empty string, http/https scheme, netloc present, hostname present.

    The fallback is exercised by temporarily hiding semantica.ingest.ssrf
    from sys.modules so the import inside __init__ raises ImportError.
    """

    @staticmethod
    def _hide_ssrf(monkeypatch):
        """Return a context in which semantica.ingest.ssrf appears unimportable."""
        import sys
        monkeypatch.setitem(sys.modules, "semantica.ingest.ssrf", None)

    # ------------------------------------------------------------------
    # Valid URLs must still be accepted in the fallback path
    # ------------------------------------------------------------------

    @pytest.mark.parametrize("url", [
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "https://semantica.example.com",
    ])
    def test_fallback_valid_url_accepted(self, url, monkeypatch):
        self._hide_ssrf(monkeypatch)
        tool = OpenClawKGTool(base_url=url)
        assert tool.base_url == url.rstrip("/")

    # ------------------------------------------------------------------
    # Malformed URLs that the fallback previously let through
    # ------------------------------------------------------------------

    @pytest.mark.parametrize("url", [
        "http://",          # scheme only, no netloc or hostname
        "https://",         # same
        "http:///path",     # empty hostname (netloc is present but hostname is None)
    ])
    def test_fallback_no_netloc_rejected(self, url, monkeypatch):
        """URLs with a valid scheme but missing netloc/hostname must be rejected
        in the fallback path, matching validate_url_for_request's behaviour."""
        self._hide_ssrf(monkeypatch)
        with pytest.raises((ValidationError, ValueError)):
            OpenClawKGTool(base_url=url)

    def test_fallback_empty_string_rejected(self, monkeypatch):
        self._hide_ssrf(monkeypatch)
        with pytest.raises((ValidationError, ValueError)):
            OpenClawKGTool(base_url="")

    def test_fallback_whitespace_only_rejected(self, monkeypatch):
        self._hide_ssrf(monkeypatch)
        with pytest.raises((ValidationError, ValueError)):
            OpenClawKGTool(base_url="   ")

    def test_fallback_invalid_scheme_rejected(self, monkeypatch):
        self._hide_ssrf(monkeypatch)
        with pytest.raises((ValidationError, ValueError)):
            OpenClawKGTool(base_url="file:///etc/passwd")

    def test_fallback_no_scheme_rejected(self, monkeypatch):
        self._hide_ssrf(monkeypatch)
        with pytest.raises((ValidationError, ValueError)):
            OpenClawKGTool(base_url="localhost:8000")

    def test_fallback_whitespace_padded_valid_url_stored_clean(self, monkeypatch):
        """Whitespace around a valid URL must be stripped before storage in the
        fallback path too — same guarantee as the normal path."""
        self._hide_ssrf(monkeypatch)
        tool = OpenClawKGTool(base_url="  http://localhost:8000  ")
        assert tool.base_url == "http://localhost:8000"


class TestOpenClawKGToolEndpointConstruction:
    """Verify that per-method URLs are assembled from base_url + hardcoded paths.

    The endpoint strings are always literals defined in the class body —
    they are not caller-supplied — so these tests confirm the URL assembly
    logic is correct rather than testing SSRF guards on the endpoints.

    All HTTP calls are mocked so no real network connection is made.
    """

    def _mock_session(self, status: int = 200, body: bytes = b"{}") -> "MagicMock":
        """Return a mock session whose post/get return a minimal JSON response."""
        from unittest.mock import MagicMock
        mock_resp = MagicMock()
        mock_resp.status_code = status
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {}
        session = MagicMock()
        session.post.return_value = mock_resp
        session.get.return_value = mock_resp
        return session

    def test_post_url_constructed_from_base_url(self):
        """_post must call session.post with the exact URL base_url+endpoint,
        the supplied payload as json=, and the tool timeout. No real connection."""
        from unittest.mock import patch

        tool = OpenClawKGTool(base_url="http://localhost:8000")
        mock_session = self._mock_session()

        with patch.object(tool, "_get_session", return_value=mock_session):
            tool._post("/extract", {"text": "hello"})

        mock_session.post.assert_called_once_with(
            "http://localhost:8000/extract",
            json={"text": "hello"},
            timeout=30,
        )

    def test_post_url_with_custom_base_url(self):
        """base_url is reflected correctly in the outbound URL for _post."""
        from unittest.mock import patch

        tool = OpenClawKGTool(base_url="http://192.168.1.10:9000")
        mock_session = self._mock_session()

        with patch.object(tool, "_get_session", return_value=mock_session):
            tool._post("/decisions", {"decision": "deploy"})

        mock_session.post.assert_called_once_with(
            "http://192.168.1.10:9000/decisions",
            json={"decision": "deploy"},
            timeout=30,
        )

    def test_get_url_constructed_from_base_url(self):
        """_get must call session.get with the exact URL base_url+endpoint,
        params={} when none are supplied, and the tool timeout."""
        from unittest.mock import patch

        tool = OpenClawKGTool(base_url="http://localhost:8000")
        mock_session = self._mock_session()

        with patch.object(tool, "_get_session", return_value=mock_session):
            tool._get("/analytics")

        mock_session.get.assert_called_once_with(
            "http://localhost:8000/analytics",
            params={},
            timeout=30,
        )

    def test_get_url_with_params(self):
        """_get must forward supplied params to session.get."""
        from unittest.mock import patch

        tool = OpenClawKGTool(base_url="http://localhost:8000")
        mock_session = self._mock_session()

        with patch.object(tool, "_get_session", return_value=mock_session):
            tool._get("/decisions/search", {"q": "deploy", "limit": 5})

        mock_session.get.assert_called_once_with(
            "http://localhost:8000/decisions/search",
            params={"q": "deploy", "limit": 5},
            timeout=30,
        )

    def test_custom_timeout_forwarded(self):
        """A non-default timeout must reach session.post and session.get."""
        from unittest.mock import patch

        tool = OpenClawKGTool(base_url="http://localhost:8000", timeout=60)
        mock_session = self._mock_session()

        with patch.object(tool, "_get_session", return_value=mock_session):
            tool._post("/extract", {"text": "x"})
            tool._get("/analytics")

        assert mock_session.post.call_args.kwargs["timeout"] == 60
        assert mock_session.get.call_args.kwargs["timeout"] == 60

    def test_repr_includes_base_url(self):
        tool = OpenClawKGTool(base_url="http://localhost:9000")
        assert "http://localhost:9000" in repr(tool)
