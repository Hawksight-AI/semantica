"""
OpenAI LLM Provider

Wrapper for OpenAI API provider with clean interface.
"""

from typing import Any, Dict, List, Optional, Union

from ..semantic_extract.providers import OpenAIProvider
from ..utils.exceptions import ProcessingError
from ..utils.logging import get_logger

logger = get_logger("llms.openai")


class OpenAI:
    """
    OpenAI LLM provider wrapper.
    
    Provides clean interface to OpenAI API for text generation.
    
    Example:
        >>> from semantica.llms import OpenAI
        >>> openai = OpenAI(model="gpt-4", api_key="your-key")
        >>> response = openai.generate("What is AI?")
    """

    def __init__(
        self,
        model: str = "gpt-3.5-turbo",
        api_key: Optional[str] = None,
        **kwargs
    ):
        """
        Initialize OpenAI provider.

        Args:
            model: Model name (default: "gpt-3.5-turbo")
            api_key: OpenAI API key (default: from OPENAI_API_KEY env var)
            **kwargs: Additional provider options
        """
        self.provider = OpenAIProvider(api_key=api_key, model=model, **kwargs)
        self.model = model
        self.api_key = api_key

    def is_available(self) -> bool:
        """Check if OpenAI provider is available."""
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
                "OpenAI provider not available. Set OPENAI_API_KEY or pass api_key."
            )
        return self.provider.generate(prompt, **kwargs)

    def generate_structured(
        self, prompt: str, **kwargs
    ) -> Union[Dict[str, Any], List[Any]]:
        """
        Generate structured JSON output.

        Args:
            prompt: Input prompt text
            **kwargs: Generation options

        Returns:
            Parsed JSON response. A dict for a top-level JSON object, or a
            list if the model returns a top-level JSON array.

        Raises:
            ProcessingError: If provider is not available or parsing fails
        """
        if not self.is_available():
            raise ProcessingError(
                "OpenAI provider not available. Set OPENAI_API_KEY or pass api_key."
            )
        return self.provider.generate_structured(prompt, **kwargs)
