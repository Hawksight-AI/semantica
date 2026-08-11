"""SSRF safeguards for ingest HTTP clients.

Validates outbound request URLs before they reach ``requests`` / urllib3 so
user-supplied targets cannot reach private, loopback, or link-local
addresses (including cloud metadata endpoints).
"""

from __future__ import annotations

import concurrent.futures
import ipaddress
import socket
import threading
from typing import Any, Iterable, Optional
from urllib.parse import urljoin, urlparse

import requests

from ..utils.exceptions import ValidationError

ALLOWED_URL_SCHEMES = frozenset({"http", "https"})

# Keep DNS resolution bounded so fake/unreachable hosts in tests and offline
# environments cannot hang request validation indefinitely.
_DNS_RESOLVE_TIMEOUT_SECONDS = 2.0
_DNS_EXECUTOR_WORKERS = 4

# Bound manual redirect following so open redirect chains cannot hang fetches.
_DEFAULT_MAX_REDIRECTS = 10
_REDIRECT_STATUS_CODES = frozenset({301, 302, 303, 307, 308})
_STRIP_BODY_ON_REDIRECT = frozenset({301, 302, 303})

_dns_executor: Optional[concurrent.futures.ThreadPoolExecutor] = None
_dns_executor_lock = threading.Lock()


def _shutdown_executor(executor: concurrent.futures.ThreadPoolExecutor) -> None:
    """Shut down *executor* without waiting for in-flight DNS lookups."""
    try:
        executor.shutdown(wait=False, cancel_futures=True)
    except TypeError:
        # cancel_futures was added in Python 3.9.
        executor.shutdown(wait=False)


def _get_dns_executor() -> concurrent.futures.ThreadPoolExecutor:
    """Return a process-wide executor for bounded DNS lookups."""
    global _dns_executor
    with _dns_executor_lock:
        if _dns_executor is None:
            _dns_executor = concurrent.futures.ThreadPoolExecutor(
                max_workers=_DNS_EXECUTOR_WORKERS,
                thread_name_prefix="semantica-ssrf-dns",
            )
        return _dns_executor


# Explicit blocked networks from issue #867, plus common non-routable ranges.
BLOCKED_NETWORKS = (
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),  # link-local / cloud metadata
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
)


def _ip_is_blocked(addr: ipaddress._BaseAddress) -> bool:
    if (
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_reserved
        or addr.is_multicast
        or addr.is_unspecified
    ):
        return True
    return any(addr in network for network in BLOCKED_NETWORKS)


def _hostname_resolves_to_blocked(hostname: str) -> bool:
    """Return True if any resolved address for *hostname* is blocked.

    DNS lookups run on a shared thread pool with ``Future.result(timeout=...)``.
    Do not use ``with ThreadPoolExecutor(...)`` here: on timeout, leaving the
    context waits for the hung ``getaddrinfo`` worker and defeats the bound.

    Raises:
        ValidationError: If DNS resolution fails or times out. Fail closed so
            outbound requests never proceed without confirmed safe IPs.
    """
    executor = _get_dns_executor()
    owned_executor = False
    try:
        try:
            future = executor.submit(socket.getaddrinfo, hostname, None)
        except RuntimeError:
            # Shared executor was shut down; use a throwaway pool that never
            # blocks the caller on shutdown.
            executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
            owned_executor = True
            future = executor.submit(socket.getaddrinfo, hostname, None)
        resolved: Iterable = future.result(timeout=_DNS_RESOLVE_TIMEOUT_SECONDS)
    except (socket.gaierror, concurrent.futures.TimeoutError, OSError) as exc:
        raise ValidationError(
            f"URL host '{hostname}' could not be resolved safely "
            "(DNS error or timeout); request blocked"
        ) from exc
    finally:
        if owned_executor:
            _shutdown_executor(executor)

    for info in resolved:
        sockaddr = info[4]
        addr = ipaddress.ip_address(sockaddr[0])
        if _ip_is_blocked(addr):
            return True
    return False


def validate_url_for_request(
    url: str, *, allow_private_ips: bool = False
) -> None:
    """Validate that *url* is safe to fetch over HTTP(S).

    Args:
        url: Absolute URL to validate.
        allow_private_ips: When True, skip private/loopback/link-local checks
            (for trusted internal deployments).

    Raises:
        ValidationError: If the scheme is not http/https, the URL is malformed,
            or the host targets a blocked address space.
    """
    if not isinstance(url, str) or not url.strip():
        raise ValidationError("URL must be a non-empty string")

    parsed = urlparse(url.strip())
    scheme = (parsed.scheme or "").lower()
    if scheme not in ALLOWED_URL_SCHEMES:
        raise ValidationError(
            f"URL scheme '{parsed.scheme}' is not permitted. "
            "Only http and https are allowed."
        )
    if not parsed.netloc:
        raise ValidationError(
            f"Invalid URL format: {url}. "
            "URL must include scheme (http/https) and netloc (domain)."
        )

    host = parsed.hostname
    if not host:
        raise ValidationError(
            f"Invalid URL format: {url}. "
            "URL must include a hostname."
        )

    if allow_private_ips:
        return

    lowered = host.lower().rstrip(".")
    if lowered == "localhost" or lowered.endswith(".localhost"):
        raise ValidationError(f"URL host is not allowed: {host}")

    try:
        literal_ip = ipaddress.ip_address(host)
    except ValueError:
        literal_ip = None

    if literal_ip is not None:
        if _ip_is_blocked(literal_ip):
            raise ValidationError(f"URL points to a blocked address: {host}")
        return

    if _hostname_resolves_to_blocked(host):
        raise ValidationError(
            f"URL host '{host}' resolves to a blocked (private/loopback/"
            "link-local) address"
        )


def request_with_ssrf_guard(
    method: str,
    url: str,
    *,
    session: Optional[requests.Session] = None,
    allow_private_ips: bool = False,
    max_redirects: int = _DEFAULT_MAX_REDIRECTS,
    **kwargs: Any,
) -> requests.Response:
    """Perform an HTTP request with SSRF checks on *url* and every redirect.

    ``requests`` follows redirects by default, which would allow a validated
    public URL to bounce into private/loopback/link-local space. This helper
    disables automatic redirects and re-validates each ``Location`` target
    before issuing the next hop.
    """
    kwargs = dict(kwargs)
    kwargs.pop("allow_redirects", None)

    validate_url_for_request(url, allow_private_ips=allow_private_ips)

    requester = session.request if session is not None else requests.request
    current_url = url
    current_method = method.upper()
    redirects_followed = 0

    while True:
        response = requester(
            current_method,
            current_url,
            allow_redirects=False,
            **kwargs,
        )

        if response.status_code not in _REDIRECT_STATUS_CODES:
            return response

        if redirects_followed >= max_redirects:
            response.close()
            raise ValidationError(
                f"Exceeded maximum redirects ({max_redirects}) while "
                f"fetching '{url}'"
            )

        location = response.headers.get("Location")
        if not location or not str(location).strip():
            response.close()
            raise ValidationError(
                f"Redirect from '{current_url}' is missing a Location header"
            )

        next_url = urljoin(current_url, str(location).strip())
        validate_url_for_request(next_url, allow_private_ips=allow_private_ips)

        # Match requests' historical method rewriting for 301/302/303.
        if (
            response.status_code in _STRIP_BODY_ON_REDIRECT
            and current_method not in {"GET", "HEAD"}
        ):
            current_method = "GET"
            for key in ("data", "json", "files"):
                kwargs.pop(key, None)

        # Params apply to the original request URL only; Location is authoritative.
        kwargs.pop("params", None)

        response.close()
        current_url = next_url
        redirects_followed += 1
