from typing import Any, Dict, List, Union, get_type_hints

import pytest

from semantica.llms import (
    Anthropic,
    DeepSeek,
    Gemini,
    Groq,
    HuggingFaceLLM,
    LiteLLM,
    Novita,
    Ollama,
    OpenAI,
)

EXPECTED_RETURN = Union[Dict[str, Any], List[Any]]


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
    hints = get_type_hints(provider_class.generate_structured)

    assert hints["return"] == EXPECTED_RETURN
