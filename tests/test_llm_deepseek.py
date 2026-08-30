"""Tests for the DeepSeek LLM provider wrapper (semantica.llms.DeepSeek)."""

from unittest.mock import MagicMock

import pytest

from semantica.llms import DeepSeek
from semantica.utils.exceptions import ProcessingError


def test_construction_stores_model_and_api_key():
    llm = DeepSeek(model="deepseek-chat", api_key="fake-key")
    assert llm.model == "deepseek-chat"
    assert llm.api_key == "fake-key"


def test_is_available_false_with_no_key(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    llm = DeepSeek(api_key=None)
    assert llm.is_available() is False


def test_generate_raises_clear_error_when_unavailable(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    llm = DeepSeek(api_key=None)
    with pytest.raises(ProcessingError, match="DeepSeek provider not available"):
        llm.generate("hello")


def test_generate_forwards_to_the_real_provider_when_available():
    llm = DeepSeek(api_key="fake-key")
    llm.provider = MagicMock()
    llm.provider.is_available.return_value = True
    llm.provider.generate.return_value = "a fake response"

    result = llm.generate("hello", temperature=0.5)

    assert result == "a fake response"
    llm.provider.generate.assert_called_once_with("hello", temperature=0.5)


def test_generate_structured_forwards_to_the_real_provider():
    llm = DeepSeek(api_key="fake-key")
    llm.provider = MagicMock()
    llm.provider.is_available.return_value = True
    llm.provider.generate_structured.return_value = {"key": "value"}

    result = llm.generate_structured("hello")

    assert result == {"key": "value"}
    llm.provider.generate_structured.assert_called_once_with("hello")


def test_generate_typed_forwards_schema_and_max_retries():
    llm = DeepSeek(api_key="fake-key")
    llm.provider = MagicMock()
    llm.provider.is_available.return_value = True
    fake_schema = object()
    llm.provider.generate_typed.return_value = "typed result"

    result = llm.generate_typed("hello", fake_schema, max_retries=5)

    assert result == "typed result"
    llm.provider.generate_typed.assert_called_once_with(
        "hello", fake_schema, max_retries=5
    )


def test_generate_structured_raises_clear_error_when_unavailable(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    llm = DeepSeek(api_key=None)
    with pytest.raises(ProcessingError, match="DeepSeek provider not available"):
        llm.generate_structured("hello")


def test_generate_typed_raises_clear_error_when_unavailable(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    llm = DeepSeek(api_key=None)
    with pytest.raises(ProcessingError, match="DeepSeek provider not available"):
        llm.generate_typed("hello", object())
