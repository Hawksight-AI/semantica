"""
HuggingFace LLM Provider

Wrapper for HuggingFace Transformers LLM provider with clean interface.
"""

from typing import Optional

from ..semantic_extract.providers import HuggingFaceLLMProvider
from ..utils.exceptions import ProcessingError
from ..utils.logging import get_logger
from .types import JSONValue

logger = get_logger("llms.huggingface")


class HuggingFaceLLM:
    """
    HuggingFace LLM provider wrapper.
    
    Provides clean interface to HuggingFace Transformers for local LLM inference.
    
    Example:
        >>> from semantica.llms import HuggingFaceLLM
        >>> hf = HuggingFaceLLM(model_name="gpt2")
        >>> response = hf.generate("What is AI?")
    """

    def __init__(
        self,
        model_name: Optional[str] = None,
        model: Optional[str] = None,
        device: Optional[str] = None,
        **kwargs
    ):
        """
        Initialize HuggingFace LLM provider.

        Args:
            model_name: HuggingFace model name (default: "gpt2")
            model: Alias for model_name (for consistency with other providers)
            device: Device to use ("cuda" or "cpu", default: auto-detect)
            **kwargs: Additional provider options
        """
        # Support both model_name and model for consistency
        if model is not None:
            model_name = model
        elif model_name is None:
            model_name = "gpt2"
        
        self.provider = HuggingFaceLLMProvider(
            model_name=model_name, device=device, **kwargs
        )
        self.model_name = model_name
        self.model = model_name  # Alias for consistency
        self.device = device

    def is_available(self) -> bool:
        """Check if HuggingFace LLM provider is available."""
        return self.provider.is_available()

    def generate(self, prompt: str, **kwargs) -> str:
        """
        Generate text from prompt.

        Args:
            prompt: Input prompt text
            **kwargs: Generation options (max_length, temperature, etc.)

        Returns:
            Generated text response

        Raises:
            ProcessingError: If provider is not available or generation fails
        """
        if not self.is_available():
            raise ProcessingError(
                "HuggingFace LLM provider not available. Install transformers library."
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
            ProcessingError: If provider is not available or parsing fails
        """
        if not self.is_available():
            raise ProcessingError(
                "HuggingFace LLM provider not available. Install transformers library."
            )
        return self.provider.generate_structured(prompt, **kwargs)
