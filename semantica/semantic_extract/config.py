"""
Configuration Management Module

This module provides centralized configuration management for semantic extraction,
supporting multiple configuration sources including environment variables, config files,
and programmatic configuration.

Supported Configuration Sources:
    - Environment variables: OPENAI_API_KEY, GEMINI_API_KEY, GROQ_API_KEY, NOVITA_API_KEY, ORCAROUTER_API_KEY, etc.
    - Config files: YAML, JSON, TOML formats
    - Programmatic: Python API for setting provider configurations

Algorithms Used:
    - Environment Variable Parsing: OS-level environment variable access
    - YAML Parsing: YAML parser for configuration file loading
    - JSON Parsing: JSON parser for configuration file loading
    - TOML Parsing: TOML parser for configuration file loading
    - Fallback Chain: Priority-based configuration resolution
    - Dictionary Merging: Deep merge algorithms for configuration updates

Key Features:
    - Environment variable support for API keys (OPENAI_API_KEY, GEMINI_API_KEY, etc.)
    - Config file support (YAML, JSON, TOML formats)
    - Programmatic configuration via Python API
    - Provider-specific configuration management
    - Automatic fallback chain (config file -> environment -> defaults)
    - Global config instance for easy access

Main Classes:
    - Config: Main configuration manager class

Example Usage:
    >>> from semantica.semantic_extract.config import config
    >>> api_key = config.get_api_key("openai")
    >>> config.set_provider("openai", api_key="sk-...", model="gpt-4")
    >>> provider_config = config.get_provider_config("gemini")

Author: Semantica Contributors
License: MIT
"""

import os
import multiprocessing
from pathlib import Path
from typing import Dict, Optional, Any

from ..utils.logging import get_logger


class Config:
    """Configuration manager - supports .env files, environment variables, and programmatic config."""

    def __init__(self, config_file: Optional[str] = None):
        """Initialize configuration manager."""
        self.logger = get_logger("config")
        self._configs: Dict[str, Dict] = {}
        # Default optimization settings
        self._configs["optimization"] = {
            "enable_cache": True,
            "cache_size": 1000,
            "max_workers": 8,
            "enable_batching": True,
            "batch_size": 10,
            "max_tokens_per_batch": 2000
        }
        self._load_config_file(config_file)
        self._load_env_vars()

    def get_optimization_config(self) -> Dict:
        """Get optimization configuration."""
        return self._configs.get("optimization", {})


    def _load_config_file(self, config_file: Optional[str]):
        """Load configuration from file."""
        if config_file and Path(config_file).exists():
            try:
                # Support YAML, JSON, TOML
                if config_file.endswith(".yaml") or config_file.endswith(".yml"):
                    import yaml

                    with open(config_file, "r") as f:
                        self._configs.update(yaml.safe_load(f) or {})
                elif config_file.endswith(".json"):
                    import json

                    with open(config_file, "r") as f:
                        self._configs.update(json.load(f) or {})
                elif config_file.endswith(".toml"):
                    import toml

                    with open(config_file, "r") as f:
                        self._configs.update(toml.load(f) or {})
            except Exception as e:
                self.logger.warning(f"Failed to load config file {config_file}: {e}")

    def _load_env_vars(self):
        """Load configuration from environment variables."""
        # Common environment variable patterns
        providers = [
            "openai",
            "gemini",
            "groq",
            "anthropic",
            "ollama",
            "novita",
            "orcarouter",
        ]
        for provider in providers:
            env_key = f"{provider.upper()}_API_KEY"
            api_key = os.getenv(env_key)
            if api_key:
                if provider not in self._configs:
                    self._configs[provider] = {}
                self._configs[provider]["api_key"] = api_key

    def set_provider(self, name: str, **config):
        """Set provider config programmatically."""
        self._configs[name] = config

    def get_provider_config(self, name: str) -> Dict:
        """Get provider configuration."""
        if name in self._configs:
            return self._configs[name]

        # Fallback to environment variables
        env_key = f"{name.upper()}_API_KEY"
        api_key = os.getenv(env_key)
        if api_key:
            return {"api_key": api_key}

        return {}

    def get_api_key(self, provider: str) -> Optional[str]:
        """Get API key with fallback chain: config -> env -> None."""
        if provider in self._configs:
            return self._configs[provider].get("api_key")
        return os.getenv(f"{provider.upper()}_API_KEY")

    def get(self, key: str, default: Any = None) -> Any:
        """
        Get configuration value by key.
        Searches in top-level configs and optimization settings.
        """
        # 1. Check top-level keys
        if key in self._configs:
            return self._configs[key]
            
        # 2. Check optimization settings (common keys)
        if "optimization" in self._configs and key in self._configs["optimization"]:
            return self._configs["optimization"][key]
            
        # 3. Handle specific mapping for optimization keys
        # Map cache_enabled -> enable_cache if needed
        if key == "cache_enabled":
            return self._configs.get("optimization", {}).get("enable_cache", default)
            
        return default


# Global config instance
config = Config()


def resolve_max_workers(
    explicit: Optional[int] = None,
    local_config: Optional[Dict[str, Any]] = None,
    methods: Optional[Any] = None,
) -> int:
    def to_int(val: Any, default: int) -> int:
        try:
            return int(val)
        except Exception:
            return default

    if isinstance(methods, str):
        normalized_methods = [methods]
    elif isinstance(methods, (list, tuple, set)):
        normalized_methods = [m for m in methods if isinstance(m, str)]
    else:
        normalized_methods = []

    if explicit is not None:
        value = to_int(explicit, 1)
    elif local_config and "max_workers" in local_config:
        value = to_int(local_config.get("max_workers", 1), 1)
    else:
        value = to_int(config.get("max_workers", 5), 5)

    if "ml" in normalized_methods and explicit is None and not (local_config and "max_workers" in local_config):
        value = 1

    if value < 1:
        value = 1

    cpu_count = multiprocessing.cpu_count() or 1
    if value > cpu_count:
        value = cpu_count
    if value > 32:
        value = 32

    return value
