"""
LiteLLM Provider

Wrapper for LiteLLM library that provides unified access to 100+ LLM providers.
Supports OpenAI, Anthropic, Groq, Azure, Bedrock, Vertex AI, and many more.
"""

from typing import Optional

from ..utils.exceptions import ProcessingError
from ..utils.logging import get_logger
from .types import JSONValue

logger = get_logger("llms.litellm")

from ..utils.helpers import safe_import

_litellm, LITELLM_AVAILABLE = safe_import("litellm")
if LITELLM_AVAILABLE:
    from litellm import completion
else:
    completion = None
    logger.warning(
        "litellm library not installed. Install with: pip install litellm"
    )


class LiteLLM:
    """
    LiteLLM provider wrapper.
    
    Provides unified interface to 100+ LLM providers through LiteLLM library.
    Supports providers like OpenAI, Anthropic, Groq, Azure, Bedrock, Vertex AI, etc.
    
    Model format: "provider/model-name" (e.g., "openai/gpt-4o", "anthropic/claude-sonnet-4-20250514", "groq/llama-3.1-8b-instant")
    
    Example:
        >>> from semantica.llms import LiteLLM
        >>> llm = LiteLLM(model="openai/gpt-4o", api_key="your-key")
        >>> response = llm.generate("What is AI?")
        >>> 
        >>> # Use with different providers
        >>> llm = LiteLLM(model="anthropic/claude-sonnet-4-20250514")
        >>> response = llm.generate("Hello!")
    """

    def __init__(
        self,
        model: str,
        api_key: Optional[str] = None,
        **kwargs
    ):
        """
        Initialize LiteLLM provider.

        Args:
            model: Model identifier in format "provider/model-name"
                   Examples: "openai/gpt-4o", "anthropic/claude-sonnet-4-20250514",
                             "groq/llama-3.1-8b-instant", "azure/gpt-4", etc.
            api_key: API key (optional, can use environment variables)
            **kwargs: Additional LiteLLM options (temperature, max_tokens, etc.)
        """
        if not LITELLM_AVAILABLE:
            raise ProcessingError(
                "LiteLLM library not installed. Install with: pip install litellm"
            )
        
        self.model = model
        self.api_key = api_key
        self.config = kwargs

    def is_available(self) -> bool:
        """Check if LiteLLM provider is available."""
        return LITELLM_AVAILABLE

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
                "LiteLLM library not installed. Install with: pip install litellm"
            )

        try:
            # Merge config with kwargs
            options = {**self.config, **kwargs}
            
            # Prepare messages
            messages = [{"role": "user", "content": prompt}]
            
            # Call LiteLLM completion
            response = completion(
                model=self.model,
                messages=messages,
                api_key=self.api_key,
                **options
            )
            
            # Extract text from response
            if hasattr(response, 'choices') and len(response.choices) > 0:
                return response.choices[0].message.content
            elif isinstance(response, dict):
                if 'choices' in response and len(response['choices']) > 0:
                    return response['choices'][0]['message']['content']
                elif 'content' in response:
                    return response['content']
            elif isinstance(response, str):
                return response
            
            raise ProcessingError(f"Unexpected response format from LiteLLM: {type(response)}")
            
        except Exception as e:
            logger.error(f"LiteLLM generation failed: {e}")
            raise ProcessingError(f"LiteLLM generation failed: {e}")

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
                "LiteLLM library not installed. Install with: pip install litellm"
            )

        try:
            import json
            
            # Add JSON format instruction to prompt
            json_prompt = f"{prompt}\n\nReturn the response as valid JSON only."
            
            # Merge config with kwargs
            options = {**self.config, **kwargs}
            
            # Prepare messages
            messages = [{"role": "user", "content": json_prompt}]
            
            # Call LiteLLM completion
            response = completion(
                model=self.model,
                messages=messages,
                api_key=self.api_key,
                **options
            )
            
            # Extract text from response
            text_response = ""
            if hasattr(response, 'choices') and len(response.choices) > 0:
                text_response = response.choices[0].message.content
            elif isinstance(response, dict):
                if 'choices' in response and len(response['choices']) > 0:
                    text_response = response['choices'][0]['message']['content']
                elif 'content' in response:
                    text_response = response['content']
            elif isinstance(response, str):
                text_response = response
            
            # Parse JSON
            try:
                return json.loads(text_response)
            except json.JSONDecodeError:
                # Try to extract JSON from text
                import re
                json_match = re.search(r'\{.*\}', text_response, re.DOTALL)
                if json_match:
                    return json.loads(json_match.group())
                raise ProcessingError(f"Failed to parse JSON from LiteLLM response: {text_response[:200]}")
                
        except Exception as e:
            logger.error(f"LiteLLM structured generation failed: {e}")
            raise ProcessingError(f"LiteLLM structured generation failed: {e}")
