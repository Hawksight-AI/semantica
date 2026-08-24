"""SSRF regression tests for AgnoKnowledgeGraph.load_urls().

Prior to the fix, load_urls() used urllib.request.urlopen with only a
scheme check — private/loopback/link-local/metadata IPs were not blocked
and redirects were followed without re-validation.

These tests exercise the real SSRF guard (no mock of request_with_ssrf_guard
itself) by patching at the socket.getaddrinfo level, confirming that
blocked addresses never reach the network layer.
"""

from __future__ import annotations

import socket
from unittest.mock import MagicMock, patch

import pytest

# conftest.py installs the full agno stub before this file is collected.
from integrations.agno.knowledge_graph import AgnoKnowledgeGraph

from semantica.utils.exceptions import ValidationError


# ---------------------------------------------------------------------------
# Minimal fakes so AgnoKnowledgeGraph.__init__ succeeds without real imports.
# ---------------------------------------------------------------------------
class _FakeNER:
    def extract_entities(self, text):
        return []


class _FakeRelExtractor:
    def extract_relations(self, text, entities=None):
        return []


class _FakeGraphBuilder:
    def build(self, sources):
        pass


class _FakeContextGraph:
    def find_nodes(self, label=None):
        return []

    def get_neighbors(self, node_id=None, hops=1):
        return []


def _make_kg() -> AgnoKnowledgeGraph:
    return AgnoKnowledgeGraph(
        graph_builder=_FakeGraphBuilder(),
        ner_extractor=_FakeNER(),
        relation_extractor=_FakeRelExtractor(),
        context_graph=_FakeContextGraph(),
    )


def _public_getaddrinfo(host, *args, **kwargs):
    """Stub that makes every hostname resolve to a public IP."""
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]


# ---------------------------------------------------------------------------
# Tests: blocked addresses must never be fetched
# ---------------------------------------------------------------------------

class TestLoadUrlsBlockedAddresses:
    """load_urls() must silently skip (warn) any URL that fails the SSRF guard."""

    @pytest.mark.parametrize("url", [
        "http://127.0.0.1/secret",
        "http://127.0.0.1:9200/",            # common internal service port
        "http://0.0.0.0/",
        "http://169.254.169.254/latest/meta-data/",
        "http://169.254.169.254/computeMetadata/v1/",
        "http://10.0.0.1/internal",
        "http://10.255.255.255/",
        "http://172.16.0.1/",
        "http://172.31.255.255/",
        "http://192.168.0.1/admin",
        "http://192.168.100.200/",
        "http://[::1]/ipv6-loopback",
        "http://[fc00::1]/ipv6-ula",
        "http://[fe80::1]/ipv6-link-local",
    ])
    def test_blocked_ip_never_reaches_network(self, url):
        """Blocked addresses must raise ValidationError inside the guard,
        which load_urls() catches and logs — _ingest_text must NOT be called."""
        kg = _make_kg()
        with patch.object(kg, "_ingest_text") as mock_ingest:
            kg.load_urls([url])
        mock_ingest.assert_not_called()

    def test_localhost_hostname_blocked(self):
        kg = _make_kg()
        with patch.object(kg, "_ingest_text") as mock_ingest:
            kg.load_urls(["http://localhost/admin"])
        mock_ingest.assert_not_called()

    def test_localhost_subdomain_blocked(self):
        kg = _make_kg()
        with patch.object(kg, "_ingest_text") as mock_ingest:
            kg.load_urls(["http://foo.localhost/"])
        mock_ingest.assert_not_called()

    def test_hostname_resolving_to_private_ip_blocked(self):
        """A hostname that resolves to a private IP must be blocked even though
        the URL string itself looks like a normal hostname."""
        def _internal_getaddrinfo(host, *a, **kw):
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.5", 0))]

        kg = _make_kg()
        with patch("semantica.ingest.ssrf.socket.getaddrinfo", side_effect=_internal_getaddrinfo):
            with patch.object(kg, "_ingest_text") as mock_ingest:
                kg.load_urls(["http://internal.corp/secret"])
        mock_ingest.assert_not_called()

    def test_hostname_resolving_to_metadata_ip_blocked(self):
        def _meta_getaddrinfo(host, *a, **kw):
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("169.254.169.254", 0))]

        kg = _make_kg()
        with patch("semantica.ingest.ssrf.socket.getaddrinfo", side_effect=_meta_getaddrinfo):
            with patch.object(kg, "_ingest_text") as mock_ingest:
                kg.load_urls(["http://metadata.internal/v1/token"])
        mock_ingest.assert_not_called()


class TestLoadUrlsNonHttpSchemes:
    """Non-HTTP(S) schemes must be rejected."""

    @pytest.mark.parametrize("url", [
        "file:///etc/passwd",
        "file://localhost/etc/shadow",
        "ftp://example.com/file.txt",
        "gopher://example.com/1",
        "dict://example.com/",
        "sftp://example.com/data",
    ])
    def test_non_http_scheme_blocked(self, url):
        kg = _make_kg()
        with patch.object(kg, "_ingest_text") as mock_ingest:
            kg.load_urls([url])
        mock_ingest.assert_not_called()


class TestLoadUrlsRedirects:
    """Redirects to private/blocked addresses must be rejected."""

    def test_redirect_to_loopback_blocked(self):
        """A public first hop that redirects to loopback must be blocked."""
        redirect = MagicMock()
        redirect.status_code = 302
        redirect.headers = {"Location": "http://127.0.0.1/secret"}
        redirect.close = MagicMock()

        kg = _make_kg()
        with patch(
            "semantica.ingest.ssrf.socket.getaddrinfo",
            return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))],
        ):
            # Patch requests.Session so the first hop returns our redirect mock.
            # The guard sees the 302, then validates the Location — 127.0.0.1 is
            # blocked without a second network call.
            with patch("semantica.ingest.ssrf.requests.Session") as MockSession:
                mock_session = MockSession.return_value
                mock_session.adapters = {}
                mock_session.headers = {}
                mock_session.auth = None
                mock_session.trust_env = True
                mock_session.request.return_value = redirect

                with patch.object(kg, "_ingest_text") as mock_ingest:
                    kg.load_urls(["https://example.com/start"])
        mock_ingest.assert_not_called()

    def test_redirect_to_metadata_ip_blocked(self):
        """Redirect to cloud metadata endpoint must be blocked."""
        redirect = MagicMock()
        redirect.status_code = 301
        redirect.headers = {"Location": "http://169.254.169.254/latest/meta-data/"}
        redirect.close = MagicMock()

        kg = _make_kg()
        with patch(
            "semantica.ingest.ssrf.socket.getaddrinfo",
            return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))],
        ):
            with patch("semantica.ingest.ssrf.requests.Session") as MockSession:
                mock_session = MockSession.return_value
                mock_session.adapters = {}
                mock_session.headers = {}
                mock_session.auth = None
                mock_session.trust_env = True
                mock_session.request.return_value = redirect

                with patch.object(kg, "_ingest_text") as mock_ingest:
                    kg.load_urls(["https://example.com/redirect-me"])
        mock_ingest.assert_not_called()


class TestLoadUrlsValidUrls:
    """Valid public URLs must succeed and call _ingest_text."""

    def test_valid_public_url_ingested(self):
        """A URL resolving to a public IP must be fetched and ingested."""
        ok_response = MagicMock()
        ok_response.status_code = 200
        ok_response.headers = {}
        ok_response.text = "This is the document content."

        kg = _make_kg()
        with patch("semantica.ingest.ssrf.socket.getaddrinfo", side_effect=_public_getaddrinfo):
            with patch("semantica.ingest.ssrf.requests.Session") as MockSession:
                mock_session = MockSession.return_value
                mock_session.adapters = {}
                mock_session.headers = {}
                mock_session.auth = None
                mock_session.trust_env = True
                mock_session.request.return_value = ok_response

                with patch.object(kg, "_ingest_text") as mock_ingest:
                    kg.load_urls(["https://example.com/doc.txt"])

        mock_ingest.assert_called_once_with(
            "This is the document content.", source="https://example.com/doc.txt"
        )

    def test_multiple_urls_each_independently_validated(self):
        """Each URL in the list is independently validated; one blocked URL
        must not prevent valid subsequent URLs from being ingested."""
        ok_response = MagicMock()
        ok_response.status_code = 200
        ok_response.headers = {}
        ok_response.text = "Valid content."

        def _selective_getaddrinfo(host, *a, **kw):
            if host == "internal.corp":
                return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.5", 0))]
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]

        kg = _make_kg()
        with patch("semantica.ingest.ssrf.socket.getaddrinfo", side_effect=_selective_getaddrinfo):
            with patch("semantica.ingest.ssrf.requests.Session") as MockSession:
                mock_session = MockSession.return_value
                mock_session.adapters = {}
                mock_session.headers = {}
                mock_session.auth = None
                mock_session.trust_env = True
                mock_session.request.return_value = ok_response

                with patch.object(kg, "_ingest_text") as mock_ingest:
                    kg.load_urls([
                        "http://internal.corp/secret",      # blocked
                        "https://example.com/public.txt",   # allowed
                    ])

        # Only the valid URL triggers ingestion
        mock_ingest.assert_called_once_with("Valid content.", source="https://example.com/public.txt")

    def test_failed_fetch_does_not_raise(self):
        """A network failure on a valid URL must log a warning, not raise."""
        import requests as _requests

        kg = _make_kg()
        with patch("semantica.ingest.ssrf.socket.getaddrinfo", side_effect=_public_getaddrinfo):
            with patch("semantica.ingest.ssrf.requests.Session") as MockSession:
                mock_session = MockSession.return_value
                mock_session.adapters = {}
                mock_session.headers = {}
                mock_session.auth = None
                mock_session.trust_env = True
                mock_session.request.side_effect = _requests.exceptions.ConnectionError("refused")

                # Must not raise; failure is logged and skipped
                kg.load_urls(["https://example.com/unreachable"])
