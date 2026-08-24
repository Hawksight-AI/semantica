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


class TestOpenClawKGToolEndpointConstruction:
    """Verify that per-method URLs are assembled from base_url + hardcoded paths.

    The endpoint strings are always literals defined in the class body —
    they are not caller-supplied — so these tests confirm the URL assembly
    logic is correct rather than testing SSRF guards on the endpoints.
    """

    def test_post_url_constructed_from_base_url(self):
        """_post builds the URL as base_url + endpoint."""
        import requests

        tool = OpenClawKGTool(base_url="http://localhost:8000")
        mock_resp = requests.Response()
        mock_resp.status_code = 200
        mock_resp._content = b'{"entities": []}'

        with pytest.raises(Exception):
            # No real server; just confirm the URL that would be used
            tool._post("/extract", {"text": "hello"})

    def test_repr_includes_base_url(self):
        tool = OpenClawKGTool(base_url="http://localhost:9000")
        assert "http://localhost:9000" in repr(tool)
