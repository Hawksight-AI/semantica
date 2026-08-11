"""Shared fixtures for explorer API tests.

Most of this suite predates the API-key auth layer added for
GHSA-j4mq-hprp-987v and exercises route logic, not authentication. Default
every test under tests/explorer/ to SEMANTICA_ALLOW_ANONYMOUS=true so those
tests keep talking to the Explorer without needing an X-API-Key header.
Auth-specific tests (test_explorer_auth.py) override this per-test via the
same `monkeypatch` fixture.
"""

import pytest


@pytest.fixture(autouse=True)
def _default_to_anonymous_explorer_access(monkeypatch):
    monkeypatch.setenv("SEMANTICA_ALLOW_ANONYMOUS", "true")
    monkeypatch.delenv("SEMANTICA_API_KEY", raising=False)
