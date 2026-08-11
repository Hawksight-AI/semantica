"""SSRF protection tests for web and API ingestors (issue #867)."""

from unittest.mock import MagicMock, patch

import pytest
import urllib3.connectionpool as pool

from semantica.ingest.api_ingestor import RESTIngestor
from semantica.ingest.ssrf import validate_url_for_request
from semantica.ingest.web_ingestor import SitemapCrawler, WebIngestor
from semantica.utils.exceptions import ValidationError


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
        with patch.object(ingestor.session, "get") as mock_get, patch.object(
            ingestor, "extract_content"
        ) as mock_extract:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.text = "ok"
            mock_resp.raise_for_status = MagicMock()
            mock_get.return_value = mock_resp
            mock_extract.return_value = MagicMock(status_code=None)

            ingestor.ingest_url("http://127.0.0.1:9/probe")

            mock_get.assert_called_once()
            mock_extract.assert_called_once()


class TestSitemapCrawlerSSRF:
    def test_private_sitemap_url_rejected(self):
        crawler = SitemapCrawler()
        with pytest.raises(ValidationError):
            crawler.parse_sitemap("http://10.0.0.1/sitemap.xml")


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
