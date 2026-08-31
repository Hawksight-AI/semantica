"""Tests for the Anthropic LLM provider wrapper (semantica.llms.Anthropic)."""

from unittest.mock import MagicMock

import pytest

from semantica.llms import Anthropic
from semantica.utils.exceptions import ProcessingError


def test_construction_stores_model_and_api_key():
    """Anthropic(...) should not crash and should remember what it was given."""
    claude = Anthropic(model="claude-sonnet-4-6", api_key="fake-key")
    assert claude.model == "claude-sonnet-4-6"
    assert claude.api_key == "fake-key"


def test_is_available_false_with_no_key(monkeypatch):
    """Without a real key, is_available() must be a real False, not truthy junk.

    api_key=None alone isn't enough to prove this: AnthropicProvider falls
    back to the ANTHROPIC_API_KEY environment variable, so this test has to
    clear it too or it would pass/fail depending on whoever's machine or CI
    runner happens to run it.
    """
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    claude = Anthropic(api_key=None)
    assert claude.is_available() is False


def test_generate_raises_clear_error_when_unavailable(monkeypatch):
    """generate() must fail loudly.

    Clears ANTHROPIC_API_KEY for the same reason as test_is_available_false_with_no_key:
    otherwise this test flakes depending on whether the runner's environment has a key set.
    """
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    claude = Anthropic(api_key=None)
    with pytest.raises(ProcessingError, match="Anthropic provider not available"):
        claude.generate("hello")


def test_generate_forwards_to_the_real_provider_when_available():
    """When available, generate() must actually call through to the real provider."""
    claude = Anthropic(api_key="fake-key")

    claude.provider = MagicMock()
    claude.provider.is_available.return_value = True
    claude.provider.generate.return_value = "a fake response"

    result = claude.generate("hello", temperature=0.5)

    assert result == "a fake response"
    claude.provider.generate.assert_called_once_with("hello", temperature=0.5)


def test_generate_structured_forwards_to_the_real_provider():
    claude = Anthropic(api_key="fake-key")
    claude.provider = MagicMock()
    claude.provider.is_available.return_value = True
    claude.provider.generate_structured.return_value = {"key": "value"}

    result = claude.generate_structured("hello")

    assert result == {"key": "value"}
    claude.provider.generate_structured.assert_called_once_with("hello")


def test_generate_typed_forwards_schema_and_max_retries():
    claude = Anthropic(api_key="fake-key")
    claude.provider = MagicMock()
    claude.provider.is_available.return_value = True
    fake_schema = object()
    claude.provider.generate_typed.return_value = "typed result"

    result = claude.generate_typed("hello", fake_schema, max_retries=5)

    assert result == "typed result"
    claude.provider.generate_typed.assert_called_once_with(
        "hello", fake_schema, max_retries=5
    )


def test_generate_structured_raises_clear_error_when_unavailable(monkeypatch):
    """generate_structured() must fail loudly, same as generate()."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    claude = Anthropic(api_key=None)
    with pytest.raises(ProcessingError, match="Anthropic provider not available"):
        claude.generate_structured("hello")


def test_generate_typed_raises_clear_error_when_unavailable(monkeypatch):
    """generate_typed() must fail loudly, same as generate() and generate_structured()."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    claude = Anthropic(api_key=None)
    with pytest.raises(ProcessingError, match="Anthropic provider not available"):
        claude.generate_typed("hello", object())
