"""SSRF protection tests for web and API ingestors (issue #867)."""

from unittest.mock import MagicMock, patch

import pytest
import urllib3.connectionpool as pool

from semantica.ingest.api_ingestor import RESTIngestor
from semantica.ingest.ssrf import (
    parse_bool,
    request_with_ssrf_guard,
    validate_url_for_request,
)
from semantica.ingest.web_ingestor import SitemapCrawler, WebIngestor
from semantica.utils.exceptions import ValidationError


class TestParseBool:
    def test_bool_passthrough(self):
        assert parse_bool(True) is True
        assert parse_bool(False) is False

    def test_none_uses_default(self):
        assert parse_bool(None) is False
        assert parse_bool(None, default=True) is True

    def test_string_true_values(self):
        for value in ("true", "TRUE", "1", "yes", "on", " Yes "):
            assert parse_bool(value) is True

    def test_string_false_values(self):
        for value in ("false", "FALSE", "0", "no", "off", " No "):
            assert parse_bool(value) is False

    def test_int_zero_one(self):
        assert parse_bool(0) is False
        assert parse_bool(1) is True

    def test_rejects_unknown_string(self):
        with pytest.raises(ValidationError, match="Invalid boolean"):
            parse_bool("maybe")


class TestValidateUrlForRequest:
    def test_accepts_https(self):
        with patch(
            "semantica.ingest.ssrf.socket.getaddrinfo",
            return_value=[(None, None, None, None, ("93.184.216.34", 0))],
        ):
            validate_url_for_request("https://example.com/path")

    def test_rejects_file_scheme(self):
        with pytest.raises(ValidationError, match="not permitted"):
            validate_url_for_request("file://localhost/etc/passwd")

    def test_rejects_gopher_scheme(self):
        with pytest.raises(ValidationError, match="not permitted"):
            validate_url_for_request("gopher://example.com/1")

    def test_rejects_literal_private_ips(self):
        for url in (
            "http://10.0.0.1/",
            "http://192.168.1.1/",
            "http://172.16.5.5/internal",
            "http://127.0.0.1:9999/internal",
            "http://169.254.169.254/latest/meta-data/",
        ):
            with pytest.raises(ValidationError, match="blocked"):
                validate_url_for_request(url)

    def test_rejects_localhost_hostname(self):
        with pytest.raises(ValidationError, match="not allowed"):
            validate_url_for_request("http://localhost/admin")

    def test_rejects_hostname_resolving_to_private_ip(self):
        with patch(
            "semantica.ingest.ssrf.socket.getaddrinfo",
            return_value=[(None, None, None, None, ("10.0.0.5", 0))],
        ):
            with pytest.raises(ValidationError, match="blocked"):
                validate_url_for_request("http://internal.corp/secret")

    def test_allow_private_ips_opt_in(self):
        validate_url_for_request(
            "http://127.0.0.1:8080/health", allow_private_ips=True
        )
        # Scheme allowlist still applies when private IPs are permitted
        with pytest.raises(ValidationError, match="not permitted"):
            validate_url_for_request(
                "file://localhost/x", allow_private_ips=True
            )

    def test_dns_failure_raises(self):
        import socket

        with patch(
            "semantica.ingest.ssrf.socket.getaddrinfo",
            side_effect=socket.gaierror("name or service not known"),
        ):
            with pytest.raises(ValidationError, match="could not be resolved safely"):
                validate_url_for_request("http://does-not-resolve.invalid/path")

    def test_dns_timeout_raises(self):
        import concurrent.futures

        with patch(
            "semantica.ingest.ssrf.concurrent.futures.Future.result",
            side_effect=concurrent.futures.TimeoutError(),
        ):
            with pytest.raises(ValidationError, match="could not be resolved safely"):
                validate_url_for_request("http://slow-dns.example/path")

    def test_hung_getaddrinfo_returns_within_timeout_bound(self):
        """Timeout must not wait on executor shutdown for a blocking resolver."""
        import time

        import semantica.ingest.ssrf as ssrf

        hang_seconds = 1.5
        bound = 0.1

        def hanging_getaddrinfo(*_args, **_kwargs):
            time.sleep(hang_seconds)
            return [(None, None, None, None, ("93.184.216.34", 0))]

        with patch.object(ssrf, "_DNS_RESOLVE_TIMEOUT_SECONDS", bound), patch(
            "semantica.ingest.ssrf.socket.getaddrinfo",
            side_effect=hanging_getaddrinfo,
        ):
            start = time.monotonic()
            with pytest.raises(ValidationError, match="could not be resolved safely"):
                ssrf._hostname_resolves_to_blocked("hanging.example")
            elapsed = time.monotonic() - start

        # Must fail closed near the configured bound, not after hang_seconds
        # (which is what ``with ThreadPoolExecutor`` shutdown waiting causes).
        assert elapsed < hang_seconds / 2
        assert elapsed < bound + 0.75


class TestRequestWithSsrfGuardRedirects:
    def test_blocks_redirect_to_loopback(self):
        redirect = MagicMock()
        redirect.status_code = 302
        redirect.headers = {"Location": "http://127.0.0.1/secret"}
        redirect.close = MagicMock()

        session = MagicMock()
        session.request.return_value = redirect

        with patch(
            "semantica.ingest.ssrf.socket.getaddrinfo",
            return_value=[(None, None, None, None, ("93.184.216.34", 0))],
        ):
            with pytest.raises(ValidationError, match="blocked"):
                request_with_ssrf_guard(
                    "GET",
                    "https://example.com/start",
                    session=session,
                )

        session.request.assert_called_once()
        assert session.request.call_args.kwargs.get("allow_redirects") is False

    def test_blocks_redirect_to_metadata_ip(self):
        redirect = MagicMock()
        redirect.status_code = 301
        redirect.headers = {"Location": "http://169.254.169.254/latest/meta-data/"}
        redirect.close = MagicMock()

        session = MagicMock()
        session.request.return_value = redirect

        with patch(
            "semantica.ingest.ssrf.socket.getaddrinfo",
            return_value=[(None, None, None, None, ("93.184.216.34", 0))],
        ):
            with pytest.raises(ValidationError, match="blocked"):
                request_with_ssrf_guard(
                    "GET",
                    "https://example.com/start",
                    session=session,
                )

    def test_strips_authorization_on_cross_host_redirect(self):
        """Sensitive headers must not leak to a different redirect host."""
        redirect = MagicMock()
        redirect.status_code = 302
        redirect.headers = {"Location": "https://other-host.example/final"}
        redirect.close = MagicMock()

        final = MagicMock()
        final.status_code = 200
        final.headers = {}

        session = MagicMock()
        session.request.side_effect = [redirect, final]

        with patch(
            "semantica.ingest.ssrf.socket.getaddrinfo",
            return_value=[(None, None, None, None, ("93.184.216.34", 0))],
        ):
            request_with_ssrf_guard(
                "GET",
                "https://example.com/start",
                session=session,
                headers={"Authorization": "Bearer secret-token"},
            )

        assert session.request.call_count == 2
        second_call_headers = session.request.call_args_list[1].kwargs.get("headers", {})
        assert "Authorization" not in second_call_headers
        # The first hop still had the credential
        first_call_headers = session.request.call_args_list[0].kwargs.get("headers", {})
        assert first_call_headers.get("Authorization") == "Bearer secret-token"

    def test_keeps_authorization_on_same_host_redirect(self):
        """Same-host redirects keep the credential (requests semantics)."""
        redirect = MagicMock()
        redirect.status_code = 302
        redirect.headers = {"Location": "https://example.com/final"}
        redirect.close = MagicMock()

        final = MagicMock()
        final.status_code = 200
        final.headers = {}

        session = MagicMock()
        session.request.side_effect = [redirect, final]

        with patch(
            "semantica.ingest.ssrf.socket.getaddrinfo",
            return_value=[(None, None, None, None, ("93.184.216.34", 0))],
        ):
            request_with_ssrf_guard(
                "GET",
                "https://example.com/start",
                session=session,
                headers={"Authorization": "Bearer secret-token"},
            )

        assert session.request.call_count == 2
        second_call_headers = session.request.call_args_list[1].kwargs.get("headers", {})
        assert second_call_headers.get("Authorization") == "Bearer secret-token"

    def test_strips_authorization_on_scheme_downgrade(self):
        """Credentials must not follow an https -> http downgrade on the same host."""
        redirect = MagicMock()
        redirect.status_code = 302
        redirect.headers = {"Location": "http://example.com/final"}
        redirect.close = MagicMock()

        final = MagicMock()
        final.status_code = 200
        final.headers = {}

        session = MagicMock()
        session.request.side_effect = [redirect, final]

        with patch(
            "semantica.ingest.ssrf.socket.getaddrinfo",
            return_value=[(None, None, None, None, ("93.184.216.34", 0))],
        ):
            request_with_ssrf_guard(
                "GET",
                "https://example.com/start",
                session=session,
                headers={"Authorization": "Bearer secret-token"},
            )

        assert session.request.call_count == 2
        second_call_headers = session.request.call_args_list[1].kwargs.get("headers", {})
        assert "Authorization" not in second_call_headers
        # The first hop still had the credential
        first_call_headers = session.request.call_args_list[0].kwargs.get("headers", {})
        assert first_call_headers.get("Authorization") == "Bearer secret-token"

    def test_keeps_authorization_on_scheme_upgrade(self):
        """Credentials survive an http -> https upgrade on default ports (requests semantics)."""
        redirect = MagicMock()
        redirect.status_code = 302
        redirect.headers = {"Location": "https://example.com/final"}
        redirect.close = MagicMock()

        final = MagicMock()
        final.status_code = 200
        final.headers = {}

        session = MagicMock()
        session.request.side_effect = [redirect, final]

        with patch(
            "semantica.ingest.ssrf.socket.getaddrinfo",
            return_value=[(None, None, None, None, ("93.184.216.34", 0))],
        ):
            request_with_ssrf_guard(
                "GET",
                "http://example.com/start",
                session=session,
                headers={"Authorization": "Bearer secret-token"},
            )

        assert session.request.call_count == 2
        second_call_headers = session.request.call_args_list[1].kwargs.get("headers", {})
        assert second_call_headers.get("Authorization") == "Bearer secret-token"

    def test_follows_safe_redirect(self):
        redirect = MagicMock()
        redirect.status_code = 302
        redirect.headers = {"Location": "https://example.com/final"}
        redirect.close = MagicMock()

        final = MagicMock()
        final.status_code = 200
        final.headers = {}

        session = MagicMock()
        session.request.side_effect = [redirect, final]

        with patch(
            "semantica.ingest.ssrf.socket.getaddrinfo",
            return_value=[(None, None, None, None, ("93.184.216.34", 0))],
        ):
            response = request_with_ssrf_guard(
                "GET",
                "https://example.com/start",
                session=session,
            )

        assert response is final
        assert session.request.call_count == 2
        assert all(
            call.kwargs.get("allow_redirects") is False
            for call in session.request.call_args_list
        )


class TestWebIngestorSSRF:
    def test_private_ip_never_reaches_urllib3(self):
        ingestor = WebIngestor(respect_robots=False, delay=0)
        attempts = []

        def intercepting_urlopen(self, method, url, **kw):
            attempts.append((self.host, self.port, url))
            raise Exception("intercepted at urllib3.urlopen")

        urls = [
            "http://10.0.0.1/",
            "http://192.168.1.1/",
            "http://127.0.0.1:9999/internal",
            "http://169.254.169.254/latest/meta-data/",
        ]
        with patch.object(pool.HTTPConnectionPool, "urlopen", intercepting_urlopen):
            for url in urls:
                attempts.clear()
                with pytest.raises(ValidationError):
                    ingestor.ingest_url(url)
                assert attempts == [], f"SSRF target reached urllib3: {url}"

    def test_file_scheme_rejected_by_semantica(self):
        ingestor = WebIngestor(respect_robots=False, delay=0)
        with pytest.raises(ValidationError, match="not permitted"):
            ingestor.ingest_url("file://localhost/etc/passwd")

    def test_allow_private_ips_permits_loopback_fetch(self):
        ingestor = WebIngestor(
            respect_robots=False, delay=0, allow_private_ips=True
        )
        with patch.object(ingestor.session, "request") as mock_request, patch.object(
            ingestor, "extract_content"
        ) as mock_extract:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.text = "ok"
            mock_resp.raise_for_status = MagicMock()
            mock_request.return_value = mock_resp
            mock_extract.return_value = MagicMock(status_code=None)

            ingestor.ingest_url("http://127.0.0.1:9/probe")

            mock_request.assert_called_once()
            assert mock_request.call_args.kwargs.get("allow_redirects") is False
            mock_extract.assert_called_once()

    def test_allow_private_ips_string_false_keeps_ssrf_on(self):
        ingestor = WebIngestor(
            respect_robots=False, delay=0, allow_private_ips="false"
        )
        assert ingestor.allow_private_ips is False
        with pytest.raises(ValidationError, match="blocked"):
            ingestor.ingest_url("http://127.0.0.1:9/probe")

    def test_allow_private_ips_string_true_opts_in(self):
        ingestor = WebIngestor(
            respect_robots=False, delay=0, allow_private_ips="true"
        )
        assert ingestor.allow_private_ips is True
        with patch.object(ingestor.session, "request") as mock_request, patch.object(
            ingestor, "extract_content"
        ) as mock_extract:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.text = "ok"
            mock_resp.raise_for_status = MagicMock()
            mock_request.return_value = mock_resp
            mock_extract.return_value = MagicMock(status_code=None)

            ingestor.ingest_url("http://127.0.0.1:9/probe")
            mock_request.assert_called_once()

    def test_redirect_to_private_ip_blocked(self):
        ingestor = WebIngestor(respect_robots=False, delay=0)
        redirect = MagicMock()
        redirect.status_code = 302
        redirect.headers = {"Location": "http://127.0.0.1/admin"}
        redirect.close = MagicMock()

        with patch.object(ingestor.session, "request", return_value=redirect), patch(
            "semantica.ingest.ssrf.socket.getaddrinfo",
            return_value=[(None, None, None, None, ("93.184.216.34", 0))],
        ):
            with pytest.raises(ValidationError, match="blocked"):
                ingestor.ingest_url("https://example.com/public")


class TestSitemapCrawlerSSRF:
    def test_private_sitemap_url_rejected(self):
        crawler = SitemapCrawler()
        with pytest.raises(ValidationError):
            crawler.parse_sitemap("http://10.0.0.1/sitemap.xml")

    def test_allow_private_ips_string_false_keeps_ssrf_on(self):
        crawler = SitemapCrawler(allow_private_ips="false")
        assert crawler.allow_private_ips is False
        with pytest.raises(ValidationError):
            crawler.parse_sitemap("http://10.0.0.1/sitemap.xml")

    def test_allow_private_ips_string_true_opts_in(self):
        crawler = SitemapCrawler(allow_private_ips="true")
        assert crawler.allow_private_ips is True

    def test_redirect_to_private_ip_blocked(self):
        crawler = SitemapCrawler()
        redirect = MagicMock()
        redirect.status_code = 302
        redirect.headers = {"Location": "http://169.254.169.254/latest/meta-data/"}
        redirect.close = MagicMock()

        with patch(
            "semantica.ingest.ssrf.requests.request", return_value=redirect
        ), patch(
            "semantica.ingest.ssrf.socket.getaddrinfo",
            return_value=[(None, None, None, None, ("93.184.216.34", 0))],
        ):
            with pytest.raises(ValidationError, match="blocked"):
                crawler.parse_sitemap("https://example.com/sitemap.xml")


class TestRESTIngestorSSRF:
    def test_private_endpoint_never_reaches_session(self):
        with patch("requests.Session") as MockSession:
            mock_session = MockSession.return_value
            ingestor = RESTIngestor()
            with pytest.raises(ValidationError):
                ingestor.ingest_endpoint("http://169.254.169.254/latest/meta-data/")
            mock_session.request.assert_not_called()

    def test_file_scheme_rejected(self):
        ingestor = RESTIngestor()
        with pytest.raises(ValidationError, match="not permitted"):
            ingestor.ingest_endpoint("file://localhost/secret")

    def test_allow_private_ips_opt_in(self):
        with patch("requests.Session") as MockSession:
            mock_session = MockSession.return_value
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"ok": True}
            mock_response.headers = {"Content-Type": "application/json"}
            mock_session.request.return_value = mock_response

            ingestor = RESTIngestor(allow_private_ips=True)
            data = ingestor.ingest_endpoint("http://127.0.0.1:8080/health")
            assert data.data == {"ok": True}
            mock_session.request.assert_called_once()
            assert mock_session.request.call_args.kwargs.get("allow_redirects") is False

    def test_allow_private_ips_string_false_keeps_ssrf_on(self):
        with patch("requests.Session") as MockSession:
            mock_session = MockSession.return_value
            ingestor = RESTIngestor(allow_private_ips="false")
            assert ingestor.allow_private_ips is False
            with pytest.raises(ValidationError, match="blocked"):
                ingestor.ingest_endpoint("http://127.0.0.1:8080/health")
            mock_session.request.assert_not_called()

    def test_allow_private_ips_string_true_opts_in(self):
        with patch("requests.Session") as MockSession:
            mock_session = MockSession.return_value
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"ok": True}
            mock_response.headers = {"Content-Type": "application/json"}
            mock_session.request.return_value = mock_response

            ingestor = RESTIngestor(allow_private_ips="true")
            assert ingestor.allow_private_ips is True
            data = ingestor.ingest_endpoint("http://127.0.0.1:8080/health")
            assert data.data == {"ok": True}
            mock_session.request.assert_called_once()

    def test_redirect_to_private_ip_blocked(self):
        with patch("requests.Session") as MockSession:
            mock_session = MockSession.return_value
            mock_session.headers = {}
            redirect = MagicMock()
            redirect.status_code = 302
            redirect.headers = {"Location": "http://127.0.0.1/secret"}
            redirect.close = MagicMock()
            mock_session.request.return_value = redirect

            ingestor = RESTIngestor()
            with patch(
                "semantica.ingest.ssrf.socket.getaddrinfo",
                return_value=[(None, None, None, None, ("93.184.216.34", 0))],
            ):
                with pytest.raises(ValidationError, match="blocked"):
                    ingestor.ingest_endpoint("https://example.com/api")
            mock_session.request.assert_called_once()
