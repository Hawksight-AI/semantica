"""
DeepSeek LLM Provider

Wrapper for DeepSeek API provider with clean interface.
"""

from typing import Any, Optional

from ..semantic_extract.providers import DeepSeekProvider
from ..utils.exceptions import ProcessingError
from ..utils.logging import get_logger
from .types import JSONValue

logger = get_logger("llms.deepseek")


class DeepSeek:
    """
    DeepSeek LLM provider wrapper.

    Provides clean interface to DeepSeek's OpenAI-compatible API.

    Example:
        >>> from semantica.llms import DeepSeek
        >>> llm = DeepSeek(model="deepseek-chat", api_key="your-key")
        >>> response = llm.generate("What is AI?")
    """

    def __init__(
        self,
        model: str = "deepseek-chat",
        api_key: Optional[str] = None,
        **kwargs
    ):
        """
        Initialize DeepSeek provider.

        Args:
            model: Model name (default: "deepseek-chat")
            api_key: DeepSeek API key (default: from DEEPSEEK_API_KEY env var)
            **kwargs: Additional provider options
        """
        self.provider = DeepSeekProvider(api_key=api_key, model=model, **kwargs)
        self.model = model
        self.api_key = api_key

    def is_available(self) -> bool:
        """Check if DeepSeek provider is available."""
        return self.provider.is_available()

    def generate(self, prompt: str, **kwargs) -> str:
        """
        Generate text from prompt.

        Args:
            prompt: Input prompt text
            **kwargs: Generation options (temperature, max_tokens, etc.)

        Returns:
            Generated text response

        Raises:
            ProcessingError: If provider is not available or generation fails
        """
        if not self.is_available():
            raise ProcessingError(
                "DeepSeek provider not available. Set DEEPSEEK_API_KEY or pass api_key."
            )
        return self.provider.generate(prompt, **kwargs)

    def generate_structured(self, prompt: str, **kwargs) -> JSONValue:
        """
        Generate structured JSON output.

        Args:
            prompt: Input prompt text
            **kwargs: Generation options

        Returns:
            Parsed JSON response as an object, array, string, number, boolean,
            or None.

        Raises:
            ProcessingError: If provider is not available or generation fails
        """
        if not self.is_available():
            raise ProcessingError(
                "DeepSeek provider not available. Set DEEPSEEK_API_KEY or pass api_key."
            )
        return self.provider.generate_structured(prompt, **kwargs)

    def generate_typed(self, prompt: str, schema: Any, max_retries: int = 3, **kwargs) -> Any:
        """
        Generate output validated against a Pydantic schema.

        Args:
            prompt: Input prompt text
            schema: Pydantic model class to validate the output against
            max_retries: Number of retries if validation fails (default: 3)
            **kwargs: Generation options

        Returns:
            An instance of `schema`, populated from the model's response

        Raises:
            ProcessingError: If provider is not available or generation fails
        """
        if not self.is_available():
            raise ProcessingError(
                "DeepSeek provider not available. Set DEEPSEEK_API_KEY or pass api_key."
            )
        return self.provider.generate_typed(prompt, schema, max_retries=max_retries, **kwargs)
