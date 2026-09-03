"""Tests for the Ollama LLM provider wrapper (semantica.llms.Ollama)."""

from unittest.mock import MagicMock

import pytest

from semantica.llms import Ollama
from semantica.utils.exceptions import ProcessingError


def test_construction_stores_model_and_base_url():
    llm = Ollama(model="llama2", base_url="http://localhost:11434")
    assert llm.model == "llama2"
    assert llm.base_url == "http://localhost:11434"


def test_is_available_false_without_a_running_server():
    """No api_key here, Ollama has none. Without a real server (or the ollama
    package) reachable at base_url, this must be a real False."""
    llm = Ollama(base_url="http://localhost:1")
    assert llm.is_available() is False


def test_generate_raises_clear_error_when_unavailable():
    llm = Ollama(base_url="http://localhost:1")
    with pytest.raises(ProcessingError, match="Ollama provider not available"):
        llm.generate("hello")


def test_generate_forwards_to_the_real_provider_when_available():
    llm = Ollama()
    llm.provider = MagicMock()
    llm.provider.is_available.return_value = True
    llm.provider.generate.return_value = "a fake response"

    result = llm.generate("hello", temperature=0.5)

    assert result == "a fake response"
    llm.provider.generate.assert_called_once_with("hello", temperature=0.5)


def test_generate_structured_forwards_to_the_real_provider():
    llm = Ollama()
    llm.provider = MagicMock()
    llm.provider.is_available.return_value = True
    llm.provider.generate_structured.return_value = {"key": "value"}

    result = llm.generate_structured("hello")

    assert result == {"key": "value"}
    llm.provider.generate_structured.assert_called_once_with("hello")


def test_generate_typed_forwards_schema_and_max_retries():
    llm = Ollama()
    llm.provider = MagicMock()
    llm.provider.is_available.return_value = True
    fake_schema = object()
    llm.provider.generate_typed.return_value = "typed result"

    result = llm.generate_typed("hello", fake_schema, max_retries=5)

    assert result == "typed result"
    llm.provider.generate_typed.assert_called_once_with(
        "hello", fake_schema, max_retries=5
    )


def test_generate_structured_raises_clear_error_when_unavailable():
    llm = Ollama(base_url="http://localhost:1")
    with pytest.raises(ProcessingError, match="Ollama provider not available"):
        llm.generate_structured("hello")


def test_generate_typed_raises_clear_error_when_unavailable():
    llm = Ollama(base_url="http://localhost:1")
    with pytest.raises(ProcessingError, match="Ollama provider not available"):
        llm.generate_typed("hello", object())
