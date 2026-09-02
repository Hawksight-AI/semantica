"""
Configuration Management Module for Normalize

This module provides centralized configuration management for data normalization operations,
supporting multiple configuration sources including environment variables, config files,
and programmatic configuration.

Supported Configuration Sources:
    - Environment variables: NORMALIZE_UNICODE_FORM, NORMALIZE_CASE, NORMALIZE_DATE_FORMAT, etc.
    - Config files: YAML, JSON, TOML formats
    - Programmatic: Python API for setting normalization configurations

Algorithms Used:
    - Environment Variable Parsing: OS-level environment variable access
    - YAML Parsing: YAML parser for configuration file loading
    - JSON Parsing: JSON parser for configuration file loading
    - TOML Parsing: TOML parser for configuration file loading
    - Fallback Chain: Priority-based configuration resolution
    - Dictionary Merging: Deep merge algorithms for configuration updates

Key Features:
    - Environment variable support for normalization parameters
    - Config file support (YAML, JSON, TOML formats)
    - Programmatic configuration via Python API
    - Method-specific configuration management
    - Automatic fallback chain (config file -> environment -> defaults)
    - Global config instance for easy access

Main Classes:
    - NormalizeConfig: Main configuration manager class for normalize module

Example Usage:
    >>> from semantica.normalize.config import normalize_config
    >>> unicode_form = normalize_config.get("unicode_form", default="NFC")
    >>> normalize_config.set("unicode_form", "NFKC")
    >>> method_config = normalize_config.get_method_config("text")
"""

import os
from pathlib import Path
from typing import Any, Dict, Optional

from ..utils.logging import get_logger


class NormalizeConfig:
    """Configuration manager for normalize module - supports .env files, environment variables, and programmatic config."""

    def __init__(self, config_file: Optional[str] = None):
        self.logger = get_logger("normalize_config")
        self._configs: Dict[str, Any] = {}
        self._method_configs: Dict[str, Dict] = {}
        self._load_config_file(config_file)
        self._load_env_vars()

    def _load_config_file(self, config_file: Optional[str]):
        if config_file and Path(config_file).exists():
            try:
                if config_file.endswith(".yaml") or config_file.endswith(".yml"):
                    import yaml

                    with open(config_file, "r") as f:
                        data = yaml.safe_load(f) or {}
                        self._configs.update(data.get("normalize", {}))
                        self._method_configs.update(data.get("normalize_methods", {}))
                elif config_file.endswith(".json"):
                    import json

                    with open(config_file, "r") as f:
                        data = json.load(f) or {}
                        self._configs.update(data.get("normalize", {}))
                        self._method_configs.update(data.get("normalize_methods", {}))
                elif config_file.endswith(".toml"):
                    import toml

                    with open(config_file, "r") as f:
                        data = toml.load(f) or {}
                        if "normalize" in data:
                            self._configs.update(data["normalize"])
                        if "normalize_methods" in data:
                            self._method_configs.update(data["normalize_methods"])
                self.logger.info(f"Loaded normalize config from {config_file}")
            except Exception as e:
                self.logger.warning(f"Failed to load config file {config_file}: {e}")

    def _load_env_vars(self):
        env_mappings = {
            "NORMALIZE_UNICODE_FORM": ("unicode_form", str),
            "NORMALIZE_CASE": ("case", str),
            "NORMALIZE_DATE_FORMAT": ("date_format", str),
            "NORMALIZE_TIMEZONE": ("timezone", str),
            "NORMALIZE_DEFAULT_LANGUAGE": ("default_language", str),
            "NORMALIZE_DEFAULT_ENCODING": ("default_encoding", str),
        }

        for env_key, (config_key, type_func) in env_mappings.items():
            value = os.getenv(env_key)
            if value:
                try:
                    if type_func == bool:
                        self._configs[config_key] = value.strip().lower() in (
                            "true",
                            "1",
                            "yes",
                            "on",
                        )
                    else:
                        self._configs[config_key] = type_func(value)
                except (ValueError, TypeError):
                    self.logger.warning(f"Failed to parse {env_key}={value}")

        env_prefix = "NORMALIZE_"
        for key, value in os.environ.items():
            if key.startswith(env_prefix) and key not in env_mappings:
                config_key = key[len(env_prefix) :].lower()
                if value.strip().lower() in ("true", "false"):
                    self._configs[config_key] = value.strip().lower() == "true"
                elif value.isdigit():
                    self._configs[config_key] = int(value)
                else:
                    try:
                        self._configs[config_key] = float(value)
                    except ValueError:
                        self._configs[config_key] = value

    def set(self, key: str, value: Any):
        """Set configuration value programmatically."""
        self._configs[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value with fallback chain: config -> env -> default."""
        if key in self._configs:
            return self._configs[key]

        env_key = f"NORMALIZE_{key.upper()}"
        value = os.getenv(env_key)
        if value:
            try:
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
normalize_config = NormalizeConfig()
