"""
LLM Providers Module

This module provides clean, intuitive imports for LLM providers used in Semantica.
It wraps the underlying provider functionality from semantica.semantic_extract.providers
to provide a cleaner API.

Supported Providers:
    - Groq: Groq API for fast inference
    - OpenAI: OpenAI API (GPT-3.5, GPT-4, etc.)
    - HuggingFaceLLM: HuggingFace Transformers for local LLM inference
    - LiteLLM: Unified interface to 100+ LLM providers (OpenAI, Anthropic, Groq, Azure, Bedrock, Vertex AI, etc.)
    - Anthropic: Anthropic Claude API (Claude sonnet, Opus, Haiku, etc.)
    - Gemini: Google Gemini API
    - Ollama: Local models served through Ollama
    - DeepSeek: DeepSeek's OpenAI-compatible API
    - Novita: Novita AI's OpenAI-compatible API

Example Usage:
    >>> from semantica.llms import Groq, OpenAI, HuggingFaceLLM, LiteLLM, Anthropic
    >>>
    >>> # Groq provider
    >>> groq = Groq(model="llama-3.1-8b-instant", api_key="your-key")
    >>> response = groq.generate("Hello, world!")
    >>>
    >>> # OpenAI provider
    >>> openai = OpenAI(model="gpt-4", api_key="your-key")
    >>> response = openai.generate("Hello, world!")
    >>>
    >>> # HuggingFace LLM provider
    >>> hf = HuggingFaceLLM(model_name="gpt2")
    >>> response = hf.generate("Hello, world!")
    >>>
    >>> # LiteLLM provider (supports 100+ LLMs)
    >>> llm = LiteLLM(model="openai/gpt-4o", api_key="your-key")
    >>> response = llm.generate("Hello, world!")
    >>> # Or use other providers via LiteLLM
    >>> llm = LiteLLM(model="anthropic/claude-sonnet-5")
    >>> response = llm.generate("Hello, world!")
    >>>
    >>> # Anthropic provider
    >>> claude = Anthropic(model="claude-sonnet-4-6", api_key="the-key")
    >>> response = claude.generate("Hello, world!")
    >>>
    >>> # Gemini provider
    >>> gemini = Gemini(model="gemini-pro", api_key="your-key")
    >>> response = gemini.generate("Hello, world!")
    >>>
    >>> # Ollama provider (local, no api_key)
    >>> ollama = Ollama(model="llama2")
    >>> response = ollama.generate("Hello, world!")
    >>>
    >>> # DeepSeek provider
    >>> deepseek = DeepSeek(model="deepseek-chat", api_key="your-key")
    >>> response = deepseek.generate("Hello, world!")
    >>>
    >>> # Novita provider
    >>> novita = Novita(model="deepseek/deepseek-v3.2", api_key="your-key")
    >>> response = novita.generate("Hello, world!")

Author: Semantica Contributors
License: MIT
"""

from .groq import Groq
from .openai import OpenAI
from .huggingface import HuggingFaceLLM
from .litellm import LiteLLM
from .anthropic import Anthropic
from .gemini import Gemini
from .ollama import Ollama
from .deepseek import DeepSeek
from .novita import Novita

__all__ = [
    "Groq",
    "OpenAI",
    "HuggingFaceLLM",
    "LiteLLM",
    "Anthropic",
    "Gemini",
    "Ollama",
    "DeepSeek",
    "Novita",
]
