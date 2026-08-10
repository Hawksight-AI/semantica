"""SSRF safeguards for ingest HTTP clients.

Validates outbound request URLs before they reach ``requests`` / urllib3 so
user-supplied targets cannot reach private, loopback, or link-local
addresses (including cloud metadata endpoints).
"""

from __future__ import annotations

import concurrent.futures
import ipaddress
import socket
from typing import Iterable
from urllib.parse import urlparse

from ..utils.exceptions import ValidationError

ALLOWED_URL_SCHEMES = frozenset({"http", "https"})

# Keep DNS resolution bounded so fake/unreachable hosts in tests and offline
# environments cannot hang request validation indefinitely.
_DNS_RESOLVE_TIMEOUT_SECONDS = 2.0

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
    """Return True if any resolved address for *hostname* is blocked."""
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(socket.getaddrinfo, hostname, None)
            resolved: Iterable = future.result(timeout=_DNS_RESOLVE_TIMEOUT_SECONDS)
    except (socket.gaierror, concurrent.futures.TimeoutError, OSError):
        # DNS failure / timeout — leave the error to requests on the actual fetch.
        return False

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
