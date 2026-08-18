"""
LLM Providers and Model Loaders Module

This module provides a unified interface for all LLM providers and HuggingFace model
loaders, enabling seamless integration with multiple language model services and
custom HuggingFace models for semantic extraction tasks.

Supported Providers:
    - "openai": OpenAI API (GPT-3.5, GPT-4, etc.)
    - "gemini": Google Gemini API (gemini-pro, etc.)
    - "groq": Groq API (llama2, mixtral, etc.)
    - "anthropic": Anthropic Claude API (claude-3-sonnet, etc.)
    - "ollama": Ollama local provider (local open-source models)
    - "deepseek": DeepSeek API (deepseek-chat, etc.)
    - "novita": Novita AI API (OpenAI-compatible)
    - "orcarouter": OrcaRouter routing gateway (OpenAI-compatible, frontier models)
    - "huggingface_llm": HuggingFace Transformers for LLM tasks

Supported Model Types:
    - NER Models: Token classification models for named entity recognition
    - Relation Models: Sequence classification models for relation extraction
    - Triplet Models: Seq2Seq models for triplet extraction

Algorithms Used:
    - Transformer Architecture: Attention mechanism-based neural networks
    - Token Classification: BERT, RoBERTa, DistilBERT for NER tasks
    - Sequence Classification: Transformer encoders for relation classification
    - Sequence-to-Sequence: Encoder-decoder transformers for triplet generation
    - Autoregressive Generation: GPT-style models for text generation
    - API Integration: RESTful API communication and JSON parsing
    - Model Caching: LRU cache and memory management for model loading
    - Device Management: CPU/GPU allocation and tensor operations

Key Features:
    - Unified provider interface for all LLM services
    - Support for multiple LLM providers:
        * OpenAI (GPT-3.5, GPT-4, etc.)
        * Google Gemini (gemini-pro, etc.)
        * Groq (llama2, mixtral, etc.)
        * Anthropic Claude (claude-3-sonnet, etc.)
        * Ollama (local open-source models)
        * HuggingFace Transformers (custom LLM models)
    - HuggingFace model loader for NER, relation extraction, and triplet extraction
    - Automatic API key management from environment variables
    - Structured JSON output generation
    - Model caching and device management (CPU/GPU)
    - Graceful fallback when providers are unavailable
    - Custom provider registration support

Main Classes:
    - BaseProvider: Abstract base class for all providers
    - OpenAIProvider: OpenAI API provider implementation
    - GeminiProvider: Google Gemini API provider implementation
    - GroqProvider: Groq API provider implementation
    - AnthropicProvider: Anthropic Claude API provider implementation
    - OllamaProvider: Ollama local provider implementation
    - HuggingFaceLLMProvider: HuggingFace transformers for LLM tasks
    - HuggingFaceModelLoader: Loader for HuggingFace models (NER, RE, TE)

Functions:
    - create_provider: Factory function to create provider instances

Example Usage:
    >>> from semantica.semantic_extract.providers import create_provider
    >>> provider = create_provider("openai", model="gpt-4")
    >>> response = provider.generate("Extract entities from: Apple Inc. was founded in 1976.")
    >>> 
    >>> loader = HuggingFaceModelLoader(device="cuda")
    >>> ner_model = loader.load_ner_model("dslim/bert-base-NER")

Author: Semantica Contributors
License: MIT
"""

import json
import os
import time
from typing import Any, Dict, List, Optional, Union, Type

try:
    from pydantic import BaseModel, ValidationError
except ImportError:
    BaseModel = Any
    ValidationError = Exception

try:
    import instructor
except ImportError:
    instructor = None

from ..utils.exceptions import ProcessingError
from ..utils.logging import get_logger
from .config import config
from .registry import provider_registry


class BaseProvider:
    """Base class for providers - makes it easy to add custom providers."""

    def __init__(self, **kwargs):
        """Initialize provider."""
        self.config = kwargs
        self.logger = get_logger(f"provider_{self.__class__.__name__}")

    def is_available(self) -> bool:
        """Check if provider is available."""
        return True

    def _add_if_set(self, target: dict, source: dict, *keys: str) -> None:
        """Add keys from source to target only if their values are not None."""
        for key in keys:
            if key in source and source[key] is not None:
                target[key] = source[key]

    def generate(self, prompt: str, **kwargs) -> str:
        """Generate text - must be implemented."""
        raise NotImplementedError

    def generate_structured(self, prompt: str, **kwargs) -> Union[dict, list]:
        """Generate structured output - must be implemented."""
        raise NotImplementedError

    def _parse_json(self, text: str) -> Union[dict, list]:
        """Extract and parse JSON from text, supporting objects and lists."""
        if not text:
            raise ProcessingError("Empty response from LLM")
            
        # Clean up text - remove markdown code blocks if present
        cleaned_text = text.strip()
        if "```json" in cleaned_text:
            cleaned_text = cleaned_text.split("```json")[1].split("```")[0].strip()
        elif "```" in cleaned_text:
            # Try to find the block that looks most like JSON
            blocks = cleaned_text.split("```")
            for block in blocks:
                block = block.strip()
                if (block.startswith("{") and block.endswith("}")) or \
                   (block.startswith("[") and block.endswith("]")):
                    cleaned_text = block
                    break

        def fix_json(json_str: str) -> str:
            """Basic JSON fixing for common LLM errors."""
            # Remove trailing commas before closing braces/brackets
            json_str = re.sub(r",\s*([\]}])", r"\1", json_str)
            return json_str

        import re

        try:
            return json.loads(cleaned_text)
        except json.JSONDecodeError:
            # Try to find JSON boundaries (outermost { } or [ ])
            start_obj = cleaned_text.find("{")
            start_list = cleaned_text.find("[")
            
            # Determine which one starts first
            start = -1
            if start_obj >= 0 and (start_list < 0 or start_obj < start_list):
                start = start_obj
            elif start_list >= 0:
                start = start_list
            
            if start >= 0:
                # Find the corresponding end
                end_obj = cleaned_text.rfind("}")
                end_list = cleaned_text.rfind("]")
                end = max(end_obj, end_list)
                
                if end > start:
                    candidate = cleaned_text[start:end+1]
                    try:
                        return json.loads(candidate)
                    except json.JSONDecodeError:
                        # Try fixing common errors
                        try:
                            return json.loads(fix_json(candidate))
                        except json.JSONDecodeError:
                            # Last resort: if it's truncated, try to close it
                            if candidate.endswith("..."):
                                candidate = candidate[:-3].strip()
                            
                            # Simple attempt to close unclosed structures
                            open_braces = candidate.count("{") - candidate.count("}")
                            open_brackets = candidate.count("[") - candidate.count("]")
                            
                            fixed_candidate = candidate
                            if open_braces > 0:
                                fixed_candidate += "}" * open_braces
                            if open_brackets > 0:
                                fixed_candidate += "]" * open_brackets
                                
                            try:
                                return json.loads(fix_json(fixed_candidate))
                            except json.JSONDecodeError as e:
                                raise ProcessingError(f"Failed to parse JSON from LLM response after cleaning: {e}")
            
            raise ProcessingError(f"No valid JSON structure found in response. Preview: {text[:100]}...")

    def generate_structured(self, prompt: str, max_retries: int = 3, **kwargs) -> Union[dict, list]:
        """Generate structured output with retry logic."""
        last_error = None
        import time
        
        for attempt in range(max_retries):
            try:
                # Add explicit JSON instruction if not present
                structured_prompt = prompt
                if "JSON" not in prompt:
                    structured_prompt = f"{prompt}\n\nReturn the response as valid JSON only."
                
                content = self.generate(structured_prompt, **kwargs)
                result = self._parse_json(content)
                
                # Basic validation: ensure it's not empty if we expect data
                if not result and attempt < max_retries - 1:
                    self.logger.warning(f"Empty structured response (attempt {attempt + 1}/{max_retries}). Retrying...")
                    continue
                    
                return result
                
            except (ProcessingError, Exception) as e:
                last_error = e
                if attempt < max_retries - 1:
                    wait_time = (attempt + 1) * 2 # Simple backoff
                    self.logger.warning(f"Extraction error (attempt {attempt + 1}/{max_retries}): {e}. Retrying in {wait_time}s...")
                    time.sleep(wait_time)
                else:
                    self.logger.error(f"Structured generation failed after {max_retries} attempts: {e}")
        
        if last_error:
            raise ProcessingError(f"Failed to generate structured output: {last_error}")
        return []

    def generate_typed(
        self, 
        prompt: str, 
        schema: Type[BaseModel], 
        max_retries: int = 3, 
        **kwargs
    ) -> BaseModel:
        """
        Generate structured output validated against a Pydantic schema.
        Uses instructor if available and supported for the provider, otherwise falls back to a repair loop.
        """
        provider_name = self.__class__.__name__
        
        # Try using instructor first if available
        if instructor:
            try:
                client = None
                mode = instructor.Mode.TOOLS  # Default mode
                
                if provider_name == "OpenAIProvider" and self.client:
                    custom_base_url = getattr(self, "base_url", None)
                    if custom_base_url:
                        # OpenAI-compatible custom endpoint: Mode.TOOLS is not reliably
                        # supported by third-party servers (Qwen, LLaMA gateways, etc.).
                        # Mode.JSON asks the model to return plain JSON and is broadly
                        # supported across all OpenAI-compatible APIs.
                        client = instructor.from_openai(self.client, mode=instructor.Mode.JSON)
                    elif hasattr(instructor, "from_provider"):
                        try:
                            client = instructor.from_provider(
                                provider=f"openai/{kwargs.get('model', self.model)}",
                                api_key=self.api_key,
                            )
                        except Exception:
                            client = instructor.from_openai(self.client)
                    else:
                        client = instructor.from_openai(self.client)
                elif provider_name == "AnthropicProvider" and self.client:
                    if hasattr(instructor, "from_provider"):
                        try:
                            client = instructor.from_provider(
                                provider=f"anthropic/{kwargs.get('model', self.model)}", 
                                api_key=self.api_key
                            )
                        except Exception:
                            client = instructor.from_anthropic(self.client)
                    else:
                        client = instructor.from_anthropic(self.client)
                elif provider_name == "GeminiProvider" and self.client:
                    if hasattr(instructor, "from_provider"):
                        try:
                            client = instructor.from_provider(
                                provider=f"gemini/{kwargs.get('model', self.model)}", 
                                api_key=self.api_key
                            )
                        except Exception:
                            client = instructor.from_gemini(
                                self.client, 
                                mode=instructor.Mode.GEMINI_JSON
                            )
                    else:
                        client = instructor.from_gemini(
                            self.client, 
                            mode=instructor.Mode.GEMINI_JSON
                        )
                elif provider_name == "GroqProvider" and self.client:
                    # Try using from_provider which is recommended for Groq in latest instructor
                    if hasattr(instructor, "from_provider"):
                        try:
                            client = instructor.from_provider(
                                provider=f"groq/{kwargs.get('model', self.model)}", 
                                api_key=self.api_key
                            )
                        except Exception:
                            client = None

                    if not client:
                        # Try using from_groq if available (newer instructor versions)
                        if hasattr(instructor, "from_groq"):
                            client = instructor.from_groq(self.client, mode=instructor.Mode.JSON)
                        else:
                            # Fallback: Create OpenAI client pointing to Groq
                            # This avoids the "Client should be an instance of openai.OpenAI" warning
                            try:
                                from openai import OpenAI
                                # Fix: Use self.api_key instead of self.client.api_key
                                groq_client = OpenAI(
                                    base_url="https://api.groq.com/openai/v1",
                                    api_key=self.api_key,
                                )
                                client = instructor.from_openai(groq_client, mode=instructor.Mode.JSON)
                            except Exception:
                                # Last resort: try passing the groq client directly
                                client = instructor.from_openai(self.client, mode=instructor.Mode.JSON)
                elif provider_name == "OllamaProvider":
                    # Try from_provider for Ollama if available
                    if hasattr(instructor, "from_provider"):
                        try:
                            client = instructor.from_provider(
                                provider=f"ollama/{kwargs.get('model', self.model)}",
                            )
                        except Exception:
                            client = None
                    
                    if not client:
                        # Create OpenAI-compatible client for Ollama
                        try:
                            from openai import OpenAI
                            # Ollama typically runs on localhost:11434/v1
                            base_url = getattr(self, "base_url", "http://localhost:11434")
                            if not base_url.endswith("/v1"):
                                base_url = f"{base_url.rstrip('/')}/v1"
                            
                            ollama_client = OpenAI(
                                base_url=base_url,
                                api_key="ollama", # required but unused
                            )
                            client = instructor.from_openai(ollama_client, mode=instructor.Mode.JSON)
                        except ImportError:
                            pass
                elif provider_name == "DeepSeekProvider" and self.client:
                    # Try from_provider for DeepSeek
                    if hasattr(instructor, "from_provider"):
                        try:
                            client = instructor.from_provider(
                                provider=f"deepseek/{kwargs.get('model', self.model)}",
                                api_key=self.api_key
                            )
                        except Exception:
                            client = None

                    if not client:
                        # DeepSeek is OpenAI compatible
                        try:
                            from openai import OpenAI
                            if isinstance(self.client, OpenAI):
                                 client = instructor.from_openai(self.client, mode=instructor.Mode.JSON)
                            else:
                                 # Try creating fresh client
                                 ds_client = OpenAI(
                                     api_key=self.api_key, 
                                     base_url="https://api.deepseek.com"
                                 )
                                 client = instructor.from_openai(ds_client, mode=instructor.Mode.JSON)
                        except Exception:
                            pass

                # Global LiteLLM support - if litellm is passed in kwargs or config
                if not client and (kwargs.get("litellm") or self.config.get("litellm")):
                    if hasattr(instructor, "from_provider"):
                        try:
                            # Format for litellm in instructor is litellm/model_name
                            provider_model = kwargs.get("model", self.model)
                            litellm_provider = f"litellm/{provider_model}"
                            client = instructor.from_provider(litellm_provider, api_key=self.api_key)
                        except Exception:
                            pass

                if client:
                    # Map generate arguments to client arguments
                    # Instructor standardizes on chat.completions.create for OpenAI/Groq/Anthropic/Gemini
                    create_kwargs = {
                        "model": kwargs.get("model", self.model),
                        "messages": [{"role": "user", "content": prompt}],
                        "response_model": schema,
                        "max_retries": max_retries,
                        "temperature": kwargs.get("temperature") if kwargs.get("temperature") is not None else 0.1,
                    }
                    self._add_if_set(create_kwargs, kwargs, "max_tokens", "max_completion_tokens",
                                     "top_p", "frequency_penalty", "presence_penalty", "seed", "stop", "logit_bias", "user", "top_k")

                    if provider_name == "GroqProvider":
                        create_kwargs["response_format"] = {"type": "json_object"}

                    try:
                        response = client.chat.completions.create(**create_kwargs)
                    except Exception as primary_err:
                        # Mode.TOOLS can fail on standard OpenAI endpoints for certain
                        # models (streaming quirks, schema binding issues). Retry once
                        # with Mode.JSON before giving up entirely.
                        # Custom-base_url providers already use Mode.JSON from the start,
                        # so we only retry here for the standard OpenAI path.
                        if (
                            provider_name == "OpenAIProvider"
                            and not getattr(self, "base_url", None)
                            and hasattr(self, "client")
                            and self.client
                        ):
                            self.logger.warning(
                                "instructor Mode.TOOLS failed for %s (%s); retrying with Mode.JSON.",
                                provider_name,
                                primary_err,
                                exc_info=True,
                            )
                            json_client = instructor.from_openai(self.client, mode=instructor.Mode.JSON)
                            # Build a clean kwargs dict for the Mode.JSON retry: drop
                            # response_format (Mode.JSON handles schema differently)
                            # but keep response_model/max_retries so instructor still
                            # validates the typed output.
                            retry_kwargs = {
                                k: v for k, v in create_kwargs.items()
                                if k != "response_format"
                            }
                            response = json_client.chat.completions.create(**retry_kwargs)
                        else:
                            raise

                    verbose_mode = kwargs.get("verbose", False) or self.config.get("verbose", False)
                    if verbose_mode:
                        self.logger.debug(
                            "[BaseProvider.generate_typed] Typed response received via instructor (%s).",
                            provider_name,
                        )
                    return response
            except Exception as e:
                self.logger.warning(
                    "Instructor generation failed (%s), falling back to manual repair loop.",
                    e,
                    exc_info=True,
                )

        # Fallback: Manual repair loop
        last_error = None
        current_prompt = prompt
        
        for attempt in range(max_retries):
            try:
                # 1. Generate JSON – try structured mode first, then fall back to
                # plain generate() + parse.  Custom gateways that reject
                # response_format=json_object would otherwise loop forever here.
                try:
                    json_result = self.generate_structured(current_prompt, max_retries=1, **kwargs)
                except Exception as struct_err:
                    self.logger.warning(
                        "generate_structured failed (%s); retrying with plain generate() + JSON parse.",
                        struct_err,
                        exc_info=True,
                    )
                    raw_content = self.generate(current_prompt, **kwargs)
                    json_result = self._parse_json(raw_content)
                
                # 2. Validate with Schema
                # If the result is a list and schema expects a wrapper, or vice versa, we might need adjustment
                # But we assume the prompt asks for the correct structure matching the schema.
                
                # Special handling if schema is a wrapper but result is a list
                if isinstance(json_result, list) and hasattr(schema, "entities") and "entities" in schema.model_fields:
                     # Auto-wrap for entities
                     json_result = {"entities": json_result}

                # Handle categorized dictionary input (e.g. {"PERSON": ["Name"], "ORG": ["Corp"]})
                elif isinstance(json_result, dict) and hasattr(schema, "entities") and "entities" in schema.model_fields:
                     # Check if it's NOT already in the correct format (i.e., missing "entities" key)
                     if "entities" not in json_result:
                         # Check if values are lists, suggesting categorized output
                         is_categorized = any(isinstance(v, list) for v in json_result.values())
                         if is_categorized:
                             flat_entities = []
                             for label, items in json_result.items():
                                 if isinstance(items, list):
                                     for item in items:
                                         if isinstance(item, str):
                                             flat_entities.append({"text": item, "label": label})
                                         elif isinstance(item, dict):
                                             # If it's already a dict but nested under label
                                             item["label"] = label
                                             flat_entities.append(item)
                             json_result = {"entities": flat_entities}

                # Handle categorized dictionary input for relations (e.g. {"founded_by": [{"subject":..., "object":...}]})
                elif isinstance(json_result, dict) and hasattr(schema, "relations") and "relations" in schema.model_fields:
                     if "relations" not in json_result:
                         is_categorized = any(isinstance(v, list) for v in json_result.values())
                         if is_categorized:
                             flat_relations = []
                             for label, items in json_result.items():
                                 if isinstance(items, list):
                                     for item in items:
                                         if isinstance(item, dict):
                                             # If predicate is missing, use the key as predicate
                                             if "predicate" not in item:
                                                 item["predicate"] = label
                                             flat_relations.append(item)
                             json_result = {"relations": flat_relations}

                # Handle categorized dictionary input for triplets
                elif isinstance(json_result, dict) and hasattr(schema, "triplets") and "triplets" in schema.model_fields:
                     if "triplets" not in json_result:
                         is_categorized = any(isinstance(v, list) for v in json_result.values())
                         if is_categorized:
                             flat_triplets = []
                             for label, items in json_result.items():
                                 if isinstance(items, list):
                                     for item in items:
                                          if isinstance(item, dict):
                                              flat_triplets.append(item)
                             json_result = {"triplets": flat_triplets}

                elif isinstance(json_result, list) and hasattr(schema, "relations") and "relations" in schema.model_fields:
                     json_result = {"relations": json_result}
                elif isinstance(json_result, list) and hasattr(schema, "triplets") and "triplets" in schema.model_fields:
                     json_result = {"triplets": json_result}

                validated = schema.model_validate(json_result)
                return validated
                
            except ValidationError as e:
                last_error = e
                error_summary = str(e)
                # Simplify error summary for the LLM
                # (You could parse e.errors() for a better message)
                
                if attempt < max_retries - 1:
                    wait_time = (attempt + 1) * 1
                    self.logger.warning(f"Schema validation failed (attempt {attempt + 1}): {e}. Retrying with error feedback...")
                    
                    # Update prompt with error info
                    current_prompt = f"{prompt}\n\nPrevious response was invalid JSON or didn't match schema:\n{error_summary}\n\nPlease fix the errors and return valid JSON matching the schema."
                    time.sleep(wait_time)
                else:
                    self.logger.error(f"Typed generation failed validation: {e}")
            
            except Exception as e:
                last_error = e
                if attempt < max_retries - 1:
                     time.sleep(1)
                else:
                    self.logger.error(f"Typed generation failed: {e}")

        raise ProcessingError(f"Failed to generate typed output after {max_retries} attempts: {last_error}")

class OpenAIProvider(BaseProvider):
    """OpenAI provider implementation."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "gpt-3.5-turbo",
        base_url: Optional[str] = None,
        **kwargs,
    ):
        """Initialize OpenAI provider.

        Args:
            api_key: OpenAI API key (or OPENAI_API_KEY env var).
            model: Default model name.
            base_url: Optional custom base URL for OpenAI-compatible endpoints
                (e.g. local gateways, Qwen, LLaMA proxies).  When set,
                ``instructor`` will use ``Mode.JSON`` instead of
                ``Mode.TOOLS`` because most OpenAI-compatible servers do not
                implement the full function-calling protocol.
        """
        super().__init__(**kwargs)
        self.api_key = api_key or config.get_api_key("openai")
        self.model = model
        self.base_url = base_url  # None → standard OpenAI; set → custom endpoint
        self.client = None
        self._init_client()

    def _init_client(self):
        """Initialize OpenAI client, respecting a custom base_url if provided."""
        if self.base_url:
            # Reject non-HTTP schemes (file://, ftp://, etc.) to prevent SSRF
            # when base_url originates from configuration rather than hardcoded values.
            from urllib.parse import urlparse
            scheme = urlparse(self.base_url).scheme
            if scheme not in ("http", "https"):
                raise ValueError(
                    f"OpenAIProvider base_url must use http or https, got scheme {scheme!r}. "
                    f"Only HTTP(S) endpoints are permitted."
                )

        try:
            from openai import OpenAI

            if self.api_key:
                init_kwargs: Dict[str, Any] = {"api_key": self.api_key}
                if self.base_url:
                    init_kwargs["base_url"] = self.base_url
                self.client = OpenAI(**init_kwargs)
        except (ImportError, OSError):
            self.client = None
            self.logger.warning(
                "openai library not installed. Install with: pip install semantica[llm-openai]"
            )

    def is_available(self) -> bool:
        """Check if provider is available."""
        return self.client is not None

    def generate(self, prompt: str, **kwargs) -> str:
        """Generate text from prompt."""
        if not self.client:
            raise ProcessingError(
                "OpenAI client not initialized. Set OPENAI_API_KEY or pass api_key."
            )

        create_kwargs = {
            "model": kwargs.get("model", self.model),
            "messages": [{"role": "user", "content": prompt}],
        }
        self._add_if_set(create_kwargs, kwargs, "temperature", "max_completion_tokens", "max_tokens",
                         "top_p", "frequency_penalty", "presence_penalty", "seed", "stop", "logit_bias", "user")

        response = self.client.chat.completions.create(**create_kwargs)
        return response.choices[0].message.content

    def generate_structured(self, prompt: str, **kwargs) -> dict:
        """Generate structured JSON output."""
        if not self.client:
            raise ProcessingError("OpenAI client not initialized.")

        create_kwargs = {
            "model": kwargs.get("model", self.model),
            "messages": [{"role": "user", "content": prompt}],
        }
        # response_format=json_object is only safe for standard OpenAI endpoints.
        # Custom gateways (base_url set) often reject or mishandle this parameter,
        # causing silent fallback to pattern extraction.
        if not self.base_url:
            create_kwargs["response_format"] = {"type": "json_object"}

        self._add_if_set(create_kwargs, kwargs, "temperature", "max_completion_tokens", "max_tokens",
                         "top_p", "frequency_penalty", "presence_penalty", "seed", "stop", "logit_bias", "user")

        response = self.client.chat.completions.create(**create_kwargs)
        try:
            return self._parse_json(response.choices[0].message.content)
        except Exception as e:
            raise ProcessingError(f"Failed to parse JSON from OpenAI response: {e}")


class GeminiProvider(BaseProvider):
    """Google Gemini provider implementation."""

    def __init__(
        self, api_key: Optional[str] = None, model: str = "gemini-pro", **kwargs
    ):
        """Initialize Gemini provider."""
        super().__init__(**kwargs)
        self.api_key = api_key or config.get_api_key("gemini")
        self.model = model
        self.client = None
        self._use_new_genai = False
        self._init_client()

    def _init_client(self):
        try:
            from google import genai as new_genai
            if self.api_key:
                self.client = new_genai.Client(api_key=self.api_key)
                self._use_new_genai = True
                return
        except Exception:
            pass
        try:
            import google.generativeai as old_genai
            if self.api_key:
                old_genai.configure(api_key=self.api_key)
                self.client = old_genai.GenerativeModel(self.model)
                self._use_new_genai = False
        except Exception:
            self.client = None
            self.logger.warning("Gemini SDK not installed. Install with: pip install semantica[llm-gemini]")

    def is_available(self) -> bool:
        """Check if provider is available."""
        return self.client is not None

    def _resp_text(self, resp: Any) -> str:
        if hasattr(resp, "text"):
            return getattr(resp, "text")
        try:
            return resp.candidates[0].content.parts[0].text
        except Exception:
            return str(resp)

    def generate(self, prompt: str, **kwargs) -> str:
        """Generate text from prompt."""
        if not self.client:
            raise ProcessingError(
                "Gemini client not initialized. Set GEMINI_API_KEY or pass api_key."
            )

        config = {}
        self._add_if_set(config, kwargs, "temperature", "top_p", "top_k", "stop_sequences", "candidate_count")
        if "max_tokens" in kwargs:
            config["max_output_tokens"] = kwargs["max_tokens"]

        if self._use_new_genai:
            resp = self.client.models.generate_content(
                model=kwargs.get("model", self.model), contents=prompt, config=config or None
            )
            return self._resp_text(resp)
        else:
            response = self.client.generate_content(prompt, generation_config=config or None)
            return self._resp_text(response)

    def generate_structured(self, prompt: str, **kwargs) -> dict:
        """Generate structured output."""
        if not self.client:
            raise ProcessingError("Gemini client not initialized.")

        json_prompt = f"{prompt}\n\nReturn the response as valid JSON only."
        if self._use_new_genai:
            model = kwargs.get("model", self.model)
            resp = self.client.models.generate_content(model=model, contents=json_prompt)
            try:
                return self._parse_json(self._resp_text(resp))
            except Exception as e:
                raise ProcessingError(f"Failed to parse JSON from Gemini response: {e}")
        else:
            response = self.client.generate_content(json_prompt)
            try:
                return self._parse_json(self._resp_text(response))
            except Exception as e:
                raise ProcessingError(f"Failed to parse JSON from Gemini response: {e}")


class GroqProvider(BaseProvider):
    """Groq provider implementation."""

    def __init__(
        self, api_key: Optional[str] = None, model: str = "llama-3.3-70b-versatile", **kwargs
    ):
        """Initialize Groq provider."""
        super().__init__(**kwargs)
        self.api_key = api_key or config.get_api_key("groq")
        self.model = model
        self.client = None
        self._init_client()

    def _init_client(self):
        """Initialize Groq client."""
        try:
            from groq import Groq

            if not self.api_key:
                # We don't raise here yet to allow is_available() to return False gracefully
                self.logger.debug("Groq API key missing during initialization")
                return

            self.client = Groq(api_key=self.api_key)
            
            # Test connection with a minimal prompt
            # Only do this if we have a key and client
            # self._test_connection()
        except ImportError:
            self.client = None
            self.logger.warning(
                "groq library not installed. Install with: pip install semantica[llm-groq]"
            )
        except Exception as e:
            self.client = None
            self.logger.error(f"Failed to initialize Groq client: {e}")

    def _test_connection(self):
        """Internal method to verify connection."""
        if not self.client:
            return
        try:
            # We use a very low limit to just test availability
            self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": "ping"}],
                max_tokens=1
            )
            self.logger.debug("Groq connection test successful")
        except Exception as e:
            self.logger.warning(f"Groq connection test failed: {e}")

    def is_available(self) -> bool:
        """Check if provider is available."""
        return self.client is not None

    def generate(self, prompt: str, **kwargs) -> str:
        """Generate text from prompt."""
        if not self.client:
            raise ProcessingError(
                "Groq client not initialized. Set GROQ_API_KEY or pass api_key."
            )

        create_kwargs = {
            "model": kwargs.get("model", self.model),
            "messages": [{"role": "user", "content": prompt}],
        }
        self._add_if_set(create_kwargs, kwargs, "temperature", "max_completion_tokens", "max_tokens",
                         "top_p", "frequency_penalty", "presence_penalty", "seed", "stop", "user")

        response = self.client.chat.completions.create(**create_kwargs)
        return response.choices[0].message.content

    def generate_structured(self, prompt: str, **kwargs) -> dict:
        """Generate structured output."""
        if not self.client:
            raise ProcessingError("Groq client not initialized.")

        # Groq requires 'json' in the prompt for json_object mode
        json_prompt = prompt if "json" in prompt.lower() else f"{prompt}\n\nReturn the response as valid JSON only."

        create_kwargs = {
            "model": kwargs.get("model", self.model),
            "messages": [{"role": "user", "content": json_prompt}],
            "response_format": {"type": "json_object"},
        }
        self._add_if_set(create_kwargs, kwargs, "temperature", "max_completion_tokens", "max_tokens",
                         "top_p", "frequency_penalty", "presence_penalty", "seed", "stop", "user")

        response = self.client.chat.completions.create(**create_kwargs)
        try:
            return self._parse_json(response.choices[0].message.content)
        except Exception as e:
            raise ProcessingError(f"Failed to parse JSON from Groq response: {e}")


class AnthropicProvider(BaseProvider):
    """Anthropic Claude provider implementation."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "claude-3-sonnet-20240229",
        **kwargs,
    ):
        """Initialize Anthropic provider."""
        super().__init__(**kwargs)
        self.api_key = api_key or config.get_api_key("anthropic")
        self.model = model
        self.client = None
        self._init_client()

    def _init_client(self):
        """Initialize Anthropic client."""
        try:
            from anthropic import Anthropic

            if self.api_key:
                self.client = Anthropic(api_key=self.api_key)
        except (ImportError, OSError):
            self.client = None
            self.logger.warning(
                "anthropic library not installed. Install with: pip install semantica[llm-anthropic]"
            )

    def is_available(self) -> bool:
        """Check if provider is available."""
        return self.client is not None

    def generate(self, prompt: str, **kwargs) -> str:
        """Generate text from prompt."""
        if not self.client:
            raise ProcessingError(
                "Anthropic client not initialized. Set ANTHROPIC_API_KEY or pass api_key."
            )

        # Anthropic requires max_tokens. 
        # We rely on kwargs, but fallback to 8192 (safe max for newer models) if not provided.
        max_tokens = kwargs.get("max_tokens", 8192)
        
        # Prepare arguments
        create_kwargs = {
            "model": kwargs.get("model", self.model),
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
        
        # Pass through other common parameters
        for param in ["temperature", "top_p", "top_k", "stop_sequences", "system", "metadata"]:
            if param in kwargs:
                create_kwargs[param] = kwargs[param]

        response = self.client.messages.create(**create_kwargs)
        return response.content[0].text

    def generate_structured(self, prompt: str, **kwargs) -> dict:
        """Generate structured output."""
        if not self.client:
            raise ProcessingError("Anthropic client not initialized.")

        json_prompt = f"{prompt}\n\nReturn the response as valid JSON only."
        
        # Anthropic requires max_tokens. 
        max_tokens = kwargs.get("max_tokens", 8192)
        
        # Prepare arguments
        create_kwargs = {
            "model": kwargs.get("model", self.model),
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": json_prompt}],
        }
        
        # Pass through other common parameters
        for param in ["temperature", "top_p", "top_k", "stop_sequences", "system", "metadata"]:
            if param in kwargs:
                create_kwargs[param] = kwargs[param]
        
        response = self.client.messages.create(**create_kwargs)
        try:
            return self._parse_json(response.content[0].text)
        except Exception as e:
            raise ProcessingError(f"Failed to parse JSON from Anthropic response: {e}")


class OllamaProvider(BaseProvider):
    """Ollama local provider implementation."""

    def __init__(
        self, base_url: str = "http://localhost:11434", model: str = "llama2", **kwargs
    ):
        """Initialize Ollama provider."""
        super().__init__(**kwargs)
        self.base_url = base_url
        self.model = model
        self.client = None
        self._init_client()

    def _init_client(self):
        """Initialize Ollama client."""
        try:
            import ollama  # type: ignore[import-untyped]

            self.client = ollama.Client(host=self.base_url)
            # Test connection
            try:
                self.client.list()  # Test if Ollama is running
            except Exception:
                self.client = None
                self.logger.warning(
                    "Ollama server not accessible. Make sure Ollama is running."
                )
        except (ImportError, OSError):
            self.client = None
            self.logger.warning(
                "ollama library not installed. Install with: pip install semantica[llm-ollama]"
            )

    def is_available(self) -> bool:
        """Check if provider is available."""
        return self.client is not None

    def _build_options(self, kwargs: dict) -> Optional[dict]:
        """Build Ollama options dict from kwargs."""
        options = {}
        self._add_if_set(options, kwargs, "temperature", "top_p", "top_k", "repeat_penalty", "seed")
        if "max_tokens" in kwargs:
            options["num_predict"] = kwargs["max_tokens"]
        if "num_ctx" in kwargs:
            options["num_ctx"] = kwargs["num_ctx"]
        elif "context_window" in kwargs:
            options["num_ctx"] = kwargs["context_window"]
        return options or None

    def generate(self, prompt: str, **kwargs) -> str:
        """Generate text from prompt."""
        if not self.client:
            raise ProcessingError(
                "Ollama client not initialized. Make sure Ollama is running."
            )

        response = self.client.generate(
            model=kwargs.get("model", self.model),
            prompt=prompt,
            options=self._build_options(kwargs),
        )
        return response.get("response", "")

    def generate_structured(self, prompt: str, **kwargs) -> dict:
        """Generate structured output."""
        if not self.client:
            raise ProcessingError("Ollama client not initialized.")

        json_prompt = f"{prompt}\n\nReturn the response as valid JSON only."
        response = self.client.generate(
            model=kwargs.get("model", self.model),
            prompt=json_prompt,
            options=self._build_options(kwargs),
        )
        try:
            return self._parse_json(response.get("response", "{}"))
        except Exception as e:
            raise ProcessingError(f"Failed to parse JSON from Ollama response: {e}")


class DeepSeekProvider(BaseProvider):
    def __init__(self, api_key: Optional[str] = None, model: str = "deepseek-chat", **kwargs):
        super().__init__(**kwargs)
        self.api_key = api_key or config.get_api_key("deepseek")
        self.base_url = "https://api.deepseek.com/v1"
        self.model = model
        self.base_url = "https://api.deepseek.com/v1"
        self.client = None
        self._init_client()

    def _init_client(self):
        try:
            from openai import OpenAI

            if self.api_key:
                self.client = OpenAI(api_key=self.api_key, base_url=self.base_url)
        except (ImportError, OSError):
            self.client = None
            self.logger.warning(
                "openai library not installed. Install with: pip install semantica[llm-openai]"
            )

    def is_available(self) -> bool:
        return self.client is not None

    def generate(self, prompt: str, **kwargs) -> str:
        if not self.client:
            raise ProcessingError("DeepSeek client not initialized. Set DEEPSEEK_API_KEY or pass api_key.")

        create_kwargs = {
            "model": kwargs.get("model", self.model),
            "messages": [{"role": "user", "content": prompt}],
        }
        self._add_if_set(create_kwargs, kwargs, "temperature", "max_tokens")

        response = self.client.chat.completions.create(**create_kwargs)
        return response.choices[0].message.content

    def generate_structured(self, prompt: str, **kwargs) -> Union[dict, list]:
        """Generate structured output."""
        if not self.client:
            raise ProcessingError("DeepSeek client not initialized.")

        create_kwargs = {
            "model": kwargs.get("model", self.model),
            "messages": [{"role": "user", "content": prompt}],
        }
        self._add_if_set(create_kwargs, kwargs, "temperature", "max_tokens")

        response = self.client.chat.completions.create(**create_kwargs)
        try:
            return self._parse_json(response.choices[0].message.content)
        except Exception as e:
            raise ProcessingError(f"Failed to parse JSON from DeepSeek response: {e}")


class NovitaProvider(BaseProvider):
    """Novita AI provider implementation - OpenAI-compatible API."""

    def __init__(self, api_key: Optional[str] = None, model: str = "deepseek/deepseek-v3.2", **kwargs):
        """Initialize Novita provider."""
        super().__init__(**kwargs)
        self.api_key = api_key or config.get_api_key("novita")
        self.model = model
        self.base_url = "https://api.novita.ai/v1"
        self.client = None
        self._init_client()

    def _init_client(self):
        try:
            from openai import OpenAI

            if self.api_key:
                self.client = OpenAI(api_key=self.api_key, base_url=self.base_url)
        except (ImportError, OSError):
            self.client = None
            self.logger.warning(
                "openai library not installed. Install with: pip install semantica[llm-openai]"
            )

    def is_available(self) -> bool:
        return self.client is not None

    def generate(self, prompt: str, **kwargs) -> str:
        if not self.client:
            raise ProcessingError("Novita client not initialized. Set NOVITA_API_KEY or pass api_key.")

        create_kwargs = {
            "model": kwargs.get("model", self.model),
            "messages": [{"role": "user", "content": prompt}],
        }
        self._add_if_set(create_kwargs, kwargs, "temperature", "max_tokens")

        response = self.client.chat.completions.create(**create_kwargs)
        return response.choices[0].message.content

    def generate_structured(self, prompt: str, **kwargs) -> Union[dict, list]:
        """Generate structured output."""
        if not self.client:
            raise ProcessingError("Novita client not initialized.")

        create_kwargs = {
            "model": kwargs.get("model", self.model),
            "messages": [{"role": "user", "content": prompt}],
            "response_format": {"type": "json_object"},
        }
        self._add_if_set(create_kwargs, kwargs, "temperature", "max_tokens")

        response = self.client.chat.completions.create(**create_kwargs)
        try:
            return self._parse_json(response.choices[0].message.content)
        except Exception as e:
            raise ProcessingError(f"Failed to parse JSON from Novita response: {e}")


class OrcaRouterProvider(BaseProvider):
    """OrcaRouter provider implementation - OpenAI-compatible routing gateway.

    OrcaRouter (https://www.orcarouter.ai) exposes a unified OpenAI-compatible
    endpoint that routes requests to frontier models across vendors. Models are
    addressed with the same ``provider/model`` prefix convention used by LiteLLM,
    e.g. ``openai/gpt-4o``, ``anthropic/claude-sonnet-4.6`` or
    ``deepseek/deepseek-v4-flash``.
    """

    def __init__(
        self, api_key: Optional[str] = None, model: str = "openai/gpt-4o", **kwargs
    ):
        """Initialize OrcaRouter provider."""
        super().__init__(**kwargs)
        self.api_key = api_key or config.get_api_key("orcarouter")
        self.model = model
        self.base_url = "https://api.orcarouter.ai/v1"
        self.client = None
        self._init_client()

    def _init_client(self):
        try:
            from openai import OpenAI

            if self.api_key:
                self.client = OpenAI(api_key=self.api_key, base_url=self.base_url)
        except (ImportError, OSError):
            self.client = None
            self.logger.warning(
                "openai library not installed. Install with: pip install semantica[llm-openai]"
            )

    def is_available(self) -> bool:
        return self.client is not None

    def generate(self, prompt: str, **kwargs) -> str:
        if not self.client:
            raise ProcessingError(
                "OrcaRouter client not initialized. Set ORCAROUTER_API_KEY or pass api_key."
            )

        create_kwargs = {
            "model": kwargs.get("model", self.model),
            "messages": [{"role": "user", "content": prompt}],
        }
        self._add_if_set(create_kwargs, kwargs, "temperature", "max_tokens")

        response = self.client.chat.completions.create(**create_kwargs)
        return response.choices[0].message.content

    def generate_structured(self, prompt: str, **kwargs) -> Union[dict, list]:
        """Generate structured output."""
        if not self.client:
            raise ProcessingError("OrcaRouter client not initialized.")

        create_kwargs = {
            "model": kwargs.get("model", self.model),
            "messages": [{"role": "user", "content": prompt}],
            "response_format": {"type": "json_object"},
        }
        self._add_if_set(create_kwargs, kwargs, "temperature", "max_tokens")

        response = self.client.chat.completions.create(**create_kwargs)
        try:
            return self._parse_json(response.choices[0].message.content)
        except Exception as e:
            raise ProcessingError(f"Failed to parse JSON from OrcaRouter response: {e}")


class HuggingFaceLLMProvider(BaseProvider):
    """HuggingFace transformers for LLM tasks."""

    def __init__(
        self, model_name: str = "gpt2", device: Optional[str] = None, **kwargs
    ):
        """Initialize HuggingFace LLM provider."""
        super().__init__(**kwargs)
        # Lazy import torch only when needed
        try:
            import torch
        except (ImportError, OSError):
            raise ImportError(
                "torch is required for HuggingFaceLLMProvider. Install with: pip install torch"
            )
        
        self.model_name = model_name
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.model = None
        self.tokenizer = None
        self._init_model()

    def _init_model(self):
        """Initialize HuggingFace model."""
        try:
            from transformers import AutoModelForCausalLM, AutoTokenizer

            self.tokenizer = AutoTokenizer.from_pretrained(self.model_name)
            self.model = AutoModelForCausalLM.from_pretrained(self.model_name)
            self.model.to(self.device)
            self.model.eval()
        except (ImportError, OSError):
            self.logger.warning(
                "transformers library not installed. Install with: pip install semantica[models-huggingface]"
            )
        except Exception as e:
            self.logger.warning(
                f"Failed to load HuggingFace model {self.model_name}: {e}"
            )
            self.model = None

    def is_available(self) -> bool:
        """Check if provider is available."""
        return self.model is not None and self.tokenizer is not None

    def generate(self, prompt: str, **kwargs) -> str:
        """Generate text from prompt."""
        if not self.model or not self.tokenizer:
            raise ProcessingError("HuggingFace model not initialized.")

        inputs = self.tokenizer.encode(prompt, return_tensors="pt").to(self.device)
        
        # Use max_new_tokens if available, otherwise fallback to max_length with a safe default
        generate_kwargs = {
            "temperature": kwargs.get("temperature", 0.7),
            "do_sample": True,
        }
        
        if "max_new_tokens" in kwargs:
            generate_kwargs["max_new_tokens"] = kwargs["max_new_tokens"]
        elif "max_tokens" in kwargs:
            generate_kwargs["max_new_tokens"] = kwargs["max_tokens"]
            
        # Support legacy max_length if explicitly provided
        if "max_length" in kwargs:
            generate_kwargs["max_length"] = kwargs["max_length"]
            # Remove max_new_tokens if max_length is set to avoid conflict
            generate_kwargs.pop("max_new_tokens", None)

        outputs = self.model.generate(
            inputs,
            **generate_kwargs
        )
        generated_text = self.tokenizer.decode(outputs[0], skip_special_tokens=True)
        # Remove the original prompt from the response
        return generated_text[len(prompt) :].strip()

    def generate_structured(self, prompt: str, **kwargs) -> dict:
        """Generate structured output."""
        response = self.generate(prompt, **kwargs)
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            start = response.find("{")
            end = response.rfind("}") + 1
            if start >= 0 and end > start:
                return json.loads(response[start:end])
            raise ProcessingError("Failed to parse JSON from HuggingFace response")


class HuggingFaceModelLoader:
    """HuggingFace model loader for NER, RE, Triplets."""

    def __init__(self, device: Optional[str] = None):
        """Initialize HuggingFace model loader."""
        # Lazy import torch only when needed
        try:
            import torch
        except (ImportError, OSError):
            raise ImportError(
                "torch is required for HuggingFaceModelLoader. Install with: pip install torch"
            )
        
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self._cache: Dict[str, Any] = {}
        self.logger = get_logger("huggingface_loader")

    def load_ner_model(self, model_name: str, **kwargs):
        """Load NER model."""
        # Import torch at method level to ensure it's available
        import torch
        
        # Include aggregation_strategy in cache key
        agg_strategy = kwargs.get("aggregation_strategy", "simple")
        cache_key = f"{model_name}_ner_{agg_strategy}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        try:
            from transformers import pipeline
        except ImportError:
            raise ImportError(
                "transformers library not installed. Install with: pip install semantica[models-huggingface]"
            )

        try:
            nlp = pipeline(
                "ner",
                model=model_name,
                device=self.device if torch.cuda.is_available() else -1,
                aggregation_strategy=agg_strategy,
                tokenizer=kwargs.get("tokenizer") # Allow custom tokenizer
            )
            self._cache[cache_key] = nlp
            return nlp
        except OSError as e:
            self.logger.error(f"Failed to load NER model '{model_name}': {e}")
            raise ValueError(f"Could not load HuggingFace model '{model_name}'. Check if model name is correct. Error: {e}")
        except Exception as e:
            self.logger.error(f"Failed to load NER model {model_name}: {e}")
            raise

    def load_relation_model(self, model_name: str, **kwargs):
        """Load relation extraction model."""
        # Import torch at method level to ensure it's available
        import torch
        
        cache_key = f"{model_name}_relation"
        if cache_key in self._cache:
            return self._cache[cache_key]

        try:
            from transformers import pipeline, AutoTokenizer
        except ImportError:
            raise ImportError(
                "transformers library not installed. Install with: pip install semantica[models-huggingface]"
            )

        try:
            # Allow custom tokenizer
            tokenizer = kwargs.get("tokenizer")
            if not tokenizer and kwargs.get("tokenizer_name"):
                tokenizer = AutoTokenizer.from_pretrained(kwargs.get("tokenizer_name"))

            pipeline_kwargs = {
                "model": model_name,
                "device": self.device if torch.cuda.is_available() else -1,
            }
            if tokenizer:
                pipeline_kwargs["tokenizer"] = tokenizer

            nlp = pipeline("text-classification", **pipeline_kwargs)
            self._cache[cache_key] = nlp
            return nlp
        except OSError as e:
            self.logger.error(f"Failed to load relation model '{model_name}': {e}")
            raise ValueError(f"Could not load HuggingFace model '{model_name}'. Check if model name is correct. Error: {e}")
        except Exception as e:
            self.logger.error(f"Failed to load relation model {model_name}: {e}")
            raise

    def load_triplet_model(self, model_name: str, **kwargs):
        """Load triplet extraction model."""
        cache_key = f"{model_name}_triplet"
        if cache_key in self._cache:
            return self._cache[cache_key]

        try:
            from transformers import AutoModelForSeq2SeqLM, AutoTokenizer, pipeline
        except ImportError:
            raise ImportError(
                "transformers library not installed. Install with: pip install semantica[models-huggingface]"
            )

        try:
            # Allow custom tokenizer
            tokenizer = kwargs.get("tokenizer")
            if not tokenizer:
                tokenizer_name = kwargs.get("tokenizer_name", model_name)
                tokenizer = AutoTokenizer.from_pretrained(tokenizer_name)
            
            model = AutoModelForSeq2SeqLM.from_pretrained(model_name)
            model.to(self.device)

            nlp = {"tokenizer": tokenizer, "model": model, "device": self.device}
            self._cache[cache_key] = nlp
            return nlp
        except OSError as e:
            self.logger.error(f"Failed to load triplet model '{model_name}': {e}")
            raise ValueError(f"Could not load HuggingFace model '{model_name}'. Check if model name is correct. Error: {e}")
        except Exception as e:
            self.logger.error(f"Failed to load triplet model {model_name}: {e}")
            raise

    def extract_entities(self, model, text: str) -> List[Dict]:
        """Extract entities using loaded model."""
        return model(text)

    def extract_relations(self, model, text: str, entities: List, **kwargs) -> List[Dict]:
        """
        Extract relations using loaded model.
        Iterates through entity pairs and classifies the relationship.
        """
        results = []
        
        # Sort entities by position
        sorted_entities = sorted(entities, key=lambda e: e.start_char)
        
        # Marker configuration
        subj_start = kwargs.get("subj_start_marker", "<subj>")
        subj_end = kwargs.get("subj_end_marker", "</subj>")
        obj_start = kwargs.get("obj_start_marker", "<obj>")
        obj_end = kwargs.get("obj_end_marker", "</obj>")
        
        # Iterate through all pairs
        import itertools
        for i, e1 in enumerate(sorted_entities):
            for e2 in sorted_entities:
                if e1 == e2:
                    continue
                
                # Check distance (optional optimization)
                # if abs(e1.start_char - e2.start_char) > 200: continue
                
                # Format text with markers
                # Strategy: [CLS] text with <subj>...</subj> and <obj>...</obj> [SEP]
                # We need to insert markers into the original text
                
                # Create a copy of text with markers inserted
                # We need to handle offsets correctly. 
                # Simplest way: reconstruct string pieces
                
                p1_start, p1_end = e1.start_char, e1.end_char
                p2_start, p2_end = e2.start_char, e2.end_char
                
                if p1_start < p2_start:
                    formatted_text = (
                        text[:p1_start] + 
                        f"{subj_start} " + text[p1_start:p1_end] + f" {subj_end}" + 
                        text[p1_end:p2_start] + 
                        f"{obj_start} " + text[p2_start:p2_end] + f" {obj_end}" + 
                        text[p2_end:]
                    )
                else:
                     formatted_text = (
                        text[:p2_start] + 
                        f"{obj_start} " + text[p2_start:p2_end] + f" {obj_end}" + 
                        text[p2_end:p1_start] + 
                        f"{subj_start} " + text[p1_start:p1_end] + f" {subj_end}" + 
                        text[p1_end:]
                    )
                
                # Predict
                try:
                    # Pipeline returns [{'label': 'LABEL', 'score': 0.99}]
                    prediction = model(formatted_text, top_k=1)
                    
                    if prediction:
                        res = prediction[0] if isinstance(prediction, list) else prediction
                        if isinstance(res, list): res = res[0] # top_k=1 returns list of dicts
                        
                        label = res.get("label")
                        score = res.get("score")
                        
                        # Filter "no_relation" or low confidence
                        if label != "no_relation" and score > kwargs.get("threshold", 0.5):
                            results.append({
                                "subject": e1,
                                "object": e2,
                                "relation": label,
                                "score": score
                            })
                except Exception as e:
                    self.logger.warning(f"Relation prediction failed for pair {e1.text}-{e2.text}: {e}")
                    
        return results

    def extract_triplets(self, model, text: str, **kwargs) -> List[Dict]:
        """Extract triplets using loaded model."""
        tokenizer = model["tokenizer"]
        model_obj = model["model"]
        device = model["device"]

        # Use kwargs for max_length, default to 512 for input and 128 for output if not specified
        max_input_length = kwargs.get("max_input_length", 512)
        max_length = kwargs.get("max_length", 128)
        
        generate_kwargs = {"max_length": max_length}
        if "max_new_tokens" in kwargs:
            generate_kwargs["max_new_tokens"] = kwargs["max_new_tokens"]
            
        # Pass other generation args including beams and penalties
        for param in ["num_beams", "temperature", "top_p", "top_k", "do_sample", 
                      "length_penalty", "repetition_penalty"]:
            if param in kwargs:
                generate_kwargs[param] = kwargs[param]

        inputs = tokenizer(
            text, return_tensors="pt", truncation=True, max_length=max_input_length
        ).to(device)
        
        outputs = model_obj.generate(**inputs, **generate_kwargs)
        # Allow controlling skip_special_tokens (important for REBEL which uses special tokens for delimiters)
        skip_special_tokens = kwargs.get("skip_special_tokens", True)
        decoded = tokenizer.decode(outputs[0], skip_special_tokens=skip_special_tokens)

        return [{"triplet": decoded}]


class ProviderPool:
    """Pool for reusing provider instances."""
    
    def __init__(self):
        self._providers: Dict[str, BaseProvider] = {}
        self.logger = get_logger("provider_pool")

    def get(self, name: str, **kwargs) -> BaseProvider:
        """Get or create a provider instance."""
        # Create a cache key from name and kwargs
        # Filter out non-hashable items or volatile args if any
        # For now, we assume kwargs are configuration options that should match
        
        # Helper to make dict hashable
        def make_hashable(value):
            if isinstance(value, dict):
                return tuple(sorted((k, make_hashable(v)) for k, v in value.items()))
            elif isinstance(value, list):
                return tuple(make_hashable(v) for v in value)
            return value

        key_parts = [name]
        for k, v in sorted(kwargs.items()):
            # Skip some keys if they shouldn't affect pooling? 
            # For now, all init args matter for the instance identity.
            key_parts.append((k, make_hashable(v)))
            
        key = str(tuple(key_parts))
        
        if key in self._providers:
            return self._providers[key]
            
        self.logger.debug(f"Creating new provider instance for {name}")
        provider = self._create_provider(name, **kwargs)
        self._providers[key] = provider
        return provider
    
    def _create_provider(self, name: str, **kwargs) -> BaseProvider:
        """Internal creation logic."""
        # Check registry first
        custom_provider = provider_registry.get(name)
        if custom_provider:
            return custom_provider(**kwargs)

        # Built-in providers
        builtin = {
            "openai": OpenAIProvider,
            "gemini": GeminiProvider,
            "groq": GroqProvider,
            "anthropic": AnthropicProvider,
            "ollama": OllamaProvider,
            "huggingface_llm": HuggingFaceLLMProvider,
            "deepseek": DeepSeekProvider,
            "novita": NovitaProvider,
            "orcarouter": OrcaRouterProvider,
        }

        provider_class = builtin.get(name.lower())
        if not provider_class:
            raise ValueError(
                f"Unknown provider: {name}. Register custom provider or use built-in: {list(builtin.keys())}"
            )

        return provider_class(**kwargs)

    def clear(self):
        """Clear the provider pool."""
        self._providers.clear()


# Global provider pool
_provider_pool = ProviderPool()


def create_provider(name: str, use_pool: bool = True, **kwargs) -> BaseProvider:
    """
    Create provider - checks registry for custom providers.
    
    Args:
        name: Provider name
        use_pool: Whether to use the provider pool (default: True)
        **kwargs: Provider arguments
    """
    if use_pool:
        return _provider_pool.get(name, **kwargs)
        
    return _provider_pool._create_provider(name, **kwargs)
