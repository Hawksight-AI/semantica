"""
Shared pytest fixtures for the ingest test suite.

The ``mock_dns`` fixture is applied to *every* test in this directory
(``autouse=True``).  It stubs out ``socket.getaddrinfo`` inside the SSRF
guard module so that unit tests that mock ``requests.Session.request`` do not
accidentally hit the network for DNS resolution — which would fail in offline
CI environments and cause intermittent timeouts.

Tests that explicitly need to exercise DNS-related behaviour (e.g. checking
that a hostname resolving to a private IP is blocked) override this fixture
by patching ``semantica.ingest.ssrf.socket.getaddrinfo`` with their own
``side_effect`` *inside* the test body; that inner patch wins because
``unittest.mock.patch`` applies patches in innermost-last order.
"""
from __future__ import annotations

import socket
from unittest.mock import patch

import pytest

_PUBLIC_IP = "93.184.216.34"  # example.com — a safe, routable public address


@pytest.fixture(autouse=True)
def mock_dns():
    """Map every hostname to a safe public IP for the duration of each test."""
    with patch(
        "semantica.ingest.ssrf.socket.getaddrinfo",
        return_value=[
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", (_PUBLIC_IP, 0))
        ],
    ):
        yield
