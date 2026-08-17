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

_TRUE_STRINGS = frozenset({"1", "true", "yes", "on"})
_FALSE_STRINGS = frozenset({"0", "false", "no", "off"})

# Keep DNS resolution bounded so fake/unreachable hosts in tests and offline
# environments cannot hang request validation indefinitely.
_DNS_RESOLVE_TIMEOUT_SECONDS = 2.0
_DNS_EXECUTOR_WORKERS = 4

# Bound manual redirect following so open redirect chains cannot hang fetches.
_DEFAULT_MAX_REDIRECTS = 10
_REDIRECT_STATUS_CODES = frozenset({301, 302, 303, 307, 308})
_STRIP_BODY_ON_REDIRECT = frozenset({301, 302, 303})

# Standard port per scheme (mirrors requests' DEFAULT_PORTS).
_DEFAULT_PORTS = {"http": 80, "https": 443}


def _should_strip_auth(old_url: str, new_url: str) -> bool:
    """Decide whether credentials must not follow a redirect.

    Mirrors ``requests.utils.should_strip_auth``: credentials are stripped
    when the hostname changes, when the port changes (outside default
    ports), or on an https -> http downgrade on the same host. The single
    exception is an http -> https upgrade on default ports, which requests
    treats as safe to keep the credential for.
    """
    old_parsed = urlparse(old_url)
    new_parsed = urlparse(new_url)

    if old_parsed.hostname != new_parsed.hostname:
        return True

    # Special case: allow http -> https redirect on standard ports.
    if (
        old_parsed.scheme == "http"
        and old_parsed.port in (80, None)
        and new_parsed.scheme == "https"
        and new_parsed.port in (443, None)
    ):
        return False

    changed_port = old_parsed.port != new_parsed.port
    changed_scheme = old_parsed.scheme != new_parsed.scheme
    default_port = (_DEFAULT_PORTS.get(old_parsed.scheme), None)
    if (
        not changed_scheme
        and old_parsed.port in default_port
        and new_parsed.port in default_port
    ):
        return False

    return changed_port or changed_scheme

_dns_executor: Optional[concurrent.futures.ThreadPoolExecutor] = None
_dns_executor_lock = threading.Lock()


def parse_bool(value: Any, default: bool = False) -> bool:
    """Parse a config value into a bool without truthy-string pitfalls.

    ``bool('false')`` is ``True`` in Python, which would silently disable SSRF
    protections when string-typed config reaches ingestors. This helper accepts
    only explicit bools and a small allowlist of string/int forms.

    Args:
        value: Config value to interpret. ``None`` yields *default*.
        default: Value returned when *value* is ``None``.

    Raises:
        ValidationError: If *value* is not a recognized boolean form.
    """
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        if value == 1:
            return True
        if value == 0:
            return False
        raise ValidationError(f"Invalid boolean value: {value!r}")
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in _TRUE_STRINGS:
            return True
        if normalized in _FALSE_STRINGS:
            return False
        raise ValidationError(f"Invalid boolean value: {value!r}")
    raise ValidationError(
        f"Invalid boolean type: {type(value).__name__} ({value!r})"
    )


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
    allow_private_ips_on_redirect: Optional[bool] = None,
    max_redirects: int = _DEFAULT_MAX_REDIRECTS,
    **kwargs: Any,
) -> requests.Response:
    """Perform an HTTP request with SSRF checks on *url* and every redirect.

    ``requests`` follows redirects by default, which would allow a validated
    public URL to bounce into private/loopback/link-local space. This helper
    disables automatic redirects and re-validates each ``Location`` target
    before issuing the next hop.

    ``allow_private_ips`` trusts the caller's own *url* (e.g. an
    operator-configured internal endpoint). That trust follows a redirect
    only when the redirect target's host matches the original host (e.g. a
    same-host path redirect on a private/localhost server); a redirect to a
    *different* host is validated with ``allow_private_ips_on_redirect``
    instead, which defaults to ``allow_private_ips`` for backward
    compatibility but can be pinned to ``False`` by callers that want to
    trust only the original host and never extend private-IP eligibility to
    any other host a redirect chain might reach — otherwise a private-IP-
    eligible endpoint could be tricked into redirecting into arbitrary
    internal address space (e.g. cloud metadata) the caller never
    configured.

    Authorization / credential-header handling (issue #947)
    --------------------------------------------------------
    Credentials are stripped from **all** sources that ``requests`` can use to
    attach an ``Authorization`` header whenever a redirect changes origin:

    1. ``kwargs["headers"]`` — per-request header dict (already handled).
    2. ``session.headers`` — session-level headers that ``requests`` merges
       automatically; cleared for the hop and restored via ``finally``.
    3. ``kwargs["auth"]`` — per-request auth tuple/callable; removed from the
       local ``kwargs`` copy when stripping is required. This copy never
       escapes to the caller, so there is nothing to restore.
    4. ``session.auth`` — session-level auth handler that ``requests`` merges
       via ``merge_setting(auth, self.auth)`` inside ``prepare_request``;
       cleared for the hop and restored via ``finally``.
    5. ``session.trust_env`` — when ``True``, ``requests`` reads ``~/.netrc``
       for the *redirect target* host and calls ``prepare_auth()`` with those
       credentials even after sources 3 and 4 are cleared; disabled for
       cross-origin hops and restored via ``finally``.

    Leaving any one of these intact allows ``requests`` to re-attach
    credentials on the hop to the foreign origin, defeating the header-level
    strip.

    Session state that was removed is unconditionally restored in a ``finally``
    block so the session is left in its original state after this call returns,
    regardless of how it exits (normal return, exception, redirect cap).  The
    loop is sequential and single-threaded within one call, so the mutation is
    safe as long as the caller does not share the session across concurrent
    threads (the standard Semantica pattern: one session per ingestor instance).

    Once credentials have been stripped for a cross-origin hop they are NOT
    re-added for subsequent hops in the same chain, even if a later hop
    happens to point back to the original host.  This prevents credential
    resurrection via crafted multi-hop redirect chains.
    """
    kwargs = dict(kwargs)
    kwargs.pop("allow_redirects", None)

    redirect_allow_private_ips = (
        allow_private_ips
        if allow_private_ips_on_redirect is None
        else allow_private_ips_on_redirect
    )
    _original_host = (urlparse(url).hostname or "").lower()

    validate_url_for_request(url, allow_private_ips=allow_private_ips)

    requester = session.request if session is not None else requests.request
    current_url = url
    current_method = method.upper()
    redirects_followed = 0

    # -- issue #947: snapshot every session-level credential source so we can
    #    restore them unconditionally when this call exits.
    _SENSITIVE = ("Authorization", "Proxy-Authorization")
    _session_auth_backup: dict = {}
    _session_auth_handler_backup: Any = None  # session.auth backup
    _session_trust_env_backup: bool = True    # session.trust_env backup

    if session is not None:
        for _h in _SENSITIVE:
            # requests stores session headers in a case-insensitive dict;
            # .get() matches regardless of the casing used at insertion time.
            _val = session.headers.get(_h)
            if _val is not None:
                _session_auth_backup[_h] = _val
        # Snapshot session.auth (HTTPBasicAuth, tuple, callable, or None).
        _session_auth_handler_backup = session.auth
        # Snapshot session.trust_env (controls .netrc / env proxy lookup).
        _session_trust_env_backup = session.trust_env

    # Track whether credentials have been stripped for this redirect chain.
    # Once stripped they must not reappear on any subsequent hop.
    _auth_stripped = False

    try:
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
            next_host = (urlparse(next_url).hostname or "").lower()
            # A redirect back to the original host inherits the caller's
            # trust in that host (e.g. a same-host path redirect on a
            # private/localhost MCP server). A redirect to a *different*
            # host must not inherit that trust, even if the original host
            # was private/internal — otherwise a compromised or malicious
            # endpoint could redirect into arbitrary private address space
            # (e.g. cloud metadata) the caller never configured.
            hop_allow_private_ips = (
                allow_private_ips
                if next_host and next_host == _original_host
                else redirect_allow_private_ips
            )
            validate_url_for_request(next_url, allow_private_ips=hop_allow_private_ips)

            # Do not leak sensitive headers or auth handlers to a different
            # origin on redirects.  All four credential sources are cleared:
            #   • kwargs["headers"]   — per-request header dict
            #   • session.headers     — session-level header dict
            #   • kwargs["auth"]      — per-request auth tuple/callable
            #   • session.auth        — session-level auth handler
            #
            # Once stripped (_auth_stripped=True), credentials stay absent for
            # the remainder of the chain — even if a later hop targets the
            # original host — to prevent credential resurrection.
            if _auth_stripped or _should_strip_auth(current_url, next_url):
                _auth_stripped = True

                # 1. Strip from per-request kwargs headers.
                kwargs = dict(kwargs)
                headers = dict(kwargs.get("headers") or {})
                for sensitive in _SENSITIVE:
                    headers.pop(sensitive, None)
                    # Also remove any case variant the caller may have used
                    # (e.g. "authorization" or "AUTHORIZATION").
                    for key in list(headers):
                        if key.lower() == sensitive.lower():
                            del headers[key]
                kwargs["headers"] = headers

                # 2. Strip per-request auth kwarg so requests cannot call
                #    prepare_auth() with the caller's credential on this hop.
                kwargs.pop("auth", None)

                # 3. Strip session-level headers so requests cannot re-inject
                #    them when merging session + per-request headers for this hop.
                if session is not None:
                    for sensitive in _SENSITIVE:
                        # CaseInsensitiveDict.pop(key, None) handles any casing.
                        session.headers.pop(sensitive, None)

                    # 4. Clear session.auth so prepare_request's merge_setting()
                    #    cannot fall back to the session-level auth handler and
                    #    reattach credentials on the foreign-origin hop.
                    session.auth = None

                    # 5. Disable .netrc / environment-proxy credential lookup so
                    #    requests cannot inject credentials from ~/.netrc for the
                    #    redirect target host on this hop.
                    session.trust_env = False

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

    finally:
        # Unconditionally restore every session credential source we touched,
        # so the session is in its original state after this call returns or raises.
        if session is not None:
            if _session_auth_backup:
                for _h, _v in _session_auth_backup.items():
                    session.headers[_h] = _v
            # Restore session.auth to whatever it was before this call.
            session.auth = _session_auth_handler_backup
            # Restore session.trust_env (.netrc / env-proxy lookup flag).
            session.trust_env = _session_trust_env_backup
