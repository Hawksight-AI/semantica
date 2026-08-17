"""Security regression tests for issue #947.

Prevents Authorization / Proxy-Authorization headers from leaking across
cross-origin redirects in request_with_ssrf_guard, MCPClient, and
PublicAPIIngestor.

Each test is focused on a single, specific security property so that a future
regression immediately pinpoints the broken invariant.
"""
from __future__ import annotations

import socket
from unittest.mock import MagicMock, call, patch

import pytest
import requests

from semantica.ingest.mcp_client import MCPClient
from semantica.ingest.public_api_ingestor import PublicAPIIngestor
from semantica.ingest.ssrf import request_with_ssrf_guard
from semantica.utils.exceptions import ValidationError

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_PUBLIC_IP = "93.184.216.34"  # example.com — public, safe


def _public_getaddrinfo(host, *args, **kwargs):
    """DNS stub that maps every hostname to a safe public IP."""
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (_PUBLIC_IP, 0))]


def _make_session_with_auth(token: str = "Bearer secret") -> requests.Session:
    """Return a real requests.Session with Authorization in session.headers."""
    sess = requests.Session()
    sess.headers["Authorization"] = token
    return sess


def _mock_redirect(location: str, status: int = 302) -> MagicMock:
    r = MagicMock()
    r.status_code = status
    r.headers = {"Location": location}
    r.close = MagicMock()
    return r


def _mock_final(status: int = 200) -> MagicMock:
    r = MagicMock()
    r.status_code = status
    r.headers = {}
    r.close = MagicMock()
    return r


# ===========================================================================
# Section 1 – request_with_ssrf_guard: session.headers stripping  (#947)
# ===========================================================================


class TestSessionHeadersStripping:
    """Authorization stored in session.headers must not reach a foreign origin."""

    @patch("semantica.ingest.ssrf.socket.getaddrinfo", side_effect=_public_getaddrinfo)
    def test_session_authorization_stripped_on_cross_origin_redirect(self, _):
        """session.headers["Authorization"] must not appear in the hop to a new host."""
        sess = _make_session_with_auth()
        redirect = _mock_redirect("https://other.example/final")
        final = _mock_final()

        with patch.object(sess, "request", side_effect=[redirect, final]) as mock_req:
            request_with_ssrf_guard("GET", "https://example.com/start", session=sess)

        assert mock_req.call_count == 2
        # The second call must not carry Authorization in kwargs["headers"].
        second_headers = mock_req.call_args_list[1].kwargs.get("headers", {})
        assert "Authorization" not in second_headers
        # Also verify requests won't re-inject it via session (the guard must
        # have cleared it from sess.headers before the second call).
        assert "Authorization" not in sess.headers or sess.headers.get("Authorization") == "Bearer secret"
        # Post-call restoration: session must be restored.
        assert sess.headers.get("Authorization") == "Bearer secret"

    @patch("semantica.ingest.ssrf.socket.getaddrinfo", side_effect=_public_getaddrinfo)
    def test_session_headers_cleared_before_second_hop_not_just_restored_after(self, _):
        """Prove session.headers["Authorization"] is absent AT CALL TIME of the second hop.

        This test closes the gap where a mock-based test only checks kwargs["headers"]
        but not whether session.headers was actually cleared before requests' internal
        header-merge would re-inject the credential.

        Strategy: capture a snapshot of sess.headers at each call invocation so we
        can assert it was empty during the second hop — not just after the guard returns.
        """
        sess = _make_session_with_auth("Bearer proof-token")
        redirect = _mock_redirect("https://other.example/final")
        final = _mock_final()

        snapshots: list = []

        original_request = sess.request.__func__ if hasattr(sess.request, "__func__") else None

        def capturing_side_effect(*args, **kwargs):
            # Snapshot what session.headers contain at the exact moment of this call.
            snapshots.append(dict(sess.headers))
            return [redirect, final][len(snapshots) - 1]

        with patch.object(sess, "request", side_effect=capturing_side_effect):
            request_with_ssrf_guard("GET", "https://example.com/start", session=sess)

        assert len(snapshots) == 2

        # Hop 1 (same origin, pre-redirect): Authorization PRESENT in session.headers.
        assert snapshots[0].get("Authorization") == "Bearer proof-token", (
            "Authorization must be in session.headers for the first (same-origin) call"
        )

        # Hop 2 (cross-origin): Authorization ABSENT from session.headers.
        # This is what prevents requests from re-injecting it via its header-merge step.
        assert "Authorization" not in snapshots[1], (
            "Authorization must have been removed from session.headers BEFORE the "
            "second (cross-origin) call — removing it only from kwargs is not enough "
            "because requests.Session merges session.headers at call time."
        )

        # After the guard returns, session state is fully restored.
        assert sess.headers.get("Authorization") == "Bearer proof-token", (
            "session.headers must be restored after the guard returns"
        )

    @patch("semantica.ingest.ssrf.socket.getaddrinfo", side_effect=_public_getaddrinfo)
    def test_session_authorization_preserved_on_same_origin_redirect(self, _):
        """Same-origin redirect must keep Authorization in session.headers untouched."""
        sess = _make_session_with_auth()
        redirect = _mock_redirect("https://example.com/page2")
        final = _mock_final()

        with patch.object(sess, "request", side_effect=[redirect, final]) as mock_req:
            request_with_ssrf_guard("GET", "https://example.com/start", session=sess)

        assert mock_req.call_count == 2
        # The second call's kwargs["headers"] should still carry the credential.
        second_headers = mock_req.call_args_list[1].kwargs.get("headers", {})
        # When no stripping occurred, kwargs["headers"] is unchanged from
        # the caller (no headers kwarg was passed here, so it may be absent
        # or empty — what matters is that the session header was NOT cleared).
        assert sess.headers.get("Authorization") == "Bearer secret"

    @patch("semantica.ingest.ssrf.socket.getaddrinfo", side_effect=_public_getaddrinfo)
    def test_session_credentials_restored_after_successful_request(self, _):
        """Session headers must be restored after a redirect chain completes normally."""
        sess = _make_session_with_auth("Bearer my-token")
        redirect = _mock_redirect("https://other.example/final")
        final = _mock_final()

        with patch.object(sess, "request", side_effect=[redirect, final]):
            request_with_ssrf_guard("GET", "https://example.com/start", session=sess)

        assert sess.headers.get("Authorization") == "Bearer my-token"

    @patch("semantica.ingest.ssrf.socket.getaddrinfo", side_effect=_public_getaddrinfo)
    def test_session_credentials_restored_after_ssrf_exception(self, _):
        """Session headers must be restored even when the guard raises ValidationError."""
        sess = _make_session_with_auth("Bearer my-token")
        # Redirect to a loopback address — guard will raise.
        redirect = _mock_redirect("http://127.0.0.1/secret")

        with patch.object(sess, "request", return_value=redirect):
            with pytest.raises(ValidationError):
                request_with_ssrf_guard(
                    "GET", "https://example.com/start", session=sess
                )

        assert sess.headers.get("Authorization") == "Bearer my-token"

    @patch("semantica.ingest.ssrf.socket.getaddrinfo", side_effect=_public_getaddrinfo)
    def test_session_credentials_restored_after_max_redirects_exceeded(self, _):
        """Session headers must be restored when the max-redirect cap is hit."""
        sess = _make_session_with_auth("Bearer loop-token")
        hop = _mock_redirect("https://other.example/loop")

        # All hops redirect to the same foreign host → exceeds cap.
        with patch.object(sess, "request", return_value=hop):
            with pytest.raises(ValidationError, match="Exceeded maximum"):
                request_with_ssrf_guard(
                    "GET",
                    "https://example.com/start",
                    session=sess,
                    max_redirects=2,
                )

        assert sess.headers.get("Authorization") == "Bearer loop-token"

    @patch("semantica.ingest.ssrf.socket.getaddrinfo", side_effect=_public_getaddrinfo)
    def test_proxy_authorization_stripped_on_cross_origin_redirect(self, _):
        """Proxy-Authorization must be stripped alongside Authorization."""
        sess = requests.Session()
        sess.headers["Proxy-Authorization"] = "Basic cHJveHk6cGFzcw=="
        redirect = _mock_redirect("https://other.example/final")
        final = _mock_final()

        with patch.object(sess, "request", side_effect=[redirect, final]) as mock_req:
            request_with_ssrf_guard("GET", "https://example.com/start", session=sess)

        second_headers = mock_req.call_args_list[1].kwargs.get("headers", {})
        assert "Proxy-Authorization" not in second_headers
        # Restored after call.
        assert "Proxy-Authorization" in sess.headers

    @patch("semantica.ingest.ssrf.socket.getaddrinfo", side_effect=_public_getaddrinfo)
    def test_both_auth_headers_stripped_simultaneously(self, _):
        """Both Authorization and Proxy-Authorization must be stripped together."""
        sess = requests.Session()
        sess.headers["Authorization"] = "Bearer tok"
        sess.headers["Proxy-Authorization"] = "Basic abc"
        redirect = _mock_redirect("https://other.example/final")
        final = _mock_final()

        with patch.object(sess, "request", side_effect=[redirect, final]) as mock_req:
            request_with_ssrf_guard("GET", "https://example.com/start", session=sess)

        second_headers = mock_req.call_args_list[1].kwargs.get("headers", {})
        assert "Authorization" not in second_headers
        assert "Proxy-Authorization" not in second_headers
        # Restored after call.
        assert sess.headers.get("Authorization") == "Bearer tok"
        assert sess.headers.get("Proxy-Authorization") == "Basic abc"


# ===========================================================================
# Section 2 – request_with_ssrf_guard: credential resurrection prevention
# ===========================================================================


class TestCredentialResurrection:
    """Stripped credentials must not reappear for later hops in the same chain."""

    @patch("semantica.ingest.ssrf.socket.getaddrinfo", side_effect=_public_getaddrinfo)
    def test_credentials_do_not_reappear_after_cross_origin_hop(self, _):
        """A subsequent same-origin-as-hop-2 redirect must not restore the credential."""
        # Chain: example.com → other.example (strip) → other.example/page2 (stay stripped)
        hop1 = _mock_redirect("https://other.example/step2")
        hop2 = _mock_redirect("https://other.example/final")  # same host as hop1 target
        final = _mock_final()

        with patch(
            "semantica.ingest.ssrf.requests.request",
            side_effect=[hop1, hop2, final],
        ) as mock_req:
            request_with_ssrf_guard(
                "GET",
                "https://example.com/start",
                headers={"Authorization": "Bearer secret"},
            )

        assert mock_req.call_count == 3
        # Hop 1 (example.com): credential present
        h1 = mock_req.call_args_list[0].kwargs.get("headers", {})
        assert h1.get("Authorization") == "Bearer secret"
        # Hop 2 (other.example): stripped
        h2 = mock_req.call_args_list[1].kwargs.get("headers", {})
        assert "Authorization" not in h2
        # Hop 3 (still other.example): stays stripped — must NOT reappear
        h3 = mock_req.call_args_list[2].kwargs.get("headers", {})
        assert "Authorization" not in h3

    @patch("semantica.ingest.ssrf.socket.getaddrinfo", side_effect=_public_getaddrinfo)
    def test_session_auth_does_not_reappear_in_multihop_chain(self, _):
        """session.headers auth stripped for hop 2 must stay absent for hop 3."""
        sess = _make_session_with_auth("Bearer multi")
        hop1 = _mock_redirect("https://other.example/step2")   # cross-origin: strip
        hop2 = _mock_redirect("https://other.example/final")   # same-as-hop1: stay stripped
        final = _mock_final()

        with patch.object(sess, "request", side_effect=[hop1, hop2, final]) as mock_req:
            request_with_ssrf_guard("GET", "https://example.com/start", session=sess)

        # After the call the session is restored.
        assert sess.headers.get("Authorization") == "Bearer multi"

        h2 = mock_req.call_args_list[1].kwargs.get("headers", {})
        assert "Authorization" not in h2
        h3 = mock_req.call_args_list[2].kwargs.get("headers", {})
        assert "Authorization" not in h3


# ===========================================================================
# Section 3 – request_with_ssrf_guard: specific redirect-type coverage
# ===========================================================================


class TestRedirectTypesAndOriginChanges:
    """Per-type and per-scenario auth-stripping rules."""

    @patch("semantica.ingest.ssrf.socket.getaddrinfo", side_effect=_public_getaddrinfo)
    def test_strips_on_307_cross_origin(self, _):
        """307 Temporary Redirect to a different host must strip credentials."""
        redirect = MagicMock()
        redirect.status_code = 307
        redirect.headers = {"Location": "https://other.example/final"}
        redirect.close = MagicMock()
        final = _mock_final()

        with patch(
            "semantica.ingest.ssrf.requests.request",
            side_effect=[redirect, final],
        ) as mock_req:
            request_with_ssrf_guard(
                "GET",
                "https://example.com/start",
                headers={"Authorization": "Bearer tok"},
            )

        second = mock_req.call_args_list[1].kwargs.get("headers", {})
        assert "Authorization" not in second

    @patch("semantica.ingest.ssrf.socket.getaddrinfo", side_effect=_public_getaddrinfo)
    def test_strips_on_308_cross_origin(self, _):
        """308 Permanent Redirect to a different host must strip credentials."""
        redirect = MagicMock()
        redirect.status_code = 308
        redirect.headers = {"Location": "https://other.example/final"}
        redirect.close = MagicMock()
        final = _mock_final()

        with patch(
            "semantica.ingest.ssrf.requests.request",
            side_effect=[redirect, final],
        ) as mock_req:
            request_with_ssrf_guard(
                "GET",
                "https://example.com/start",
                headers={"Authorization": "Bearer tok"},
            )

        second = mock_req.call_args_list[1].kwargs.get("headers", {})
        assert "Authorization" not in second

    @patch("semantica.ingest.ssrf.socket.getaddrinfo", side_effect=_public_getaddrinfo)
    def test_strips_on_port_change(self, _):
        """Redirect that changes the port (non-default) must strip credentials."""
        redirect = _mock_redirect("https://example.com:8443/final")
        final = _mock_final()

        with patch(
            "semantica.ingest.ssrf.requests.request",
            side_effect=[redirect, final],
        ) as mock_req:
            request_with_ssrf_guard(
                "GET",
                "https://example.com/start",
                headers={"Authorization": "Bearer tok"},
            )

        second = mock_req.call_args_list[1].kwargs.get("headers", {})
        assert "Authorization" not in second

    @patch("semantica.ingest.ssrf.socket.getaddrinfo", side_effect=_public_getaddrinfo)
    def test_strips_on_subdomain_change(self, _):
        """Redirect from apex to subdomain (different hostname) must strip credentials."""
        redirect = _mock_redirect("https://api.example.com/final")
        final = _mock_final()

        with patch(
            "semantica.ingest.ssrf.requests.request",
            side_effect=[redirect, final],
        ) as mock_req:
            request_with_ssrf_guard(
                "GET",
                "https://example.com/start",
                headers={"Authorization": "Bearer tok"},
            )

        second = mock_req.call_args_list[1].kwargs.get("headers", {})
        assert "Authorization" not in second

    @patch("semantica.ingest.ssrf.socket.getaddrinfo", side_effect=_public_getaddrinfo)
    def test_keeps_on_https_443_explicit_to_implicit(self, _):
        """https://example.com:443 → https://example.com (same, just drop explicit port)."""
        redirect = _mock_redirect("https://example.com/final")
        final = _mock_final()

        with patch(
            "semantica.ingest.ssrf.requests.request",
            side_effect=[redirect, final],
        ) as mock_req:
            request_with_ssrf_guard(
                "GET",
                "https://example.com:443/start",
                headers={"Authorization": "Bearer tok"},
            )

        second = mock_req.call_args_list[1].kwargs.get("headers", {})
        assert second.get("Authorization") == "Bearer tok"

    @patch("semantica.ingest.ssrf.socket.getaddrinfo", side_effect=_public_getaddrinfo)
    def test_case_insensitive_header_stripped(self, _):
        """Lowercase/UPPERCASE variants of Authorization must also be stripped."""
        redirect = _mock_redirect("https://other.example/final")
        final = _mock_final()

        with patch(
            "semantica.ingest.ssrf.requests.request",
            side_effect=[redirect, final],
        ) as mock_req:
            request_with_ssrf_guard(
                "GET",
                "https://example.com/start",
                # Pass a lowercase variant to verify case-insensitive stripping.
                headers={"authorization": "Bearer lower", "AUTHORIZATION": "Bearer upper"},
            )

        second = mock_req.call_args_list[1].kwargs.get("headers", {})
        for key in second:
            assert key.lower() != "authorization", (
                f"Authorization header variant {key!r} was not stripped"
            )


# ===========================================================================
# Section 4 – MCPClient: redirect auth-stripping  (#947)
# ===========================================================================


class TestMCPClientAuthRedirect:
    """MCPClient._send_request_http must not leak credentials on cross-origin redirect."""

    def _mock_mcp_response(self, payload=None):
        resp = MagicMock()
        resp.status_code = 200
        resp.headers = {}
        resp.raise_for_status = MagicMock()
        resp.json.return_value = payload or {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {"serverInfo": {}, "capabilities": {}},
        }
        return resp

    @patch("semantica.ingest.ssrf.socket.getaddrinfo", side_effect=_public_getaddrinfo)
    def test_cross_origin_redirect_strips_authorization(self, _):
        """Authorization must not reach a different host after an MCP server redirect."""
        redirect = _mock_redirect("https://other.example/mcp")
        redirect.status_code = 302
        final = self._mock_mcp_response()

        client = MCPClient(
            url="https://mcp.example.com/mcp",
            headers={"Authorization": "Bearer mcp-token"},
        )

        with patch(
            "semantica.ingest.ssrf.requests.request",
            side_effect=[redirect, final],
        ) as mock_req:
            client._send_request_http({"jsonrpc": "2.0", "method": "ping"})

        assert mock_req.call_count == 2
        second_headers = mock_req.call_args_list[1].kwargs.get("headers", {})
        assert "Authorization" not in second_headers

    @patch("semantica.ingest.ssrf.socket.getaddrinfo", side_effect=_public_getaddrinfo)
    def test_same_origin_redirect_preserves_authorization(self, _):
        """Same-host redirect must keep Authorization intact."""
        redirect = _mock_redirect("https://mcp.example.com/mcp/v2")
        redirect.status_code = 301
        final = self._mock_mcp_response()

        client = MCPClient(
            url="https://mcp.example.com/mcp",
            headers={"Authorization": "Bearer mcp-token"},
        )

        with patch(
            "semantica.ingest.ssrf.requests.request",
            side_effect=[redirect, final],
        ) as mock_req:
            client._send_request_http({"jsonrpc": "2.0", "method": "ping"})

        assert mock_req.call_count == 2
        second_headers = mock_req.call_args_list[1].kwargs.get("headers", {})
        assert second_headers.get("Authorization") == "Bearer mcp-token"

    def test_localhost_mcp_server_is_not_blocked(self):
        """localhost MCP endpoints must work (allow_private_ips=True)."""
        final = self._mock_mcp_response()
        client = MCPClient(url="http://localhost:8000/mcp")

        with patch(
            "semantica.ingest.ssrf.requests.request",
            return_value=final,
        ) as mock_req:
            client._send_request_http({"jsonrpc": "2.0", "method": "ping"})

        mock_req.assert_called_once()

    def test_loopback_ip_mcp_server_is_not_blocked(self):
        """127.0.0.1 MCP endpoints must work (allow_private_ips=True)."""
        final = self._mock_mcp_response()
        client = MCPClient(url="http://127.0.0.1:9000/mcp")

        with patch(
            "semantica.ingest.ssrf.requests.request",
            return_value=final,
        ) as mock_req:
            client._send_request_http({"jsonrpc": "2.0", "method": "ping"})

        mock_req.assert_called_once()

    @patch("semantica.ingest.ssrf.socket.getaddrinfo", side_effect=_public_getaddrinfo)
    def test_scheme_downgrade_strips_authorization(self, _):
        """https MCP server that redirects to http must strip the credential."""
        redirect = _mock_redirect("http://mcp.example.com/mcp")
        redirect.status_code = 302
        final = self._mock_mcp_response()

        client = MCPClient(
            url="https://mcp.example.com/mcp",
            headers={"Authorization": "Bearer downgrade-test"},
        )

        with patch(
            "semantica.ingest.ssrf.requests.request",
            side_effect=[redirect, final],
        ) as mock_req:
            client._send_request_http({"jsonrpc": "2.0", "method": "ping"})

        second_headers = mock_req.call_args_list[1].kwargs.get("headers", {})
        assert "Authorization" not in second_headers

    @patch("semantica.ingest.ssrf.socket.getaddrinfo", side_effect=_public_getaddrinfo)
    def test_max_redirect_cap_respected(self, _):
        """Infinite redirect loop must raise ValidationError."""
        hop = _mock_redirect("https://mcp.example.com/mcp/loop")

        client = MCPClient(url="https://mcp.example.com/mcp")

        with patch(
            "semantica.ingest.ssrf.requests.request",
            return_value=hop,
        ):
            with pytest.raises((ValidationError, Exception), match="[Rr]edirect|[Ee]xceeded"):
                client._send_request_http({"jsonrpc": "2.0", "method": "ping"})

    @patch("semantica.ingest.ssrf.socket.getaddrinfo", side_effect=_public_getaddrinfo)
    def test_allow_redirects_false_enforced(self, _):
        """The guard must pass allow_redirects=False on every hop."""
        final = self._mock_mcp_response()
        client = MCPClient(
            url="https://mcp.example.com/mcp",
            headers={"Authorization": "Bearer tok"},
        )

        with patch(
            "semantica.ingest.ssrf.requests.request",
            return_value=final,
        ) as mock_req:
            client._send_request_http({"jsonrpc": "2.0", "method": "ping"})

        assert mock_req.call_args.kwargs.get("allow_redirects") is False


# ===========================================================================
# Section 5 – PublicAPIIngestor: redirect auth-stripping  (#947)
# ===========================================================================


def _mock_public_response(status: int = 200, json_payload=None) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status
    resp.headers = {"Content-Type": "application/json"}
    resp.json.return_value = json_payload or [{"id": 1}]
    resp.text = ""
    if status >= 400:
        resp.raise_for_status.side_effect = requests.exceptions.HTTPError(
            f"{status} error"
        )
    else:
        resp.raise_for_status.return_value = None
    resp.close = MagicMock()
    return resp


class TestPublicAPIIngestorRedirectSecurity:
    """PublicAPIIngestor must not leak credentials on redirect and must block SSRF."""

    @patch("semantica.ingest.ssrf.socket.getaddrinfo", side_effect=_public_getaddrinfo)
    def test_redirect_to_private_ip_blocked_in_detect(self, _):
        """detect_public_api() must reject a redirect that resolves to a private IP."""
        redirect = _mock_redirect("http://169.254.169.254/latest/meta-data/")

        with patch("requests.Session") as MockSession:
            mock_session = MockSession.return_value
            mock_session.headers = {}
            mock_session.request.return_value = redirect
            mock_session.request.return_value.close = MagicMock()

            ingestor = PublicAPIIngestor(rate_limit_delay=0)
            with pytest.raises(ValidationError, match="blocked"):
                ingestor.detect_public_api("https://example.com/api")

    @patch("semantica.ingest.ssrf.socket.getaddrinfo", side_effect=_public_getaddrinfo)
    def test_redirect_to_private_ip_blocked_in_ingest(self, _):
        """ingest_public_api() must reject a redirect that resolves to a private IP."""
        redirect = _mock_redirect("http://10.0.0.1/internal")

        with patch("requests.Session") as MockSession:
            mock_session = MockSession.return_value
            mock_session.headers = {}
            mock_session.request.return_value = redirect
            mock_session.request.return_value.close = MagicMock()

            ingestor = PublicAPIIngestor(rate_limit_delay=0)
            with pytest.raises(ValidationError, match="blocked"):
                ingestor.ingest_public_api("https://example.com/api")

    @patch("semantica.ingest.ssrf.socket.getaddrinfo", side_effect=_public_getaddrinfo)
    def test_session_auth_not_leaked_on_cross_origin_redirect_ingest(self, _):
        """Session-level auth header must not reach a foreign host via ingest_public_api."""
        redirect = _mock_redirect("https://other.example/api")
        final = _mock_public_response(json_payload=[{"id": 1}])

        # Simulate a session that somehow has Authorization (e.g. misconfiguration).
        with patch("requests.Session") as MockSession:
            mock_session = MockSession.return_value
            mock_session.headers = {"Authorization": "Bearer leaked"}
            mock_session.request.side_effect = [redirect, final]

            ingestor = PublicAPIIngestor(
                rate_limit_delay=0, validate_no_auth=False
            )
            # Inject the auth-bearing session directly.
            ingestor.session = mock_session

            ingestor.ingest_public_api("https://example.com/api")

        assert mock_session.request.call_count == 2
        second_headers = mock_session.request.call_args_list[1].kwargs.get(
            "headers", {}
        )
        assert "Authorization" not in second_headers

    @patch("semantica.ingest.ssrf.socket.getaddrinfo", side_effect=_public_getaddrinfo)
    def test_allow_redirects_false_enforced_in_detect(self, _):
        """detect_public_api() must pass allow_redirects=False to the underlying call."""
        final = _mock_public_response()

        with patch("requests.Session") as MockSession:
            mock_session = MockSession.return_value
            mock_session.headers = {}
            mock_session.request.return_value = final

            ingestor = PublicAPIIngestor(rate_limit_delay=0)
            ingestor.detect_public_api("https://example.com/api")

        assert mock_session.request.call_args.kwargs.get("allow_redirects") is False

    @patch("semantica.ingest.ssrf.socket.getaddrinfo", side_effect=_public_getaddrinfo)
    def test_allow_redirects_false_enforced_in_ingest(self, _):
        """ingest_public_api() must pass allow_redirects=False to the underlying call."""
        final = _mock_public_response(json_payload=[{"id": 1}])

        with patch("requests.Session") as MockSession:
            mock_session = MockSession.return_value
            mock_session.headers = {}
            mock_session.request.return_value = final

            ingestor = PublicAPIIngestor(rate_limit_delay=0)
            ingestor.ingest_public_api("https://example.com/api")

        assert mock_session.request.call_args.kwargs.get("allow_redirects") is False

    @patch("semantica.ingest.ssrf.socket.getaddrinfo", side_effect=_public_getaddrinfo)
    def test_validate_no_auth_false_does_not_bypass_redirect_stripping(self, _):
        """Even with validate_no_auth=False the guard strips auth on cross-origin redirect."""
        redirect = _mock_redirect("https://other.example/api")
        final = _mock_public_response(json_payload=[{"id": 1}])

        with patch("requests.Session") as MockSession:
            mock_session = MockSession.return_value
            mock_session.headers = {}
            mock_session.request.side_effect = [redirect, final]

            ingestor = PublicAPIIngestor(
                rate_limit_delay=0, validate_no_auth=False
            )
            ingestor.ingest_public_api(
                "https://example.com/api",
                headers={"Authorization": "Bearer should-be-stripped"},
            )

        second_headers = mock_session.request.call_args_list[1].kwargs.get(
            "headers", {}
        )
        assert "Authorization" not in second_headers
