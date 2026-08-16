"""
Configuration Management Module for Split

This module provides centralized configuration management for text splitting and chunking,
supporting multiple configuration sources including environment variables, config files,
and programmatic configuration.

Supported Configuration Sources:
    - Environment variables: SPLIT_CHUNK_SIZE, SPLIT_CHUNK_OVERLAP, etc.
    - Config files: YAML, JSON, TOML formats
    - Programmatic: Python API for setting split configurations

Algorithms Used:
    - Environment Variable Parsing: OS-level environment variable access
    - YAML Parsing: YAML parser for configuration file loading
    - JSON Parsing: JSON parser for configuration file loading
    - TOML Parsing: TOML parser for configuration file loading
    - Fallback Chain: Priority-based configuration resolution
    - Dictionary Merging: Deep merge algorithms for configuration updates

Key Features:
    - Environment variable support for split parameters
    - Config file support (YAML, JSON, TOML formats)
    - Programmatic configuration via Python API
    - Method-specific configuration management
    - Automatic fallback chain (config file -> environment -> defaults)
    - Global config instance for easy access

Main Classes:
    - SplitConfig: Main configuration manager class for split module

Example Usage:
    >>> from semantica.split.config import split_config
    >>> chunk_size = split_config.get("chunk_size", default=1000)
    >>> split_config.set("chunk_size", 2000)
    >>> method_config = split_config.get_method_config("recursive")

Author: Semantica Contributors
License: MIT
"""

import os
from pathlib import Path
from typing import Any, Dict, Optional

from ..utils.logging import get_logger


class SplitConfig:
    """Configuration manager for split module - supports .env files, environment variables, and programmatic config."""

    def __init__(self, config_file: Optional[str] = None):
        """Initialize configuration manager."""
        self.logger = get_logger("split_config")
        self._configs: Dict[str, Any] = {}
        self._method_configs: Dict[str, Dict] = {}
        self._load_config_file(config_file)
        self._load_env_vars()

    def _load_config_file(self, config_file: Optional[str]):
        """Load configuration from file."""
        if config_file and Path(config_file).exists():
            try:
                # Support YAML, JSON, TOML
                if config_file.endswith(".yaml") or config_file.endswith(".yml"):
                    import yaml

                    with open(config_file, "r") as f:
                        data = yaml.safe_load(f) or {}
                        self._configs.update(data.get("split", {}))
                        self._method_configs.update(data.get("split_methods", {}))
                elif config_file.endswith(".json"):
                    import json

                    with open(config_file, "r") as f:
                        data = json.load(f) or {}
                        self._configs.update(data.get("split", {}))
                        self._method_configs.update(data.get("split_methods", {}))
                elif config_file.endswith(".toml"):
                    import toml

                    with open(config_file, "r") as f:
                        data = toml.load(f) or {}
                        if "split" in data:
                            self._configs.update(data["split"])
                        if "split_methods" in data:
                            self._method_configs.update(data["split_methods"])
            except Exception as e:
                self.logger.warning(f"Failed to load config file {config_file}: {e}")

    def _load_env_vars(self):
        """Load configuration from environment variables."""
        # Common environment variable patterns for split module
        env_mappings = {
            "SPLIT_CHUNK_SIZE": ("chunk_size", int),
            "SPLIT_CHUNK_OVERLAP": ("chunk_overlap", int),
            "SPLIT_DEFAULT_METHOD": ("default_method", str),
            "SPLIT_MAX_CHUNK_SIZE": ("max_chunk_size", int),
            "SPLIT_MIN_CHUNK_SIZE": ("min_chunk_size", int),
        }

        for env_key, (config_key, type_func) in env_mappings.items():
            value = os.getenv(env_key)
            if value:
                try:
                    self._configs[config_key] = type_func(value)
                except (ValueError, TypeError):
                    self.logger.warning(f"Failed to parse {env_key}={value}")

    def set(self, key: str, value: Any):
        """Set configuration value programmatically."""
        self._configs[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value with fallback chain: config -> env -> default."""
        # Check config first
        if key in self._configs:
            return self._configs[key]

        # Check environment variables
        env_key = f"SPLIT_{key.upper()}"
        value = os.getenv(env_key)
        if value:
            try:
                # Try to convert to appropriate type
                if isinstance(default, bool):
                    return value.strip().lower() in ("true", "1", "yes", "on")
                elif isinstance(default, int):
                    return int(value)
                elif isinstance(default, float):
                    return float(value)
                return value
            except (ValueError, TypeError):
                pass

        return default

    def set_method_config(self, method: str, **config):
        """Set method-specific configuration."""
        self._method_configs[method] = config

    def get_method_config(self, method: str) -> Dict:
        """Get method-specific configuration."""
        return self._method_configs.get(method, {})

    def get_all(self) -> Dict[str, Any]:
        """Get all configuration."""
        return {
            "config": self._configs.copy(),
            "method_configs": self._method_configs.copy(),
        }


# Global config instance
split_config = SplitConfig()
