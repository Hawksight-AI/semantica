"""
Gemini LLM Provider

Wrapper for Google Gemini API provider with clean interface.
"""

from typing import Any, Dict, List, Optional, Union

from ..semantic_extract.providers import GeminiProvider
from ..utils.exceptions import ProcessingError
from ..utils.logging import get_logger

logger = get_logger("llms.gemini")


class Gemini:
    """
    Google Gemini LLM provider wrapper.

    Provides clean interface to Google's Gemini API.

    Example:
        >>> from semantica.llms import Gemini
        >>> gemini = Gemini(model="gemini-pro", api_key="your-key")
        >>> response = gemini.generate("What is AI?")
    """

    def __init__(
        self,
        model: str = "gemini-pro",
        api_key: Optional[str] = None,
        **kwargs
    ):
        """
        Initialize Gemini provider.

        Args:
            model: Model name (default: "gemini-pro")
            api_key: Gemini API key (default: from GEMINI_API_KEY env var)
            **kwargs: Additional provider options
        """
        self.provider = GeminiProvider(api_key=api_key, model=model, **kwargs)
        self.model = model
        self.api_key = api_key

    def is_available(self) -> bool:
        """Check if Gemini provider is available."""
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
                "Gemini provider not available. Set GEMINI_API_KEY or pass api_key."
            )
        return self.provider.generate(prompt, **kwargs)

    def generate_structured(self, prompt: str, **kwargs) -> Union[Dict[str, Any], List[Any]]:
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
                "Gemini provider not available. Set GEMINI_API_KEY or pass api_key."
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
                "Gemini provider not available. Set GEMINI_API_KEY or pass api_key."
            )
        return self.provider.generate_typed(prompt, schema, max_retries=max_retries, **kwargs)
