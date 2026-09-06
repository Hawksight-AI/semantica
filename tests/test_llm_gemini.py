"""Tests for the Gemini LLM provider wrapper (semantica.llms.Gemini)."""

from unittest.mock import MagicMock

import pytest

from semantica.llms import Gemini
from semantica.utils.exceptions import ProcessingError


def test_construction_stores_model_and_api_key():
    gemini = Gemini(model="gemini-pro", api_key="fake-key")
    assert gemini.model == "gemini-pro"
    assert gemini.api_key == "fake-key"


def test_is_available_false_with_no_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    gemini = Gemini(api_key=None)
    assert gemini.is_available() is False


def test_generate_raises_clear_error_when_unavailable(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    gemini = Gemini(api_key=None)
    with pytest.raises(ProcessingError, match="Gemini provider not available"):
        gemini.generate("hello")


def test_generate_forwards_to_the_real_provider_when_available():
    gemini = Gemini(api_key="fake-key")
    gemini.provider = MagicMock()
    gemini.provider.is_available.return_value = True
    gemini.provider.generate.return_value = "a fake response"

    result = gemini.generate("hello", temperature=0.5)

    assert result == "a fake response"
    gemini.provider.generate.assert_called_once_with("hello", temperature=0.5)


def test_generate_structured_forwards_to_the_real_provider():
    gemini = Gemini(api_key="fake-key")
    gemini.provider = MagicMock()
    gemini.provider.is_available.return_value = True
    gemini.provider.generate_structured.return_value = {"key": "value"}

    result = gemini.generate_structured("hello")

    assert result == {"key": "value"}
    gemini.provider.generate_structured.assert_called_once_with("hello")


def test_per_call_model_override_forwarded_for_both_methods():
    gemini = Gemini(api_key="fake-key")
    gemini.provider = MagicMock()
    gemini.provider.is_available.return_value = True

    gemini.generate("hello", model="gemini-1.5-flash")
    gemini.generate_structured("hello", model="gemini-1.5-flash")

    gemini.provider.generate.assert_called_once_with("hello", model="gemini-1.5-flash")
    gemini.provider.generate_structured.assert_called_once_with(
        "hello", model="gemini-1.5-flash"
    )


def test_generate_typed_forwards_schema_and_max_retries():
    gemini = Gemini(api_key="fake-key")
    gemini.provider = MagicMock()
    gemini.provider.is_available.return_value = True
    fake_schema = object()
    gemini.provider.generate_typed.return_value = "typed result"

    result = gemini.generate_typed("hello", fake_schema, max_retries=5)

    assert result == "typed result"
    gemini.provider.generate_typed.assert_called_once_with(
        "hello", fake_schema, max_retries=5
    )


def test_generate_structured_raises_clear_error_when_unavailable(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    gemini = Gemini(api_key=None)
    with pytest.raises(ProcessingError, match="Gemini provider not available"):
        gemini.generate_structured("hello")


def test_generate_typed_raises_clear_error_when_unavailable(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    gemini = Gemini(api_key=None)
    with pytest.raises(ProcessingError, match="Gemini provider not available"):
        gemini.generate_typed("hello", object())
