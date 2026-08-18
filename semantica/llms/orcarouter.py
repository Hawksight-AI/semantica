"""
OrcaRouter LLM Provider

Wrapper for the OrcaRouter routing gateway with a clean interface.

OrcaRouter (https://www.orcarouter.ai) exposes a unified OpenAI-compatible
endpoint that routes requests to frontier models across vendors, addressed with
the same ``provider/model`` prefix convention used by LiteLLM.
"""

from typing import Any, Dict, Optional

from ..semantic_extract.providers import OrcaRouterProvider
from ..utils.exceptions import ProcessingError
from ..utils.logging import get_logger

logger = get_logger("llms.orcarouter")


class OrcaRouter:
    """
    OrcaRouter LLM provider wrapper.

    Provides clean interface to OrcaRouter API for text generation.

    Example:
        >>> from semantica.llms import OrcaRouter
        >>> llm = OrcaRouter(model="openai/gpt-4o", api_key="your-key")
        >>> response = llm.generate("What is AI?")
    """

    def __init__(
        self, model: str = "openai/gpt-4o", api_key: Optional[str] = None, **kwargs
    ):
        """
        Initialize OrcaRouter provider.

        Args:
            model: Model name, ``provider/model`` prefix (default: "openai/gpt-4o")
            api_key: OrcaRouter API key (default: from ORCAROUTER_API_KEY env var)
            **kwargs: Additional provider options
        """
        self.provider = OrcaRouterProvider(api_key=api_key, model=model, **kwargs)
        self.model = model
        self.api_key = api_key

    def is_available(self) -> bool:
        """Check if OrcaRouter provider is available."""
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
                "OrcaRouter not available. Set ORCAROUTER_API_KEY or pass api_key."
            )
        return self.provider.generate(prompt, **kwargs)

    def generate_structured(self, prompt: str, **kwargs) -> Dict[str, Any]:
        """
        Generate structured JSON output.

        Args:
            prompt: Input prompt text
            **kwargs: Generation options

        Returns:
            Parsed JSON response as dictionary

        Raises:
            ProcessingError: If provider is not available or parsing fails
        """
        if not self.is_available():
            raise ProcessingError(
                "OrcaRouter not available. Set ORCAROUTER_API_KEY or pass api_key."
            )
        return self.provider.generate_structured(prompt, **kwargs)
