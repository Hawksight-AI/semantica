"""Regression tests for DNS check-then-use (TOCTOU) hardening in the
ontology URL fetcher (GHSA-8c7v-62gr-hj6g's secondary "smaller" gap).

`_validate_fetch_url` resolves and validates a hostname once; if the actual
HTTP client resolved it again independently at connect time, a low-TTL or
rebinding DNS answer could differ between the two lookups, reopening the
SSRF window the validation exists to close. `_make_pinned_session` closes
this by pinning the connection pool's `host` directly to the already-
validated IP (bypassing DNS resolution for the connection entirely), while
explicitly restoring the real hostname as the outgoing HTTP `Host` header
and, for HTTPS, the TLS SNI `server_hostname` / `assert_hostname` — so the
connection reaches the pinned IP but still presents (and verifies against)
the original hostname's identity.

test_ontology_ssrf.py covers the redirect-handling logic around this with
mocks; this file proves the pinning mechanism itself works end-to-end
against real local servers, with no DNS mocking at all — the test hostname
is never resolved, which is exactly the property being verified. It also
includes a negative control (mismatched cert hostname) proving TLS
verification is genuinely enforced against the real hostname, not silently
bypassed or checked against the pinned IP instead.
"""

import http.server
import socket
import threading

import pytest

from semantica.explorer.routes import ontology as ontology_mod


def _start_local_server():
    captured = {}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            captured["host_header"] = self.headers.get("Host")
            body = b"pinned response"
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_args):
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread, captured


def test_pinned_session_connects_to_pinned_ip_without_resolving_hostname():
    """A session built by _make_pinned_session must reach the pinned IP
    directly. The request URL uses a hostname that cannot be resolved via
    real DNS ('.invalid' is reserved by RFC 2606) — if pinning weren't
    working, this request would fail with a name-resolution error instead
    of reaching the local server, since nothing else could route it there.
    """
    server, thread, captured = _start_local_server()
    port = server.server_address[1]
    url = f"http://pinned-test.invalid:{port}/resource"
    try:
        session = ontology_mod._make_pinned_session(["127.0.0.1"], url)
        try:
            resp = session.get(url, timeout=5)
            assert resp.status_code == 200
            assert resp.content == b"pinned response"
        finally:
            session.close()
    finally:
        server.shutdown()
        thread.join(timeout=2)

    # Host header must still be the original hostname, not the pinned IP —
    # proving connection target and presented identity are decoupled
    # correctly (this is what keeps virtual hosting / TLS SNI correct).
    assert captured["host_header"] == f"pinned-test.invalid:{port}"


def test_pinned_session_ignores_a_different_real_resolution():
    """Even if the hostname *does* resolve to something else via real DNS,
    the pinned session must still go to the pinned IP — this is the actual
    TOCTOU property: the connection uses what was validated, not whatever
    a fresh lookup returns. 'localhost' reliably resolves to a loopback
    address, which is deliberately NOT where our test server listens on
    (127.0.0.1 specifically) — but since Windows/most stacks map
    'localhost' to 127.0.0.1 too, use a distinct high loopback address
    (127.0.0.2) for the server so a real 'localhost' resolution (127.0.0.1)
    provably would NOT reach it, isolating the assertion to pinning alone.
    """
    captured = {}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            captured["host_header"] = self.headers.get("Host")
            body = b"pinned via explicit ip"
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_args):
            pass

    try:
        server = http.server.HTTPServer(("127.0.0.2", 0), Handler)
    except OSError:
        # 127.0.0.2 isn't bindable in this environment (uncommon, but
        # possible in some sandboxes) — skip rather than false-fail.
        import pytest
        pytest.skip("127.0.0.2 is not bindable in this environment")

    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://localhost:{port}/resource"
    try:
        session = ontology_mod._make_pinned_session(["127.0.0.2"], url)
        try:
            resp = session.get(url, timeout=5)
            assert resp.status_code == 200
            assert resp.content == b"pinned via explicit ip"
        finally:
            session.close()
    finally:
        server.shutdown()
        thread.join(timeout=2)

    assert captured["host_header"] == f"localhost:{port}"


def test_pinned_session_falls_back_across_multiple_pinned_ips():
    """A hostname can have multiple A/AAAA records; pinning to only the
    first-returned address means a fetch fails outright if that specific
    address happens to be unreachable even though a later one would work.
    _make_pinned_session must fall back through every pinned IP in order.
    """
    server, thread, captured = _start_local_server()
    port = server.server_address[1]
    url = f"http://pinned-test.invalid:{port}/resource"
    # 127.0.0.3 has nothing listening on this port — connection refused,
    # forcing a fallback to the second (real) address.
    unreachable_ip = "127.0.0.3"
    try:
        session = ontology_mod._make_pinned_session([unreachable_ip, "127.0.0.1"], url)
        try:
            resp = session.get(url, timeout=5)
            assert resp.status_code == 200
            assert resp.content == b"pinned response"
        finally:
            session.close()
    finally:
        server.shutdown()
        thread.join(timeout=2)


def test_pinned_session_raises_when_every_pinned_ip_is_unreachable():
    """If none of the pinned IPs are reachable, the session must raise
    rather than silently falling back to resolving the hostname itself
    (which would reopen the exact TOCTOU window pinning exists to close)."""
    import requests

    url = "http://pinned-test.invalid:9/resource"  # port 9 (discard) — nothing listens
    session = ontology_mod._make_pinned_session(["127.0.0.3", "127.0.0.4"], url)
    try:
        with pytest.raises(requests.exceptions.ConnectionError):
            session.get(url, timeout=5)
    finally:
        session.close()


def test_pinned_session_disables_environment_proxy_trust():
    """A pinned session must never honor HTTP_PROXY/HTTPS_PROXY env vars —
    a proxy would perform its own DNS resolution of the target host outside
    this process's control, reopening the exact TOCTOU window pinning
    exists to close."""
    session = ontology_mod._make_pinned_session(["127.0.0.1"], "http://example.org/")
    try:
        assert session.trust_env is False
    finally:
        session.close()


def test_pinned_session_ignores_env_proxy_and_connects_directly(monkeypatch):
    """End-to-end: even with HTTP_PROXY pointed at an address that would
    fail if contacted, a pinned session must reach the real local server
    directly — proving the env var is genuinely not consulted, not just
    that the trust_env flag is set."""
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.5:1/")  # would fail if ever used
    server, thread, _captured = _start_local_server()
    port = server.server_address[1]
    url = f"http://pinned-test.invalid:{port}/resource"
    try:
        session = ontology_mod._make_pinned_session(["127.0.0.1"], url)
        try:
            resp = session.get(url, timeout=5)
            assert resp.status_code == 200
            assert resp.content == b"pinned response"
        finally:
            session.close()
    finally:
        server.shutdown()
        thread.join(timeout=2)


def test_pinned_session_fails_closed_if_a_proxy_is_explicitly_forced():
    """Backstop: if a proxy is somehow still configured on the session
    despite trust_env=False (e.g. set explicitly, as a future code path
    might), the adapter must fail closed with a clear error rather than
    silently connecting through the proxy unpinned."""
    from fastapi import HTTPException

    session = ontology_mod._make_pinned_session(["127.0.0.1"], "http://example.org/")
    session.proxies = {"http": "http://127.0.0.5:1"}
    try:
        with pytest.raises(HTTPException) as exc_info:
            session.get("http://example.org/", timeout=5)
        assert exc_info.value.status_code == 502
    finally:
        session.close()


def test_validate_fetch_url_returns_the_resolved_ip():
    """_validate_fetch_url must return every IP it validated, so callers can
    pin the connection to them (with fallback across all of them)."""
    def fake_getaddrinfo(host, *_a, **_k):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]

    import unittest.mock as mock
    with mock.patch.object(ontology_mod.socket, "getaddrinfo", side_effect=fake_getaddrinfo):
        resolved_ips = ontology_mod._validate_fetch_url("http://example.org/ontology.ttl")

    assert resolved_ips == ["93.184.216.34"]


def test_validate_fetch_url_returns_all_validated_ips_deduplicated():
    """A hostname with multiple A/AAAA records must return every distinct
    validated address, in resolution order, so the caller can fall back
    across all of them rather than failing if only the first is
    unreachable."""
    def fake_getaddrinfo(host, *_a, **_k):
        return [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0)),
            (socket.AF_INET, socket.SOCK_DGRAM, 17, "", ("93.184.216.34", 0)),  # duplicate, different socktype
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.35", 0)),
        ]

    import unittest.mock as mock
    with mock.patch.object(ontology_mod.socket, "getaddrinfo", side_effect=fake_getaddrinfo):
        resolved_ips = ontology_mod._validate_fetch_url("http://example.org/ontology.ttl")

    assert resolved_ips == ["93.184.216.34", "93.184.216.35"]


def test_validate_fetch_url_still_rejects_private_ip():
    """Confirm the pinning refactor didn't loosen the original address
    classification — a hostname resolving to a private/internal address
    must still be rejected before any IP is returned."""
    import ipaddress
    import unittest.mock as mock

    import pytest
    from fastapi import HTTPException

    def fake_getaddrinfo(host, *_a, **_k):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("169.254.169.254", 0))]

    with mock.patch.object(ontology_mod.socket, "getaddrinfo", side_effect=fake_getaddrinfo):
        with pytest.raises(HTTPException) as exc_info:
            ontology_mod._validate_fetch_url("http://attacker.example/ontology.ttl")

    assert exc_info.value.status_code == 422


# ---------------------------------------------------------------------------
# HTTPS: SNI + certificate hostname verification must use the real hostname,
# not the pinned IP — this is the highest-risk part of pinning to get wrong,
# since a mistake here could silently weaken TLS verification rather than
# just breaking connectivity. Requires the optional `cryptography` package
# to mint a throwaway self-signed cert; skipped gracefully without it.
# ---------------------------------------------------------------------------

def _make_self_signed_cert(hostname: str, tmp_path):
    import datetime

    pytest.importorskip("cryptography")
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, hostname)])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=1))
        .add_extension(x509.SubjectAlternativeName([x509.DNSName(hostname)]), critical=False)
        .sign(key, hashes.SHA256())
    )

    cert_path = tmp_path / "cert.pem"
    key_path = tmp_path / "key.pem"
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    return str(cert_path), str(key_path)


def _start_local_https_server(cert_path, key_path):
    import ssl

    captured = {}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            captured["host_header"] = self.headers.get("Host")
            body = b"tls pinned response"
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_args):
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    ssl_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ssl_ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ssl_ctx.load_cert_chain(cert_path, key_path)
    server.socket = ssl_ctx.wrap_socket(server.socket, server_side=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread, captured


def test_pinned_https_session_verifies_against_real_hostname_not_pinned_ip(tmp_path):
    """A pinned HTTPS connection must present + verify SNI/cert against the
    real hostname, even though the socket connects to the pinned IP. The
    cert's SAN is the hostname, never '127.0.0.1' — if pinning verified
    against the IP instead (or against nothing), this would either fail
    for the wrong reason or silently succeed with no real verification."""
    cert_path, key_path = _make_self_signed_cert("pinned-tls-test.invalid", tmp_path)
    server, thread, captured = _start_local_https_server(cert_path, key_path)
    port = server.server_address[1]
    url = f"https://pinned-tls-test.invalid:{port}/resource"
    try:
        session = ontology_mod._make_pinned_session(["127.0.0.1"], url)
        try:
            resp = session.get(url, timeout=5, verify=cert_path)
        finally:
            session.close()
    finally:
        server.shutdown()
        thread.join(timeout=2)

    assert resp.status_code == 200
    assert resp.content == b"tls pinned response"
    assert captured["host_header"] == f"pinned-tls-test.invalid:{port}"


def test_pinned_https_session_rejects_hostname_mismatch(tmp_path):
    """Negative control: requesting a hostname that does NOT match the
    cert's SAN must still fail verification — proving pinning doesn't
    silently bypass or misdirect certificate hostname checking."""
    cert_path, key_path = _make_self_signed_cert("pinned-tls-test.invalid", tmp_path)
    server, thread, _captured = _start_local_https_server(cert_path, key_path)
    port = server.server_address[1]
    url = f"https://wrong-name.invalid:{port}/resource"
    try:
        session = ontology_mod._make_pinned_session(["127.0.0.1"], url)
        try:
            import requests
            with pytest.raises(requests.exceptions.SSLError):
                session.get(url, timeout=5, verify=cert_path)
        finally:
            session.close()
    finally:
        server.shutdown()
        thread.join(timeout=2)
