from typing import get_args

import pytest

from semantica.llms import (
    Anthropic,
    DeepSeek,
    Gemini,
    Groq,
    HuggingFaceLLM,
    JSONValue,
    LiteLLM,
    Novita,
    Ollama,
    OpenAI,
)


@pytest.mark.parametrize(
    "provider_class",
    [
        OpenAI,
        Groq,
        HuggingFaceLLM,
        LiteLLM,
        Anthropic,
        Gemini,
        DeepSeek,
        Novita,
        Ollama,
    ],
)
def test_generate_structured_return_annotation(provider_class):
    annotations = provider_class.generate_structured.__annotations__

    assert annotations["return"] == JSONValue


def test_json_value_includes_scalar_results():
    scalar_types = {str, int, float, bool, type(None)}

    assert scalar_types.issubset(set(get_args(JSONValue)))
