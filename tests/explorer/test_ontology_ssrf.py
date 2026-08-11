"""Regression tests for outbound URL fetching in ontology.py (SSRF hardening).

`_fetch_url_sync` disables `requests`' automatic redirect following and
re-validates every hop with `_validate_fetch_url` (see GHSA-8c7v-62gr-hj6g:
unvalidated redirect targets previously let a public first hop 302 the
server into fetching cloud metadata / loopback services).

These tests cover the redirect-handling logic itself: relative `Location`
headers must resolve correctly instead of being rejected outright, redirect
targets that resolve to private/loopback addresses must still be blocked,
and every response must be closed (no leaked connections across hops).
"""

import socket
from unittest.mock import MagicMock, patch

import pytest

from semantica.explorer.routes import ontology as ontology_mod


def _fake_getaddrinfo(host, *args, **kwargs):
    # These tests are about the redirect-handling logic, not the address
    # classifier itself, so every host resolves to a public IP unless a
    # test overrides the side_effect to simulate an internal target.
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]


def _make_response(is_redirect=False, is_permanent=False, location=None, body=b"ok"):
    resp = MagicMock()
    resp.is_redirect = is_redirect
    resp.is_permanent_redirect = is_permanent
    resp.headers = {"Location": location} if location else {}
    resp.raise_for_status = MagicMock()
    resp.iter_content = MagicMock(return_value=iter([body]))
    resp.close = MagicMock()
    return resp


@patch.object(ontology_mod.socket, "getaddrinfo", side_effect=_fake_getaddrinfo)
def test_relative_redirect_location_is_resolved(mock_getaddrinfo):
    """A relative Location header (e.g. '/ontology.ttl') must resolve against
    the current URL via urljoin, not be rejected as a malformed URL."""
    redirect_resp = _make_response(is_redirect=True, location="/ontology.ttl")
    final_resp = _make_response(body=b"final content")

    with patch("requests.get", side_effect=[redirect_resp, final_resp]) as mock_get:
        result = ontology_mod._fetch_url_sync("http://example.org/start")

    assert result == b"final content"
    second_call_url = mock_get.call_args_list[1].args[0]
    assert second_call_url == "http://example.org/ontology.ttl"
    redirect_resp.close.assert_called_once()
    final_resp.close.assert_called_once()


@patch.object(ontology_mod.socket, "getaddrinfo", side_effect=_fake_getaddrinfo)
def test_redirect_to_private_ip_is_rejected(mock_getaddrinfo):
    """Re-validation must reject a redirect target resolving to a private
    address even though the first hop was a validated public URL — this is
    the exact GHSA-8c7v scenario: public first hop, malicious redirect."""
    def getaddrinfo_side_effect(host, *a, **k):
        if host == "internal.example":
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("169.254.169.254", 0))]
        return _fake_getaddrinfo(host, *a, **k)

    mock_getaddrinfo.side_effect = getaddrinfo_side_effect
    redirect_resp = _make_response(is_redirect=True, location="http://internal.example/latest/meta-data/")

    with patch("requests.get", side_effect=[redirect_resp]):
        with pytest.raises(ontology_mod.HTTPException) as exc_info:
            ontology_mod._fetch_url_sync("http://example.org/start")

    assert exc_info.value.status_code == 422
    redirect_resp.close.assert_called_once()


@patch.object(ontology_mod.socket, "getaddrinfo", side_effect=_fake_getaddrinfo)
def test_final_response_is_closed(mock_getaddrinfo):
    final_resp = _make_response(body=b"content")
    with patch("requests.get", side_effect=[final_resp]):
        ontology_mod._fetch_url_sync("http://example.org/start")
    final_resp.close.assert_called_once()


@patch.object(ontology_mod.socket, "getaddrinfo", side_effect=_fake_getaddrinfo)
def test_redirect_chain_exceeding_cap_is_rejected(mock_getaddrinfo):
    responses = [_make_response(is_redirect=True, location=f"/hop{i}") for i in range(10)]
    with patch("requests.get", side_effect=responses):
        with pytest.raises(ontology_mod.HTTPException) as exc_info:
            ontology_mod._fetch_url_sync("http://example.org/start")
    assert exc_info.value.status_code == 502
    assert all(r.close.called for r in responses[:6])
